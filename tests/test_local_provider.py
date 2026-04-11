from __future__ import annotations

import json
from pathlib import Path

from knowledge_graph import local_provider


def test_choose_generation_target_prefers_local_ready():
    selection = local_provider.choose_generation_target(
        {
            "local_runtime_status": "ready",
            "local_model_name": "qwen3.5:9b",
            "detail": "本地模型已就绪。",
        },
        api_key="",
        ark_model="doubao-seed-1-8-251228",
        provider_preference="local",
    )

    assert selection.provider_mode == "local"
    assert selection.model == "qwen3.5:9b"
    assert selection.api_key == ""


def test_choose_generation_target_falls_back_to_ark():
    selection = local_provider.choose_generation_target(
        {
            "local_runtime_status": "missing_model",
            "detail": "未检测到本地模型。",
        },
        api_key="demo-key",
        ark_model="doubao-seed-1-8-251228",
        provider_preference="ark",
    )

    assert selection.provider_mode == "ark"
    assert selection.model == "doubao-seed-1-8-251228"
    assert selection.api_key == "demo-key"


def test_choose_generation_target_requires_api_key_when_local_unavailable():
    try:
        local_provider.choose_generation_target(
            {
                "local_runtime_status": "not_configured",
                "detail": "尚未配置本地模型目录。",
            },
            api_key="",
            ark_model="doubao-seed-1-8-251228",
            provider_preference="local",
        )
    except ValueError as exc:
        assert "当前已切换到本地模式" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_resolve_for_generation_attempts_start_when_local_stopped(monkeypatch):
    manager = local_provider.LocalProviderManager()
    calls = {"ensure_started": 0}

    monkeypatch.setattr(
        manager,
        "get_public_status",
        lambda auto_start=False: {
            "provider_mode": "ark",
            "local_runtime_status": "stopped",
            "local_model_name": None,
            "local_model_dir": "models",
            "detail": "本地模型目录已配置，运行时当前未启动。",
        },
    )

    def fake_ensure_started():
        calls["ensure_started"] += 1
        return {
            "provider_mode": "local",
            "local_runtime_status": "ready",
            "local_model_name": "qwen3.5:9b",
            "local_model_dir": "models",
            "detail": "本地模型已就绪。",
        }

    monkeypatch.setattr(manager, "ensure_started", fake_ensure_started)

    selection = manager.resolve_for_generation(
        api_key="",
        ark_model="doubao-seed-1-8-251228",
        provider_preference="local",
    )

    assert selection.provider_mode == "local"
    assert selection.model == "qwen3.5:9b"
    assert calls["ensure_started"] == 1


def test_resolve_for_generation_attempts_start_when_local_failed(monkeypatch):
    manager = local_provider.LocalProviderManager()
    calls = {"ensure_started": 0}

    monkeypatch.setattr(
        manager,
        "get_public_status",
        lambda auto_start=False: {
            "provider_mode": "ark",
            "local_runtime_status": "failed",
            "local_model_name": None,
            "local_model_dir": "models",
            "detail": "端口被其他 Ollama 占用。",
        },
    )

    def fake_ensure_started():
        calls["ensure_started"] += 1
        return {
            "provider_mode": "local",
            "local_runtime_status": "ready",
            "local_model_name": "qwen3.5:9b",
            "local_model_dir": "models",
            "detail": "本地模型已就绪。",
        }

    monkeypatch.setattr(manager, "ensure_started", fake_ensure_started)

    selection = manager.resolve_for_generation(
        api_key="",
        ark_model="doubao-seed-1-8-251228",
        provider_preference="local",
    )

    assert selection.provider_mode == "local"
    assert selection.model == "qwen3.5:9b"
    assert calls["ensure_started"] == 1


def test_local_provider_status_not_configured_without_embedded_runtime(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "local_provider.json"
    monkeypatch.setattr(local_provider, "LOCAL_PROVIDER_CONFIG_PATH", config_path)
    monkeypatch.setattr(local_provider, "EMBEDDED_OLLAMA_EXE", tmp_path / "missing" / "ollama.exe")

    manager = local_provider.LocalProviderManager()
    status = manager.get_public_status(auto_start=False)

    assert status["provider_mode"] == "ark"
    assert status["local_runtime_status"] == "not_configured"
    assert "嵌入式 Ollama" in str(status["detail"])
    assert status["preferred_local_model"] == "qwen3.5:9b"


def test_local_provider_status_missing_model_when_whitelist_not_found(tmp_path: Path, monkeypatch):
    embedded_dir = tmp_path / "embedded"
    embedded_dir.mkdir()
    embedded_exe = embedded_dir / "ollama.exe"
    embedded_exe.write_text("placeholder", encoding="utf-8")
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    config_path = tmp_path / "local_provider.json"
    config_path.write_text(json.dumps({"model_dir": str(model_dir)}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(local_provider, "EMBEDDED_OLLAMA_EXE", embedded_exe)
    monkeypatch.setattr(local_provider, "LOCAL_PROVIDER_CONFIG_PATH", config_path)
    monkeypatch.setattr(local_provider.LocalProviderManager, "_ensure_runtime_started_locked", lambda self, path: None)
    monkeypatch.setattr(local_provider.LocalProviderManager, "_list_model_names_locked", lambda self: ["other-model:1b"])

    manager = local_provider.LocalProviderManager()
    status = manager.get_public_status(auto_start=True)

    assert status["provider_mode"] == "ark"
    assert status["local_runtime_status"] == "missing_model"
    assert "qwen3.5:9b" in str(status["detail"])
    assert status["available_local_models"] == []


def test_local_provider_status_ready_prefers_primary_model(tmp_path: Path, monkeypatch):
    embedded_dir = tmp_path / "embedded"
    embedded_dir.mkdir()
    embedded_exe = embedded_dir / "ollama.exe"
    embedded_exe.write_text("placeholder", encoding="utf-8")
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    config_path = tmp_path / "local_provider.json"
    config_path.write_text(json.dumps({"model_dir": str(model_dir)}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(local_provider, "EMBEDDED_OLLAMA_EXE", embedded_exe)
    monkeypatch.setattr(local_provider, "LOCAL_PROVIDER_CONFIG_PATH", config_path)
    monkeypatch.setattr(local_provider.LocalProviderManager, "_ensure_runtime_started_locked", lambda self, path: None)
    monkeypatch.setattr(
        local_provider.LocalProviderManager,
        "_list_model_names_locked",
        lambda self: ["qwen3.5:4b", "qwen3.5:9b"],
    )

    manager = local_provider.LocalProviderManager()
    status = manager.get_public_status(auto_start=True)

    assert status["provider_mode"] == "local"
    assert status["local_runtime_status"] == "ready"
    assert status["local_model_name"] == "qwen3.5:9b"
    assert status["available_local_models"] == ["qwen3.5:9b", "qwen3.5:4b"]


def test_local_provider_status_stopped_when_models_exist_on_disk(tmp_path: Path, monkeypatch):
    embedded_dir = tmp_path / "embedded"
    embedded_dir.mkdir()
    embedded_exe = embedded_dir / "ollama.exe"
    embedded_exe.write_text("placeholder", encoding="utf-8")
    model_dir = tmp_path / "models"
    manifest_dir = model_dir / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "9b").write_text("manifest", encoding="utf-8")
    config_path = tmp_path / "local_provider.json"
    config_path.write_text(json.dumps({"model_dir": str(model_dir)}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(local_provider, "EMBEDDED_OLLAMA_EXE", embedded_exe)
    monkeypatch.setattr(local_provider, "LOCAL_PROVIDER_CONFIG_PATH", config_path)
    monkeypatch.setattr(local_provider.LocalProviderManager, "_list_model_names_locked", lambda self: (_ for _ in ()).throw(local_provider.OllamaClientError("offline")))
    monkeypatch.setattr(local_provider.LocalProviderManager, "_is_port_open", lambda self: False)

    manager = local_provider.LocalProviderManager()
    status = manager.get_public_status(auto_start=False)

    assert status["local_runtime_status"] == "stopped"
    assert status["available_local_models"] == ["qwen3.5:9b"]


def test_local_provider_status_reports_runtime_model_mismatch_when_disk_models_exist(tmp_path: Path, monkeypatch):
    embedded_dir = tmp_path / "embedded"
    embedded_dir.mkdir()
    embedded_exe = embedded_dir / "ollama.exe"
    embedded_exe.write_text("placeholder", encoding="utf-8")
    model_dir = tmp_path / "models"
    manifest_dir = model_dir / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "9b").write_text("manifest", encoding="utf-8")
    config_path = tmp_path / "local_provider.json"
    config_path.write_text(json.dumps({"model_dir": str(model_dir)}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(local_provider, "EMBEDDED_OLLAMA_EXE", embedded_exe)
    monkeypatch.setattr(local_provider, "LOCAL_PROVIDER_CONFIG_PATH", config_path)
    monkeypatch.setattr(local_provider.EmbeddedOllamaRuntime, "is_ready", lambda self: True)
    monkeypatch.setattr(local_provider.LocalProviderManager, "_list_model_names_locked", lambda self: [])

    manager = local_provider.LocalProviderManager()
    status = manager.get_public_status(auto_start=False)

    assert status["local_runtime_status"] == "failed"
    assert "未暴露这些模型" in str(status["detail"])
    assert status["available_local_models"] == ["qwen3.5:9b"]


def test_ensure_started_allows_restart_from_failed_status(monkeypatch):
    manager = local_provider.LocalProviderManager()
    states = [
        local_provider.LocalProviderStatus(
            provider_mode="ark",
            local_runtime_status="failed",
            local_model_name=None,
            local_model_dir="models",
            detail="端口上的 Ollama 与当前模型目录不匹配。",
            preferred_local_model="qwen3.5:9b",
            available_local_models=["qwen3.5:9b"],
            local_model_candidates=["qwen3.5:9b", "qwen3.5:4b"],
        ),
        local_provider.LocalProviderStatus(
            provider_mode="local",
            local_runtime_status="ready",
            local_model_name="qwen3.5:9b",
            local_model_dir="models",
            detail="本地模型已就绪。",
            preferred_local_model="qwen3.5:9b",
            available_local_models=["qwen3.5:9b"],
            local_model_candidates=["qwen3.5:9b", "qwen3.5:4b"],
        ),
    ]
    calls = {"start": 0}

    monkeypatch.setattr(manager._config_store, "load_model_dir", lambda: Path("models"))

    def fake_status(*, auto_start=False):
        return states.pop(0)

    monkeypatch.setattr(manager, "_get_public_status_locked", fake_status)

    def fake_start(model_dir):
        calls["start"] += 1
        return None

    monkeypatch.setattr(manager, "_ensure_runtime_started_locked", fake_start)

    status = manager.ensure_started()

    assert status["local_runtime_status"] == "ready"
    assert calls["start"] == 1


def test_stop_conflicting_ollama_on_port_stops_ollama_process(monkeypatch):
    runtime = local_provider.EmbeddedOllamaRuntime()
    calls = {"stop_process": 0}

    monkeypatch.setattr(
        runtime,
        "_find_port_owner",
        lambda: local_provider.PortOwnerInfo(pid=123, process_name="ollama", process_path=r"C:\demo\ollama.exe"),
    )
    monkeypatch.setattr(runtime, "_wait_until_port_closed", lambda timeout_seconds=5.0: True)

    def fake_run(*args, **kwargs):
        calls["stop_process"] += 1
        class _Result:
            stdout = ""
        return _Result()

    monkeypatch.setattr(local_provider.subprocess, "run", fake_run)

    assert runtime._stop_conflicting_ollama_on_port() is None
    assert calls["stop_process"] == 1
