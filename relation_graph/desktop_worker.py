from __future__ import annotations

import json
import logging
import sys
from typing import Any, Callable

from relation_graph.desktop_service import DesktopServiceError, RelationGraphDesktopService


logger = logging.getLogger(__name__)


class DesktopWorkerProtocolError(RuntimeError):
    pass


class RelationGraphDesktopWorker:
    def __init__(self, service: RelationGraphDesktopService | None = None):
        self._service = service or RelationGraphDesktopService()
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "provider.getStatus": lambda params: self._service.get_provider_status(),
            "provider.bindModelDir": self._service.bind_model_dir,
            "provider.downloadModels": self._service.download_models,
            "provider.ensureStarted": lambda params: self._service.ensure_started(),
            "provider.launchRuntimeTerminal": lambda params: self._service.launch_runtime_terminal(),
            "provider.setPreferredModel": self._service.set_preferred_model,
            "job.submit": self._service.submit_job,
            "job.getStatus": self._service.get_job_status,
            "app.shutdown": self._handle_shutdown,
        }
        self._running = False

    def run(self) -> int:
        self._service.start()
        self._running = True
        try:
            for line in sys.stdin:
                payload = line.strip()
                if not payload:
                    continue
                response = self._handle_line(payload)
                self._write_message(response)
                if response.get("method") == "app.shutdown" or response.get("shutdown"):
                    break
        finally:
            self._service.shutdown()
            self._running = False
        return 0

    def _handle_line(self, payload: str) -> dict[str, Any]:
        request_id = None
        method = ""
        try:
            message = json.loads(payload)
            if not isinstance(message, dict):
                raise DesktopWorkerProtocolError("协议消息必须是 JSON 对象。")
            request_id = message.get("id")
            method = str(message.get("method") or "").strip()
            if not request_id:
                raise DesktopWorkerProtocolError("协议消息缺少 id。")
            if not method:
                raise DesktopWorkerProtocolError("协议消息缺少 method。")
            params = message.get("params") or {}
            if not isinstance(params, dict):
                raise DesktopWorkerProtocolError("协议消息 params 必须是对象。")
            handler = self._handlers.get(method)
            if handler is None:
                raise DesktopWorkerProtocolError(f"不支持的方法：{method}")
            result = handler(params)
            response = {"id": request_id, "ok": True, "result": result}
            if method == "app.shutdown":
                response["method"] = method
                response["shutdown"] = True
            return response
        except DesktopServiceError as exc:
            return self._error_response(request_id, str(exc), "service_error")
        except DesktopWorkerProtocolError as exc:
            return self._error_response(request_id, str(exc), "protocol_error")
        except Exception as exc:
            logger.exception("桌面 worker 处理请求失败: %s", method or "<unknown>")
            return self._error_response(request_id, f"桌面服务异常：{exc}", "internal_error")

    def _handle_shutdown(self, params: dict[str, Any]) -> dict[str, bool]:
        self._running = False
        return {"ok": True}

    @staticmethod
    def _error_response(request_id: Any, message: str, code: str) -> dict[str, Any]:
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "message": message,
                "code": code,
            },
        }

    @staticmethod
    def _write_message(payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
