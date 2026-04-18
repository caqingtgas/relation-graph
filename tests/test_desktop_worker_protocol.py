from __future__ import annotations

from relation_graph.desktop_service import DesktopServiceError
from relation_graph.desktop_worker import RelationGraphDesktopWorker


class StubService:
    def __init__(self):
        self.started = False
        self.shutdown_called = False

    def start(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.shutdown_called = True

    def get_provider_status(self) -> dict[str, object]:
        return {"provider_mode": "ark", "local_runtime_status": "stopped"}

    def bind_model_dir(self, params: dict[str, object]) -> dict[str, object]:
        raise DesktopServiceError(
            "目录不可用。",
            code="provider_config_invalid",
            retryable=False,
            details={"parameter": "model_dir"},
        )

    def download_models(self, params: dict[str, object]) -> dict[str, object]:
        return {}

    def ensure_started(self) -> dict[str, object]:
        return {}

    def launch_runtime_terminal(self) -> dict[str, object]:
        return {}

    def set_preferred_model(self, params: dict[str, object]) -> dict[str, object]:
        return {}

    def submit_job(self, params: dict[str, object]) -> dict[str, object]:
        return {"job_id": "job-1"}

    def get_job_status(self, params: dict[str, object]) -> dict[str, object]:
        return {"job_id": params["job_id"], "status": "queued"}


def test_protocol_error_includes_structure():
    worker = RelationGraphDesktopWorker(service=StubService())

    response = worker._handle_line('{"id":"req-1","method":"missing.method","params":{}}')

    assert response["id"] == "req-1"
    assert response["ok"] is False
    assert response["error"]["code"] == "protocol_error"
    assert response["error"]["retryable"] is False
    assert response["error"]["method"] == "missing.method"
    assert response["error"]["details"] == {}


def test_service_error_preserves_code_retryable_and_details():
    worker = RelationGraphDesktopWorker(service=StubService())

    response = worker._handle_line('{"id":"req-2","method":"provider.bindModelDir","params":{"model_dir":"E:/bad"}}')

    assert response["ok"] is False
    assert response["error"]["code"] == "provider_config_invalid"
    assert response["error"]["retryable"] is False
    assert response["error"]["method"] == "provider.bindModelDir"
    assert response["error"]["details"] == {"parameter": "model_dir"}


def test_shutdown_request_sets_shutdown_flag():
    service = StubService()
    worker = RelationGraphDesktopWorker(service=service)

    response = worker._handle_line('{"id":"req-3","method":"app.shutdown","params":{}}')

    assert response["ok"] is True
    assert response["shutdown"] is True
    assert response["method"] == "app.shutdown"
