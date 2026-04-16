from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from relation_graph.desktop_service import RelationGraphDesktopService, ServiceDependencies, DesktopServiceError
from relation_graph.desktop_worker import RelationGraphDesktopWorker


@dataclass
class _DummyBatch:
    sources: list[str]
    temp_dir: Path | None = None
    total_bytes: int = 10


class _LocalProviderStub:
    def __init__(self):
        self.resolve_result = type(
            "Selection",
            (),
            {
                "provider_mode": "local",
                "model": "qwen3.5:9b",
                "api_key": "",
                "detail": "本地模型已就绪。",
            },
        )()
        self.status_payload = {
            "provider_mode": "ark",
            "local_runtime_status": "stopped",
            "local_model_name": None,
            "local_model_dir": "models",
            "detail": "stopped",
            "preferred_local_model": "qwen3.5:9b",
            "available_local_models": ["qwen3.5:9b"],
            "local_model_candidates": ["qwen3.5:9b", "qwen3.5:4b"],
        }
        self.captured: dict[str, object] = {}

    def get_public_status(self, *, auto_start=False):
        self.captured["auto_start"] = auto_start
        return dict(self.status_payload)

    def resolve_for_generation(self, **kwargs):
        self.captured.update(kwargs)
        return self.resolve_result

    def select_existing_model_dir(self, model_dir: str):
        self.captured["model_dir"] = model_dir
        return dict(self.status_payload)

    def download_models_and_configure(self, model_dir: str):
        self.captured["download_model_dir"] = model_dir
        return dict(self.status_payload)

    def ensure_started(self):
        payload = dict(self.status_payload)
        payload["local_runtime_status"] = "ready"
        return payload

    def launch_runtime_terminal(self):
        payload = dict(self.status_payload)
        payload["detail"] = "已打开本地引擎终端。"
        self.captured["launch_runtime_terminal"] = True
        return payload

    def set_preferred_model(self, model_name: str):
        self.captured["model_name"] = model_name
        payload = dict(self.status_payload)
        payload["preferred_local_model"] = model_name
        return payload

    def shutdown(self):
        self.captured["shutdown"] = True


class _JobManagerStub:
    def __init__(self):
        self.captured: dict[str, object] = {}

    def submit_job(self, **kwargs):
        self.captured.update(kwargs)
        return {
            "job_id": "job-local",
            "status": "queued",
            "provider_mode": kwargs["provider_mode"],
        }

    def get_public_job(self, job_id: str):
        if job_id != "job-local":
            raise KeyError(job_id)
        return {
            "job_id": job_id,
            "status": "queued",
            "provider_mode": "local",
            "detail": "任务排队中",
        }

    def shutdown(self):
        self.captured["shutdown"] = True


def _build_service() -> tuple[RelationGraphDesktopService, _LocalProviderStub, _JobManagerStub]:
    local_provider = _LocalProviderStub()
    job_manager = _JobManagerStub()
    service = RelationGraphDesktopService(
        ServiceDependencies(
            job_manager=job_manager,
            local_provider_manager=local_provider,
        )
    )
    service.start()
    return service, local_provider, job_manager


def test_submit_job_prefers_local_without_api_key(monkeypatch):
    service, _, job_manager = _build_service()
    monkeypatch.setattr(
        "relation_graph.desktop_service.save_selected_files",
        lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]),
    )

    response = service.submit_job(
        {
            "api_key": "",
            "model": "doubao-seed-1-8-251228",
            "provider_preference": "local",
            "files": ["E:/demo.txt"],
        }
    )

    assert response["provider_mode"] == "local"
    assert job_manager.captured["provider_mode"] == "local"
    assert "status_url" not in response
    service.shutdown()


def test_submit_job_delegates_provider_resolution_to_manager(monkeypatch):
    service, local_provider, _ = _build_service()
    monkeypatch.setattr(
        "relation_graph.desktop_service.save_selected_files",
        lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]),
    )

    response = service.submit_job(
        {
            "api_key": "",
            "model": "doubao-seed-1-8-251228",
            "provider_preference": "local",
            "files": ["E:/demo.txt"],
        }
    )

    assert response["provider_mode"] == "local"
    assert local_provider.captured["provider_preference"] == "local"
    assert local_provider.captured["ark_model"] == "doubao-seed-1-8-251228"
    service.shutdown()


def test_get_provider_status_is_read_only():
    service, local_provider, _ = _build_service()

    response = service.get_provider_status()

    assert response["local_runtime_status"] == "stopped"
    assert local_provider.captured["auto_start"] is False
    service.shutdown()


def test_worker_returns_structured_protocol_error():
    worker = RelationGraphDesktopWorker(service=RelationGraphDesktopService(ServiceDependencies(_JobManagerStub(), _LocalProviderStub())))
    response = worker._handle_line(json.dumps({"id": "1", "method": "unknown.method", "params": {}}))

    assert response["ok"] is False
    assert response["error"]["code"] == "protocol_error"


def test_worker_routes_job_status():
    service, _, _ = _build_service()
    worker = RelationGraphDesktopWorker(service=service)

    response = worker._handle_line(json.dumps({"id": "1", "method": "job.getStatus", "params": {"job_id": "job-local"}}))

    assert response["ok"] is True
    assert response["result"]["job_id"] == "job-local"
    service.shutdown()


def test_service_raises_structured_error_for_missing_job():
    service, _, _ = _build_service()

    with pytest.raises(DesktopServiceError, match="任务不存在"):
        service.get_job_status({"job_id": "missing"})

    service.shutdown()


def test_launch_runtime_terminal_routes_to_local_provider():
    service, local_provider, _ = _build_service()

    response = service.launch_runtime_terminal()

    assert response["detail"] == "已打开本地引擎终端。"
    assert local_provider.captured["launch_runtime_terminal"] is True
    service.shutdown()
