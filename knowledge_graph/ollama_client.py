from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from knowledge_graph.http_utils import create_http_client, request_json_with_retry
from knowledge_graph.settings import (
    LOCAL_OLLAMA_BASE_URL,
    LOCAL_PARSE_RETRY_COUNT,
    LOCAL_PRIMARY_MODEL_ID,
    LOCAL_REQUEST_RETRY_COUNT,
    LOCAL_TIMEOUT_SECONDS,
)


class OllamaClientError(RuntimeError):
    pass


class OllamaTransportError(OllamaClientError):
    pass


class OllamaResponseFormatError(OllamaClientError):
    pass


@dataclass(frozen=True)
class OllamaClientConfig:
    model: str = LOCAL_PRIMARY_MODEL_ID
    base_url: str = LOCAL_OLLAMA_BASE_URL
    timeout: int = LOCAL_TIMEOUT_SECONDS
    retry_count: int = LOCAL_REQUEST_RETRY_COUNT
    parse_retry_count: int = LOCAL_PARSE_RETRY_COUNT


@dataclass(frozen=True)
class OllamaUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_payload(cls, payload: dict) -> "OllamaUsage":
        prompt_tokens = int(payload.get("prompt_eval_count") or 0)
        completion_tokens = int(payload.get("eval_count") or 0)
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class OllamaClient:
    def __init__(self, config: OllamaClientConfig):
        self.config = config
        self._client = create_http_client(timeout=float(self.config.timeout))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _prefix(request_label: Optional[str]) -> str:
        return f"[{request_label}] " if request_label else ""

    def list_models(self) -> list[str]:
        payload = self._request_json("GET", "/api/tags")
        models = payload.get("models")
        if not isinstance(models, list):
            return []
        model_names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("model") or item.get("name") or "").strip()
            if name:
                model_names.append(name)
        return model_names

    def health_check(self) -> bool:
        try:
            self.list_models()
            return True
        except OllamaClientError:
            return False

    def generate_json_with_usage(
        self,
        *,
        user_prompt: str,
        response_schema: dict,
        schema_name: str,
        schema_description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        request_label: Optional[str] = None,
    ) -> tuple[dict, OllamaUsage]:
        payload = self._build_payload(
            user_prompt=user_prompt,
            response_schema=response_schema,
            schema_name=schema_name,
            schema_description=schema_description,
            system_prompt=system_prompt,
            model=model,
        )
        last_error: OllamaResponseFormatError | None = None
        for attempt in range(1, self.config.parse_retry_count + 2):
            response_payload = self._request_json("POST", "/api/chat", json_payload=payload, request_label=request_label)
            usage = OllamaUsage.from_payload(response_payload)
            raw_content = self._extract_structured_content(response_payload)
            try:
                parsed = self._parse_json_text(raw_content)
            except json.JSONDecodeError as exc:
                preview = raw_content[:200].replace("\n", "\\n")
                last_error = OllamaResponseFormatError(
                    f"{self._prefix(request_label)}本地模型结构化输出解析失败：{exc}；原始片段：{preview}"
                )
            else:
                if isinstance(parsed, dict):
                    return parsed, usage
                last_error = OllamaResponseFormatError(f"{self._prefix(request_label)}本地模型结构化输出不是 JSON 对象。")
            if attempt <= self.config.parse_retry_count:
                time.sleep(min(attempt, 2))
        raise last_error or OllamaResponseFormatError(f"{self._prefix(request_label)}本地模型结构化输出解析失败。")

    def _build_payload(
        self,
        *,
        user_prompt: str,
        response_schema: dict,
        schema_name: str,
        schema_description: Optional[str],
        system_prompt: Optional[str],
        model: Optional[str],
    ) -> dict:
        grounded_user_prompt = self._build_grounded_user_prompt(
            user_prompt=user_prompt,
            response_schema=response_schema,
            schema_name=schema_name,
            schema_description=schema_description,
        )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": grounded_user_prompt})
        return {
            "model": model or self.config.model,
            "messages": messages,
            "stream": False,
            "format": response_schema,
            "think": False,
            "options": {
                "temperature": 0,
            },
        }

    @staticmethod
    def _build_grounded_user_prompt(
        *,
        user_prompt: str,
        response_schema: dict,
        schema_name: str,
        schema_description: Optional[str],
    ) -> str:
        schema_json = json.dumps(response_schema, ensure_ascii=False, separators=(",", ":"))
        description_line = f"\nSchema说明：{schema_description}" if schema_description else ""
        return (
            f"{user_prompt}\n\n"
            f"你必须只输出一个 JSON 对象，不能输出解释、前后缀、Markdown 代码块、思考过程。"
            f"\nSchema名称：{schema_name}{description_line}\n"
            f"请严格遵循以下 JSON Schema：\n{schema_json}"
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[dict] = None,
        request_label: Optional[str] = None,
    ) -> dict:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        prefix = self._prefix(request_label)
        return request_json_with_retry(
            self._client,
            method,
            url,
            json_payload=json_payload,
            retry_count=self.config.retry_count,
            status_handler=lambda exc, attempt: self._handle_status_error(exc, attempt, prefix),
            transport_error_handler=lambda exc: OllamaTransportError(f"{prefix}本地模型连接异常：{exc}"),
            response_format_error_factory=lambda detail: OllamaResponseFormatError(f"{prefix}本地模型{detail}"),
        )

    def _handle_status_error(self, exc: httpx.HTTPStatusError, attempt: int, prefix: str) -> dict:
        status_code = exc.response.status_code
        detail = exc.response.text[:400]
        if status_code in {502, 503, 504} and attempt <= self.config.retry_count:
            return {
                "retry": True,
                "delay": float(2 ** (attempt - 1)),
            }
        return {
            "retry": False,
            "error": OllamaTransportError(f"{prefix}本地模型请求失败，状态码 {status_code}，返回：{detail}"),
        }

    @staticmethod
    def _extract_structured_content(payload: dict) -> str:
        message = payload.get("message")
        if not isinstance(message, dict):
            raise OllamaResponseFormatError("本地模型返回中缺少 message。")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            first_call = tool_calls[0]
            if isinstance(first_call, dict):
                function_info = first_call.get("function")
                if isinstance(function_info, dict):
                    arguments = function_info.get("arguments")
                    if isinstance(arguments, dict):
                        return json.dumps(arguments, ensure_ascii=False)
                    if isinstance(arguments, str) and arguments.strip():
                        return arguments.strip()
        raise OllamaResponseFormatError("本地模型返回中缺少可解析的 content。")

    @staticmethod
    def _parse_json_text(raw_content: str) -> dict:
        text = raw_content.strip()
        if not text:
            raise json.JSONDecodeError("empty content", raw_content, 0)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            extracted = OllamaClient._extract_json_object(text)
            if extracted is not None:
                return json.loads(extracted)

        raise json.JSONDecodeError("no json object found", raw_content, 0)

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                inner = "\n".join(lines[1:-1]).strip()
                if inner:
                    return inner

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return None
