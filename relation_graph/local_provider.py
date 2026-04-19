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

from relation_graph.ollama_client import OllamaClient, OllamaClientConfig, OllamaClientError
from relation_graph.settings import (
    LOCAL_CONTEXT_LENGTH,
    LOCAL_FALLBACK_MODEL_ID,
    LOCAL_MODEL_CANDIDATES,
    LOCAL_OLLAMA_BASE_URL,
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_PORT,
    LOCAL_OLLAMA_START_TIMEOUT_SECONDS,
    LOCAL_PRIMARY_MODEL_ID,
    LOCAL_PROVIDER_CONFIG_PATH,
    resolve_embedded_ollama_exe,
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


@dataclass(frozen=True)
class PortOwnerInfo:
    pid: int
    process_name: str | None = None
    process_path: str | None = None


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
        embedded_ollama_exe = resolve_embedded_ollama_exe()
        if self._process is not None and self._process.poll() is not None:
            self._process = None
            self._active_model_dir = None

        desired_models = set(LocalModelRegistry.list_model_names_from_disk(model_dir))
        runtime_models = self._list_models_if_ready()
        if runtime_models is not None:
            if not desired_models or desired_models.intersection(runtime_models):
                if self._active_model_dir is None:
                    self._active_model_dir = model_dir
                return None
            self.shutdown()
            stop_error = self._stop_conflicting_ollama_on_port()
            if stop_error:
                return stop_error
        elif self.is_port_open():
            stop_error = self._stop_conflicting_ollama_on_port()
            if stop_error:
                return stop_error

        env = os.environ.copy()
        env["OLLAMA_HOST"] = f"{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}"
        env["OLLAMA_MODELS"] = str(model_dir)
        env["OLLAMA_CONTEXT_LENGTH"] = str(LOCAL_CONTEXT_LENGTH)
        env.setdefault("OLLAMA_KEEP_ALIVE", "30m")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(
            [str(embedded_ollama_exe), "serve"],
            cwd=str(embedded_ollama_exe.parent),
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
        return "嵌入式 Ollama 启动超时，请检查Ollama目录和模型目录。"

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

    def _list_models_if_ready(self) -> set[str] | None:
        try:
            return {name.strip() for name in self.list_model_names() if name.strip()}
        except OllamaClientError:
            return None

    @staticmethod
    def is_port_open() -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((LOCAL_OLLAMA_HOST, LOCAL_OLLAMA_PORT)) == 0

    @staticmethod
    def _process_name_matches_ollama(info: PortOwnerInfo | None) -> bool:
        if info is None:
            return False
        name = (info.process_name or "").strip().lower()
        path = Path(info.process_path).name.lower() if info.process_path else ""
        return name == "ollama" or path == "ollama.exe"

    @staticmethod
    def _wait_until_port_closed(timeout_seconds: float = 5.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not EmbeddedOllamaRuntime.is_port_open():
                return True
            time.sleep(0.2)
        return not EmbeddedOllamaRuntime.is_port_open()

    @staticmethod
    def _find_port_owner() -> PortOwnerInfo | None:
        if os.name != "nt":
            return None
        script = f"""
$conn = Get-NetTCPConnection -LocalAddress '{LOCAL_OLLAMA_HOST}' -LocalPort {LOCAL_OLLAMA_PORT} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $conn) {{
  return
}}
$proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
[pscustomobject]@{{
  pid = [int]$conn.OwningProcess
  process_name = if ($proc) {{ $proc.ProcessName }} else {{ $null }}
  process_path = if ($proc) {{ $proc.Path }} else {{ $null }}
}} | ConvertTo-Json -Compress
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        payload = (result.stdout or "").strip()
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        pid = int(parsed.get("pid") or 0)
        if pid <= 0:
            return None
        process_name = str(parsed.get("process_name") or "").strip() or None
        process_path = str(parsed.get("process_path") or "").strip() or None
        return PortOwnerInfo(pid=pid, process_name=process_name, process_path=process_path)

    def _stop_conflicting_ollama_on_port(self) -> str | None:
        info = self._find_port_owner()
        if info is None:
            if self.is_port_open():
                return f"本地推理端口 {LOCAL_OLLAMA_PORT} 已被其他程序占用，无法启动嵌入式 Ollama。"
            return None
        if not self._process_name_matches_ollama(info):
            process_label = info.process_name or f"PID {info.pid}"
            return f"本地推理端口 {LOCAL_OLLAMA_PORT} 当前被 {process_label} 占用，无法自动切换到当前项目的本地引擎。"

        if self._process is not None and self._process.poll() is None and self._process.pid == info.pid:
            self.shutdown()
        else:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Stop-Process -Id {info.pid} -Force"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        if self._wait_until_port_closed():
            return None
        return f"本地推理端口 {LOCAL_OLLAMA_PORT} 上的 ollama.exe 未能成功关闭，请手动结束该进程后重试。"

    @staticmethod
    def quote_ps(value: str) -> str:
        return value.replace("'", "''")

    def _base_terminal_script(self, model_dir: Path) -> tuple[Path, str]:
        embedded_ollama_exe = resolve_embedded_ollama_exe()
        model_dir_text = self.quote_ps(str(model_dir))
        runtime_dir_text = self.quote_ps(str(embedded_ollama_exe.parent))
        host_text = self.quote_ps(f"{LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT}")
        script = f"""
$env:OLLAMA_MODELS = '{model_dir_text}'
$env:OLLAMA_HOST = '{host_text}'
$env:OLLAMA_CONTEXT_LENGTH = '{LOCAL_CONTEXT_LENGTH}'
$env:OLLAMA_KEEP_ALIVE = '30m'
Set-Location '{runtime_dir_text}'
"""
        return embedded_ollama_exe.parent, script

    @staticmethod
    def _launch_powershell_terminal(runtime_dir: Path, script: str) -> None:
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", script],
            cwd=str(runtime_dir),
            creationflags=creationflags,
        )

    def launch_download_terminal(self, model_dir: Path) -> None:
        runtime_dir, base_script = self._base_terminal_script(model_dir)
        model_dir_text = self.quote_ps(str(model_dir))
        script = base_script + f"""
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
        self._launch_powershell_terminal(runtime_dir, script)

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
            requested_provider in {"auto", "local"}
            and local_status.get("local_runtime_status") in {LocalRuntimeStatus.STOPPED.value, LocalRuntimeStatus.FAILED.value}
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

    def select_existing_model_dir(self, model_dir: str | Path) -> dict[str, object]:
        path = self._normalize_model_dir(model_dir)
        if not path.exists() or not path.is_dir():
            raise RuntimeError("所选路径无效，请重新选择目录。")
        self._config_store.save(model_dir=path)
        return self.get_public_status(auto_start=True)

    def download_models_and_configure(self, model_dir: str | Path) -> dict[str, object]:
        if os.name != "nt":
            raise RuntimeError("下载模型并配置目录仅在 Windows 首发版本中提供。")
        embedded_ollama_exe = resolve_embedded_ollama_exe()
        if not embedded_ollama_exe.exists():
            raise RuntimeError(f"未找到嵌入式 Ollama，请将 ollama.exe 放入 {embedded_ollama_exe.parent}。")

        path = self._normalize_model_dir(model_dir)
        path.mkdir(parents=True, exist_ok=True)
        self._config_store.save(model_dir=path)

        with self._lock:
            start_error = self._ensure_runtime_started_locked(path)
            if start_error:
                raise RuntimeError(start_error)
            self._runtime.launch_download_terminal(path)

        status = self.get_public_status(auto_start=False)
        status["detail"] = (
            f"已打开下载终端，正在向 {path} 下载 {LOCAL_PRIMARY_MODEL_ID} 和 {LOCAL_FALLBACK_MODEL_ID}。"
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

    @staticmethod
    def _runtime_model_mismatch_detail(model_dir: Path, disk_models: list[str]) -> str:
        models_text = " / ".join(disk_models) if disk_models else "白名单模型"
        return (
            f"已在 {model_dir} 识别到本地模型 {models_text}，"
            f"但当前 {LOCAL_OLLAMA_HOST}:{LOCAL_OLLAMA_PORT} 上运行的 Ollama 未暴露这些模型。"
            " 通常是旧的或其他项目启动的 Ollama 进程占用了该端口，"
            "或服务启动时没有绑定这个模型目录。请先关闭已有 ollama.exe，应用会继续自动检测当前项目的本地引擎状态。"
        )

    def _build_model_dir_not_configured_status(self, preferred_model: str) -> LocalProviderStatus:
        available_models: list[str] = []
        runtime_ready = self._runtime.is_ready()
        if runtime_ready:
            try:
                runtime_models = self._list_model_names_locked()
            except OllamaClientError:
                runtime_ready = False
            else:
                normalized_runtime_models = {name.strip() for name in runtime_models}
                available_models = [candidate for candidate in LOCAL_MODEL_CANDIDATES if candidate in normalized_runtime_models]

        if runtime_ready:
            if available_models:
                detail = (
                    f"已检测到嵌入式 Ollama 运行中，当前可用模型为 {' / '.join(available_models)}。"
                    " 但尚未配置本地模型目录，请先下载模型并配置目录，或绑定已有模型目录。"
                )
            else:
                detail = (
                    "已检测到嵌入式 Ollama 运行中，但当前未识别到白名单模型。"
                    f" 请先下载或放入 {' / '.join(LOCAL_MODEL_CANDIDATES)}，再绑定对应模型目录。"
                )
        elif self._is_port_open():
            detail = (
                f"已检测到本地推理端口 {LOCAL_OLLAMA_PORT} 被占用，但尚未配置本地模型目录。"
                " 请先下载模型并配置目录，或绑定已有模型目录。"
            )
        else:
            detail = "尚未配置本地模型目录；应用会继续自动检测嵌入式 Ollama。请先下载模型并配置目录，或绑定已有模型目录。"

        return self._build_status(
            runtime_status=LocalRuntimeStatus.NOT_CONFIGURED,
            detail=detail,
            model_dir=None,
            preferred_model=preferred_model,
            available_models=available_models,
        )

    def _build_runtime_waiting_status(
        self,
        *,
        model_dir: Path,
        preferred_model: str,
        disk_models: list[str],
        chosen_disk_model: str | None,
    ) -> LocalProviderStatus:
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
                detail=f"本地模型目录已配置，当前正在等待 Ollama 就绪；应用会自动持续检测，检测到后将使用 {chosen_disk_model}。",
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

        embedded_ollama_exe = resolve_embedded_ollama_exe()
        if not embedded_ollama_exe.exists():
            return self._build_status(
                runtime_status=LocalRuntimeStatus.NOT_CONFIGURED,
                detail=f"未找到嵌入式 Ollama，请将 ollama.exe 放入 {embedded_ollama_exe.parent}。",
                model_dir=self._config_store.load_model_dir(),
                preferred_model=preferred_model,
                available_models=[],
            )

        model_dir = self._config_store.load_model_dir()
        if model_dir is None:
            return self._build_model_dir_not_configured_status(preferred_model)
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
            return self._build_runtime_waiting_status(
                model_dir=model_dir,
                preferred_model=preferred_model,
                disk_models=disk_models,
                chosen_disk_model=chosen_disk_model,
            )

        try:
            model_names = self._list_model_names_locked()
        except OllamaClientError:
            return self._build_runtime_waiting_status(
                model_dir=model_dir,
                preferred_model=preferred_model,
                disk_models=disk_models,
                chosen_disk_model=chosen_disk_model,
            )

        normalized_runtime_models = {name.strip() for name in model_names}
        available_models = [candidate for candidate in LOCAL_MODEL_CANDIDATES if candidate in normalized_runtime_models]
        chosen_model = self._choose_model_name(available_models, preferred_model)
        if chosen_model is None:
            if chosen_disk_model is not None:
                return self._build_status(
                    runtime_status=LocalRuntimeStatus.FAILED,
                    detail=self._runtime_model_mismatch_detail(model_dir, disk_models),
                    model_dir=model_dir,
                    preferred_model=preferred_model,
                    available_models=disk_models,
                )
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
    def _normalize_model_dir(model_dir: str | Path) -> Path:
        raw_value = str(model_dir or "").strip()
        if not raw_value:
            raise RuntimeError("未选择目录。")
        return Path(raw_value)

