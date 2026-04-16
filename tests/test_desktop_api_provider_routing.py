from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from relation_graph import desktop_api


@dataclass
class _DummyBatch:
    sources: list[str]
    temp_dir: Path | None = None
    total_bytes: int = 10


def test_submit_job_prefers_local_without_api_key(monkeypatch):
    monkeypatch.setattr(
        desktop_api.local_provider_manager,
        "resolve_for_generation",
        lambda **kwargs: type(
            "Selection",
            (),
            {
                "provider_mode": "local",
                "model": "qwen3.5:9b",
                "api_key": "",
                "detail": "本地模型已就绪。",
            },
        )(),
    )
    monkeypatch.setattr(desktop_api, "save_selected_files", lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]))
    monkeypatch.setattr(desktop_api, "cleanup_saved_upload_batch", lambda batch: None)
    monkeypatch.setattr(
        desktop_api.job_manager,
        "submit_job",
        lambda **kwargs: {
            "job_id": "job-local",
            "status": "queued",
            "status_url": "/jobs/job-local",
            "provider_mode": kwargs["provider_mode"],
        },
    )

    client = TestClient(desktop_api.app)
    response = client.post(
        "/jobs",
        json={"api_key": "", "model": "doubao-seed-1-8-251228", "provider_preference": "local", "files": ["E:/demo.txt"]},
    )

    assert response.status_code == 202
    assert response.json()["provider_mode"] == "local"


def test_submit_job_falls_back_to_ark_when_local_missing_and_api_key_present(monkeypatch):
    monkeypatch.setattr(
        desktop_api.local_provider_manager,
        "resolve_for_generation",
        lambda **kwargs: type(
            "Selection",
            (),
            {
                "provider_mode": "ark",
                "model": "doubao-seed-1-8-251228",
                "api_key": "demo-key",
                "detail": "未检测到本地模型。 已切换为火山方舟。",
            },
        )(),
    )
    monkeypatch.setattr(desktop_api, "save_selected_files", lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]))
    monkeypatch.setattr(desktop_api, "cleanup_saved_upload_batch", lambda batch: None)
    monkeypatch.setattr(
        desktop_api.job_manager,
        "submit_job",
        lambda **kwargs: {
            "job_id": "job-ark",
            "status": "queued",
            "status_url": "/jobs/job-ark",
            "provider_mode": kwargs["provider_mode"],
        },
    )

    client = TestClient(desktop_api.app)
    response = client.post(
        "/jobs",
        json={"api_key": "demo-key", "model": "doubao-seed-1-8-251228", "provider_preference": "ark", "files": ["E:/demo.txt"]},
    )

    assert response.status_code == 202
    assert response.json()["provider_mode"] == "ark"


def test_submit_job_delegates_provider_resolution_to_manager(monkeypatch):
    captured = {}

    def fake_resolve_for_generation(**kwargs):
        captured.update(kwargs)
        return type(
            "Selection",
            (),
            {
                "provider_mode": "local",
                "model": "qwen3.5:9b",
                "api_key": "",
                "detail": "本地模型已就绪。",
            },
        )()

    monkeypatch.setattr(desktop_api.local_provider_manager, "resolve_for_generation", fake_resolve_for_generation)
    monkeypatch.setattr(desktop_api, "save_selected_files", lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]))
    monkeypatch.setattr(desktop_api, "cleanup_saved_upload_batch", lambda batch: None)
    monkeypatch.setattr(
        desktop_api.job_manager,
        "submit_job",
        lambda **kwargs: {
            "job_id": "job-local",
            "status": "queued",
            "status_url": "/jobs/job-local",
            "provider_mode": kwargs["provider_mode"],
        },
    )

    client = TestClient(desktop_api.app)
    response = client.post(
        "/jobs",
        json={"api_key": "", "model": "doubao-seed-1-8-251228", "provider_preference": "local", "files": ["E:/demo.txt"]},
    )

    assert response.status_code == 202
    assert response.json()["provider_mode"] == "local"
    assert captured["provider_preference"] == "local"
    assert captured["ark_model"] == "doubao-seed-1-8-251228"
