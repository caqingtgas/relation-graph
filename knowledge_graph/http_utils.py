from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx


HttpStatusHandler = Callable[[httpx.HTTPStatusError, int], dict[str, Any]]
TransportErrorHandler = Callable[[Exception], Exception]
ResponseFormatErrorFactory = Callable[[str], Exception]


def create_http_client(*, timeout: float) -> httpx.Client:
    return httpx.Client(timeout=float(timeout), http2=False)


def request_json_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    json_payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retry_count: int,
    status_handler: HttpStatusHandler,
    transport_error_handler: TransportErrorHandler,
    response_format_error_factory: ResponseFormatErrorFactory,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retry_count + 2):
        try:
            response = client.request(method, url, json=json_payload, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise response_format_error_factory("返回了非对象响应。")
            return payload
        except httpx.HTTPStatusError as exc:
            action = status_handler(exc, attempt)
            if action.get("retry"):
                time.sleep(float(action.get("delay", 0)))
                continue
            raise action["error"] from exc
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt <= retry_count:
                time.sleep(float(2 ** (attempt - 1)))
                continue
            raise transport_error_handler(exc) from exc
        except json.JSONDecodeError as exc:
            raise response_format_error_factory(f"返回 JSON 解析失败：{exc}") from exc
    raise transport_error_handler(last_error or RuntimeError("unknown transport error"))
