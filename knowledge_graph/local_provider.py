from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from knowledge_graph.ollama_client import OllamaClient, OllamaClientConfig, OllamaClientError
from knowledge_graph.settings import (
    EMBEDDED_OLLAMA_EXE,
    LOCAL_FALLBACK_MODEL_ID,
    LOCAL_MODEL_CANDIDATES,
    LOCAL_OLLAMA_BASE_URL,
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_PORT,
    LOCAL_OLLAMA_START_TIMEOUT_SECONDS,
    LOCAL_PRIMARY_MODEL_ID,
    LOCAL_PROVIDER_CONFIG_PATH,
)


class LocalRuntimeStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    MISSING_MODEL = "missing_model"
    FAILED = "failed"


@dataclass(frozen=True)
class LocalProviderStatus:
    provider_mode: str
    local_runtime_status: str
    local_model_name: str | None
    local_model_dir: str | None
    detail: str
    preferred_local_model: str | None
    available_local_models: list[str]
    local_model_candidates: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderSelection:
    provider_mode: str
    model: str
    api_key: str
    detail: str


def choose_generation_target(
    local_status: dict,
    *,
    api_key: str,
    ark_model: str,
    provider_preference: str = "auto",
) -> ProviderSelection:
    requested = (provider_preference or "auto").strip().lower()
    local_runtime_status = str(local_status.get("local_runtime_status") or "")
    local_model_name = str(local_status.get("local_model_name") or "").strip()
    detail = str(local_status.get("detail") or "").strip()

    if requested == "local":
        if local_runtime_status == LocalRuntimeStatus.READY.value and local_model_name:
            return ProviderSelection(
                provider_mode="local",
                model=local_model_name,
                api_key="",
                detail="当前已切换到本地模式，本次任务将使用本地模型。",
            )
        raise ValueError(f"{detail or '本地模型暂不可用。'} 当前已切换到本地模式，请先完成本地模型配置。")

    if requested == "ark":
        if not api_key.strip():
            raise ValueError("当前已切换到云端模式，请填写火山方舟 API Key。")
        return ProviderSelection(
            provider_mode="ark",
            model=ark_model.strip(),
            api_key=api_key.strip(),
            detail="当前已切换到云端模式，本次任务将使用火山方舟。",
        )

    if local_runtime_status == LocalRuntimeStatus.READY.value and local_model_name:
        return ProviderSelection(
            provider_mode="local",
            model=local_model_name,
            api_key="",
            detail="检测到本地模型可用，本次任务将优先使用本地路线。",
        )
    if api_key.strip():
        fallback_detail = detail
        if fallback_detail:
            fallback_detail += " 已切换为火山方舟。"
        else:
            fallback_detail = "本地模型不可用，本次任务将使用火山方舟。"
        return ProviderSelection(
            provider_mode="ark",
            model=ark_model.strip(),
            api_key=api_key.strip(),
            detail=fallback_detail,
        )
    raise ValueError(f"{detail or '未检测到可用的本地模型。'} 如需立即生成，请填写火山方舟 API Key。")


class LocalProviderConfigStore:
    def __init__(self, path: Path):
        self._path = path

    def load(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, *, model_dir: Path | None = None, preferred_model: str | None = None) -> None:
        payload = self.load()
        if model_dir is not None:
            payload["model_dir"] = str(model_dir)
        if preferred_model is not None:
            payload["preferred_local_model"] = preferred_model
        elif "preferred_local_model" not in payload:
            payload["preferred_local_model"] = LOCAL_PRIMARY_MODEL_ID
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_model_dir(self) -> Path | None:
        model_dir = str(self.load().get("model_dir") or "").strip()
        return Path(model_dir) if model_dir else None

    def load_preferred_model(self) -> str:
        preferred = str(self.load().get("preferred_local_model") or "").strip()
        return preferred or LOCAL_PRIMARY_MODEL_ID


class LocalModelRegistry:
    @staticmethod
    def list_model_names_from_disk(model_dir: Path) -> list[str]:
        manifests_dir = model_dir / "manifests" / "registry.ollama.ai" / "library"
        if not manifests_dir.exists():
            return []
        model_names: list[str] = []
        for manifest_path in manifests_dir.rglob("*"):
            if not manifest_path.is_file():
                continue
            relative_parts = manifest_path.relative_to(manifests_dir).parts
            if len(relative_parts) < 2:
                continue
            model_names.append(":".join((relative_parts[-2], relative_parts[-1])))
        return sorted(set(model_names))

    @staticmethod
    def choose_model_name(available_models: list[str], preferred_model: str | None) -> str | None:
        available = {name.strip() for name in available_models if name.strip()}
        if preferred_model and preferred_model in available:
            return preferred_model
        for candidate in LOCAL_MODEL_CANDIDATES:
            if candidate in available:
                return candidate
        return None


class EmbeddedOllamaRuntime:
    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._active_model_dir: Path | None = None

    def shutdown(self) -> None:
        process = self._process
        self._process = None
        self._active_model_dir = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def ensure_started(self, model_dir: Path) -> str | None:
        if self._process is not None and self._process.poll() is not None:
            self._process = None
            self._active_model_dir = None

        if self.is_ready():
            if self._active_model_dir is None or self._active_model_dir == model_dir:
                return None
            self.shutdown()
        if self.is_port_open():
            return f"本地推理端口 {LOCAL_OLLAMA_PORT} 已被其他程序占用，无法启动嵌入式 Ollama。"

        env = os.environ.copy()
        env["OLLAMA_HOST"] = f"{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}"
        env["OLLAMA_MODELS"] = str(model_dir)
        env.setdefault("OLLAMA_KEEP_ALIVE", "30m")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(
            [str(EMBEDDED_OLLAMA_EXE), "serve"],
            cwd=str(EMBEDDED_OLLAMA_EXE.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self._active_model_dir = model_dir

        deadline = time.time() + LOCAL_OLLAMA_START_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._process.poll() is not None:
                code = self._process.returncode
                self._process = None
                self._active_model_dir = None
                return f"嵌入式 Ollama 启动失败，退出码 {code}。"
            if self.is_ready():
                return None
            time.sleep(0.5)
        return "嵌入式 Ollama 启动超时，请检查运行时和模型目录。"

    def is_ready(self) -> bool:
        try:
            with OllamaClient(
                OllamaClientConfig(
                    base_url=LOCAL_OLLAMA_BASE_URL,
                    timeout=2,
                    retry_count=0,
                    parse_retry_count=0,
                )
            ) as client:
                return client.health_check()
        except OllamaClientError:
            return False

    def list_model_names(self) -> list[str]:
        with OllamaClient(
            OllamaClientConfig(
                base_url=LOCAL_OLLAMA_BASE_URL,
                timeout=3,
                retry_count=0,
                parse_retry_count=0,
            )
        ) as client:
            return client.list_models()

    @staticmethod
    def is_port_open() -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((LOCAL_OLLAMA_HOST, LOCAL_OLLAMA_PORT)) == 0

    @staticmethod
    def quote_ps(value: str) -> str:
        return value.replace("'", "''")

    def launch_download_terminal(self, model_dir: Path) -> None:
        model_dir_text = self.quote_ps(str(model_dir))
        runtime_dir_text = self.quote_ps(str(EMBEDDED_OLLAMA_EXE.parent))
        host_text = self.quote_ps(f"{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}")
        script = f"""
$env:OLLAMA_MODELS = '{model_dir_text}'
$env:OLLAMA_HOST = '{host_text}'
Set-Location '{runtime_dir_text}'
Write-Host '模型下载目录: {model_dir_text}'
Write-Host '将依次下载: {LOCAL_PRIMARY_MODEL_ID}, {LOCAL_FALLBACK_MODEL_ID}'
& .\\ollama.exe pull {LOCAL_PRIMARY_MODEL_ID}
if ($LASTEXITCODE -ne 0) {{
  Write-Host ''
  Write-Host '主模型下载失败，请检查网络或目录权限。'
  Read-Host '按回车关闭窗口'
  exit $LASTEXITCODE
}}
& .\\ollama.exe pull {LOCAL_FALLBACK_MODEL_ID}
if ($LASTEXITCODE -ne 0) {{
  Write-Host ''
  Write-Host '回退模型下载失败，请检查网络或目录权限。'
  Read-Host '按回车关闭窗口'
  exit $LASTEXITCODE
}}
Write-Host ''
Write-Host '模型下载完成，可以回到项目页面继续使用。'
Read-Host '按回车关闭窗口'
"""
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", script],
            cwd=str(EMBEDDED_OLLAMA_EXE.parent),
            creationflags=creationflags,
        )


class LocalProviderManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._config_store = LocalProviderConfigStore(LOCAL_PROVIDER_CONFIG_PATH)
        self._runtime = EmbeddedOllamaRuntime()

    def shutdown(self) -> None:
        with self._lock:
            self._runtime.shutdown()

    def resolve_for_generation(
        self,
        *,
        api_key: str,
        ark_model: str,
        provider_preference: str = "auto",
    ) -> ProviderSelection:
        local_status = self.get_public_status(auto_start=False)
        requested_provider = (provider_preference or "auto").strip().lower()
        should_try_local_start = (
            requested_provider in {"auto", "local"} and local_status.get("local_runtime_status") == LocalRuntimeStatus.STOPPED.value
        )
        if should_try_local_start:
            try:
                local_status = self.ensure_started()
            except RuntimeError:
                local_status = self.get_public_status(auto_start=False)
        return choose_generation_target(
            local_status,
            api_key=api_key,
            ark_model=ark_model,
            provider_preference=provider_preference,
        )

    def select_existing_model_dir(self) -> dict[str, object]:
        path = self._select_directory("选择已有本地模型目录", show_new_folder_button=False)
        self._config_store.save(model_dir=path)
        return self.get_public_status(auto_start=False)

    def download_models_and_configure(self) -> dict[str, object]:
        if os.name != "nt":
            raise RuntimeError("下载模型并配置目录仅在 Windows 首发版本中提供。")
        if not EMBEDDED_OLLAMA_EXE.exists():
            raise RuntimeError(f"未找到嵌入式 Ollama 运行时，请将 ollama.exe 放入 {EMBEDDED_OLLAMA_EXE.parent}。")

        model_dir = self._select_directory("选择模型下载目录", show_new_folder_button=True)
        model_dir.mkdir(parents=True, exist_ok=True)
        self._config_store.save(model_dir=model_dir)

        with self._lock:
            start_error = self._ensure_runtime_started_locked(model_dir)
            if start_error:
                raise RuntimeError(start_error)
            self._runtime.launch_download_terminal(model_dir)

        status = self.get_public_status(auto_start=False)
        status["detail"] = (
            f"已打开下载终端，正在向 {model_dir} 下载 {LOCAL_PRIMARY_MODEL_ID} 和 {LOCAL_FALLBACK_MODEL_ID}。"
            " 下载完成后，本地状态会自动刷新。"
        )
        return status

    def ensure_started(self) -> dict[str, object]:
        with self._lock:
            status = self._get_public_status_locked(auto_start=False)
            model_dir = self._config_store.load_model_dir()
            if status.local_runtime_status == LocalRuntimeStatus.READY.value:
                return status.to_dict()
            if model_dir is None:
                raise RuntimeError(status.detail)
            if status.local_runtime_status not in {
                LocalRuntimeStatus.STOPPED.value,
                LocalRuntimeStatus.MISSING_MODEL.value,
            }:
                raise RuntimeError(status.detail)
            if status.local_runtime_status == LocalRuntimeStatus.MISSING_MODEL.value:
                raise RuntimeError(status.detail)
            start_error = self._ensure_runtime_started_locked(model_dir)
            if start_error:
                raise RuntimeError(start_error)
            return self._get_public_status_locked(auto_start=False).to_dict()

    def set_preferred_model(self, model_name: str) -> dict[str, object]:
        normalized = (model_name or "").strip()
        if normalized not in LOCAL_MODEL_CANDIDATES:
            allowed = " / ".join(LOCAL_MODEL_CANDIDATES)
            raise RuntimeError(f"仅支持切换到白名单模型：{allowed}")
        self._config_store.save(preferred_model=normalized)
        return self.get_public_status(auto_start=False)

    def get_public_status(self, *, auto_start: bool = False) -> dict[str, object]:
        with self._lock:
            return self._get_public_status_locked(auto_start=auto_start).to_dict()

    def _build_status(
        self,
        *,
        runtime_status: LocalRuntimeStatus,
        detail: str,
        model_dir: Path | None,
        preferred_model: str,
        available_models: list[str],
        local_model_name: str | None = None,
        provider_mode: str | None = None,
    ) -> LocalProviderStatus:
        return LocalProviderStatus(
            provider_mode=provider_mode or ("local" if runtime_status == LocalRuntimeStatus.READY else "ark"),
            local_runtime_status=runtime_status.value,
            local_model_name=local_model_name,
            local_model_dir=str(model_dir) if model_dir else None,
            detail=detail,
            preferred_local_model=preferred_model,
            available_local_models=available_models,
            local_model_candidates=list(LOCAL_MODEL_CANDIDATES),
        )

    def _get_public_status_locked(self, *, auto_start: bool) -> LocalProviderStatus:
        preferred_model = self._config_store.load_preferred_model()

        if os.name != "nt":
            return self._build_status(
                runtime_status=LocalRuntimeStatus.FAILED,
                detail="本地路线首发仅支持 Windows。",
                model_dir=None,
                preferred_model=preferred_model,
                available_models=[],
            )

        if not EMBEDDED_OLLAMA_EXE.exists():
            return self._build_status(
                runtime_status=LocalRuntimeStatus.NOT_CONFIGURED,
                detail=f"未找到嵌入式 Ollama 运行时，请将 ollama.exe 放入 {EMBEDDED_OLLAMA_EXE.parent}。",
                model_dir=self._config_store.load_model_dir(),
                preferred_model=preferred_model,
                available_models=[],
            )

        model_dir = self._config_store.load_model_dir()
        if model_dir is None:
            return self._build_status(
                runtime_status=LocalRuntimeStatus.NOT_CONFIGURED,
                detail="尚未配置本地模型目录，请先下载模型并配置目录，或绑定已有模型目录。",
                model_dir=None,
                preferred_model=preferred_model,
                available_models=[],
            )
        if not model_dir.exists() or not model_dir.is_dir():
            return self._build_status(
                runtime_status=LocalRuntimeStatus.NOT_CONFIGURED,
                detail="已保存的本地模型目录不存在，请重新配置目录。",
                model_dir=model_dir,
                preferred_model=preferred_model,
                available_models=[],
            )

        disk_models = self._list_model_names_from_disk(model_dir)
        chosen_disk_model = self._choose_model_name(disk_models, preferred_model)

        if auto_start:
            start_error = self._ensure_runtime_started_locked(model_dir)
            if start_error:
                return self._build_status(
                    runtime_status=LocalRuntimeStatus.FAILED,
                    detail=start_error,
                    model_dir=model_dir,
                    preferred_model=preferred_model,
                    available_models=disk_models,
                )
        elif not self._runtime.is_ready():
            if self._is_port_open():
                return self._build_status(
                    runtime_status=LocalRuntimeStatus.FAILED,
                    detail=f"本地推理端口 {LOCAL_OLLAMA_PORT} 已被其他程序占用或运行时未就绪。",
                    model_dir=model_dir,
                    preferred_model=preferred_model,
                    available_models=disk_models,
                )
            if chosen_disk_model is not None:
                return self._build_status(
                    runtime_status=LocalRuntimeStatus.STOPPED,
                    detail=f"本地模型目录已配置，运行时当前未启动。可手动启动后使用 {chosen_disk_model}。",
                    model_dir=model_dir,
                    preferred_model=preferred_model,
                    available_models=disk_models,
                )
            return self._build_status(
                runtime_status=LocalRuntimeStatus.MISSING_MODEL,
                detail=f"当前目录尚未识别到白名单模型，请下载或放入 {' / '.join(LOCAL_MODEL_CANDIDATES)}。",
                model_dir=model_dir,
                preferred_model=preferred_model,
                available_models=disk_models,
            )

        try:
            model_names = self._list_model_names_locked()
        except OllamaClientError:
            if self._is_port_open():
                return self._build_status(
                    runtime_status=LocalRuntimeStatus.FAILED,
                    detail=f"本地推理端口 {LOCAL_OLLAMA_PORT} 已被其他程序占用或运行时未就绪。",
                    model_dir=model_dir,
                    preferred_model=preferred_model,
                    available_models=disk_models,
                )
            if chosen_disk_model is not None:
                return self._build_status(
                    runtime_status=LocalRuntimeStatus.STOPPED,
                    detail=f"本地模型目录已配置，运行时当前未启动。可手动启动后使用 {chosen_disk_model}。",
                    model_dir=model_dir,
                    preferred_model=preferred_model,
                    available_models=disk_models,
                )
            return self._build_status(
                runtime_status=LocalRuntimeStatus.MISSING_MODEL,
                detail=f"当前目录尚未识别到白名单模型，请下载或放入 {' / '.join(LOCAL_MODEL_CANDIDATES)}。",
                model_dir=model_dir,
                preferred_model=preferred_model,
                available_models=disk_models,
            )

        normalized_runtime_models = {name.strip() for name in model_names}
        available_models = [candidate for candidate in LOCAL_MODEL_CANDIDATES if candidate in normalized_runtime_models]
        chosen_model = self._choose_model_name(available_models, preferred_model)
        if chosen_model is None:
            return self._build_status(
                runtime_status=LocalRuntimeStatus.MISSING_MODEL,
                detail=f"当前目录尚未识别到白名单模型，请下载或放入 {' / '.join(LOCAL_MODEL_CANDIDATES)}。",
                model_dir=model_dir,
                preferred_model=preferred_model,
                available_models=available_models,
            )

        if preferred_model and preferred_model != chosen_model and preferred_model not in available_models:
            detail = f"偏好模型 {preferred_model} 暂不可用，已自动回退到 {chosen_model}。"
        else:
            detail = f"本地模型已就绪，当前使用 {chosen_model}。"

        return self._build_status(
            runtime_status=LocalRuntimeStatus.READY,
            detail=detail,
            model_dir=model_dir,
            preferred_model=preferred_model,
            available_models=available_models,
            local_model_name=chosen_model,
        )

    def _list_model_names_locked(self) -> list[str]:
        return self._runtime.list_model_names()

    @staticmethod
    def _list_model_names_from_disk(model_dir: Path) -> list[str]:
        return LocalModelRegistry.list_model_names_from_disk(model_dir)

    @staticmethod
    def _choose_model_name(available_models: list[str], preferred_model: str | None) -> str | None:
        return LocalModelRegistry.choose_model_name(available_models, preferred_model)

    def _ensure_runtime_started_locked(self, model_dir: Path) -> str | None:
        return self._runtime.ensure_started(model_dir)

    @staticmethod
    def _is_port_open() -> bool:
        return EmbeddedOllamaRuntime.is_port_open()

    @staticmethod
    def _select_directory(description: str, *, show_new_folder_button: bool) -> Path:
        if os.name != "nt":
            raise RuntimeError("目录选择仅在 Windows 首发版本中提供。")
        description_text = description.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$dialog.Description = '{description_text}'; "
            f"$dialog.ShowNewFolderButton = ${str(show_new_folder_button).lower()}; "
            "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
            "  Write-Output $dialog.SelectedPath "
            "}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        selected = (result.stdout or "").strip()
        if not selected:
            raise RuntimeError("未选择目录。")
        path = Path(selected)
        if path.exists() and not path.is_dir():
            raise RuntimeError("所选路径无效，请重新选择目录。")
        return path
