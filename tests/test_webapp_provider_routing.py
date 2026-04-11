from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_graph import webapp


@dataclass
class _DummyBatch:
    sources: list[str]


def test_generate_prefers_local_without_api_key(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        webapp.local_provider_manager,
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
    monkeypatch.setattr(webapp, "save_uploaded_files", lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]))
    monkeypatch.setattr(webapp, "cleanup_saved_upload_batch", lambda batch: None)
    monkeypatch.setattr(
        webapp.job_manager,
        "submit_job",
        lambda **kwargs: {
            "job_id": "job-local",
            "status": "queued",
            "status_url": "/jobs/job-local",
            "provider_mode": kwargs["provider_mode"],
        },
    )

    client = TestClient(webapp.app)
    response = client.post(
        "/generate",
        data={"api_key": "", "model": "doubao-seed-1-8-251228", "provider_preference": "local"},
        files={"files": ("demo.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["provider_mode"] == "local"


def test_generate_falls_back_to_ark_when_local_missing_and_api_key_present(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        webapp.local_provider_manager,
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
    monkeypatch.setattr(webapp, "save_uploaded_files", lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]))
    monkeypatch.setattr(webapp, "cleanup_saved_upload_batch", lambda batch: None)
    monkeypatch.setattr(
        webapp.job_manager,
        "submit_job",
        lambda **kwargs: {
            "job_id": "job-ark",
            "status": "queued",
            "status_url": "/jobs/job-ark",
            "provider_mode": kwargs["provider_mode"],
        },
    )

    client = TestClient(webapp.app)
    response = client.post(
        "/generate",
        data={"api_key": "demo-key", "model": "doubao-seed-1-8-251228", "provider_preference": "ark"},
        files={"files": ("demo.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["provider_mode"] == "ark"


def test_generate_delegates_provider_resolution_to_manager(monkeypatch, tmp_path: Path):
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

    monkeypatch.setattr(webapp.local_provider_manager, "resolve_for_generation", fake_resolve_for_generation)
    monkeypatch.setattr(webapp, "save_uploaded_files", lambda files, max_total_bytes=None: _DummyBatch(sources=["demo"]))
    monkeypatch.setattr(webapp, "cleanup_saved_upload_batch", lambda batch: None)
    monkeypatch.setattr(
        webapp.job_manager,
        "submit_job",
        lambda **kwargs: {
            "job_id": "job-local",
            "status": "queued",
            "status_url": "/jobs/job-local",
            "provider_mode": kwargs["provider_mode"],
        },
    )

    client = TestClient(webapp.app)
    response = client.post(
        "/generate",
        data={"api_key": "", "model": "doubao-seed-1-8-251228", "provider_preference": "local"},
        files={"files": ("demo.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 202
    assert response.json()["provider_mode"] == "local"
    assert captured["provider_preference"] == "local"
    assert captured["ark_model"] == "doubao-seed-1-8-251228"
