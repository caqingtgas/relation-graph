from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from relation_graph.http_utils import create_http_client, request_json_with_retry
from relation_graph.settings import (
    ARK_BASE_URL,
    ARK_ENDPOINT_PATH,
    DEFAULT_MODEL_ID,
    LLM_PARSE_RETRY_COUNT,
    LLM_REQUEST_RETRY_COUNT,
    LLM_TIMEOUT_SECONDS,
)


class ArkClientError(RuntimeError):
    pass


class ArkAuthenticationError(ArkClientError):
    pass


class ArkTransportError(ArkClientError):
    pass


class ArkResponseFormatError(ArkClientError):
    pass


@dataclass(frozen=True)
class ArkClientConfig:
    api_key: str
    model: str = DEFAULT_MODEL_ID
    base_url: str = ARK_BASE_URL
    endpoint_path: str = ARK_ENDPOINT_PATH
    timeout: int = LLM_TIMEOUT_SECONDS
    retry_count: int = LLM_REQUEST_RETRY_COUNT
    parse_retry_count: int = LLM_PARSE_RETRY_COUNT


@dataclass(frozen=True)
class ArkUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_payload(cls, payload: dict) -> "ArkUsage":
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return cls()
        return cls(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
        )

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class ArkClient:
    def __init__(self, config: ArkClientConfig):
        if not config.api_key:
            raise ArkAuthenticationError("未提供火山方舟 API Key。")
        self.config = config
        self._client = create_http_client(timeout=float(self.config.timeout))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ArkClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def generate_json(
        self,
        *,
        user_prompt: str,
        response_schema: dict,
        schema_name: str,
        schema_description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        request_label: Optional[str] = None,
    ) -> dict:
        parsed, _ = self.generate_json_with_usage(
            user_prompt=user_prompt,
            response_schema=response_schema,
            schema_name=schema_name,
            schema_description=schema_description,
            system_prompt=system_prompt,
            model=model,
            request_label=request_label,
        )
        return parsed

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
    ) -> tuple[dict, ArkUsage]:
        payload = self._build_payload(
            user_prompt=user_prompt,
            response_schema=response_schema,
            schema_name=schema_name,
            schema_description=schema_description,
            system_prompt=system_prompt,
            model=model,
        )
        last_error: ArkResponseFormatError | None = None
        for attempt in range(1, self.config.parse_retry_count + 2):
            response_payload = self._post(payload, request_label=request_label)
            usage = ArkUsage.from_payload(response_payload)
            raw_content = self._extract_message_content(response_payload)
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError as exc:
                last_error = ArkResponseFormatError(
                    f"{self._prefix(request_label)}结构化输出解析失败：{exc}"
                )
            else:
                if isinstance(parsed, dict):
                    return parsed, usage
                last_error = ArkResponseFormatError(f"{self._prefix(request_label)}结构化输出不是 JSON 对象。")
            if attempt <= self.config.parse_retry_count:
                time.sleep(min(attempt, 2))
        raise last_error or ArkResponseFormatError(f"{self._prefix(request_label)}结构化输出解析失败。")

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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return {
            "model": model or self.config.model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "description": schema_description,
                    "schema": response_schema,
                    "strict": True,
                },
            },
        }

    @staticmethod
    def _prefix(request_label: Optional[str]) -> str:
        return f"[{request_label}] " if request_label else ""

    @staticmethod
    def _retry_delay(attempt: int, response: httpx.Response) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return float(2 ** (attempt - 1))

    def _post(self, payload: dict, *, request_label: Optional[str] = None) -> dict:
        url = f"{self.config.base_url.rstrip('/')}/{self.config.endpoint_path.lstrip('/')}"
        prefix = self._prefix(request_label)
        return request_json_with_retry(
            self._client,
            "POST",
            url,
            json_payload=payload,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            retry_count=self.config.retry_count,
            status_handler=lambda exc, attempt: self._handle_status_error(exc, attempt, prefix),
            transport_error_handler=lambda exc: self._handle_transport_error(exc, prefix),
            response_format_error_factory=lambda detail: ArkResponseFormatError(f"{prefix}火山方舟{detail}"),
        )

    def _handle_status_error(self, exc: httpx.HTTPStatusError, attempt: int, prefix: str) -> dict:
        status_code = exc.response.status_code
        detail = exc.response.text[:400]
        if status_code in {401, 403}:
            return {
                "retry": False,
                "error": ArkAuthenticationError(
                    f"{prefix}火山方舟鉴权失败，状态码 {status_code}。请检查 API Key 是否正确。"
                ),
            }
        if status_code in {429, 502, 503, 504} and attempt <= self.config.retry_count:
            return {
                "retry": True,
                "delay": self._retry_delay(attempt, exc.response),
            }
        return {
            "retry": False,
            "error": ArkTransportError(f"{prefix}火山方舟请求失败，状态码 {status_code}，返回：{detail}"),
        }

    @staticmethod
    def _handle_transport_error(exc: Exception, prefix: str) -> ArkTransportError:
        cause = getattr(exc, "__cause__", None)
        if isinstance(cause, ssl.SSLError):
            return ArkTransportError(f"{prefix}网络连接异常（SSL 握手失败）：{cause}")
        return ArkTransportError(f"{prefix}网络连接异常：{exc}")

    @staticmethod
    def _extract_message_content(payload: dict) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ArkResponseFormatError("火山方舟返回中缺少 choices。")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ArkResponseFormatError("火山方舟返回中缺少 message。")
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            if parts:
                return "".join(parts)
        raise ArkResponseFormatError("火山方舟返回中缺少可解析的 content。")

