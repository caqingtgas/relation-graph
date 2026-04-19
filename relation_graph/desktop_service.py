from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from relation_graph.job_runtime import JobManager
from relation_graph.local_provider import LocalProviderManager
from relation_graph.pipeline.artifact_store import cleanup_saved_upload_batch, save_selected_files
from relation_graph.runtime_assets import ensure_runtime_assets
from relation_graph.settings import DEFAULT_ARK_MODEL_ID, MAX_FILES_PER_JOB, MAX_TOTAL_UPLOAD_BYTES


logger = logging.getLogger(__name__)


class DesktopServiceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "service_error",
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


@dataclass(frozen=True)
class ServiceDependencies:
    job_manager: JobManager
    local_provider_manager: LocalProviderManager


class RelationGraphDesktopService:
    def __init__(self, dependencies: ServiceDependencies | None = None):
        deps = dependencies or ServiceDependencies(
            job_manager=JobManager(),
            local_provider_manager=LocalProviderManager(),
        )
        self._job_manager = deps.job_manager
        self._local_provider_manager = deps.local_provider_manager
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        ensure_runtime_assets()
        self._started = True

    def shutdown(self) -> None:
        self._job_manager.shutdown()
        self._local_provider_manager.shutdown()
        self._started = False

    def get_provider_status(self, params: dict[str, Any] | None = None) -> dict[str, object]:
        auto_start = bool((params or {}).get("auto_start"))
        return self._local_provider_manager.get_public_status(auto_start=auto_start)

    def bind_model_dir(self, params: dict[str, Any]) -> dict[str, object]:
        model_dir = self._require_string(params, "model_dir")
        try:
            return self._local_provider_manager.select_existing_model_dir(model_dir)
        except RuntimeError as exc:
            raise DesktopServiceError(str(exc), code="provider_config_invalid") from exc
        except Exception as exc:
            logger.exception("绑定已有模型目录失败")
            raise DesktopServiceError("绑定已有模型目录失败，请稍后重试。", code="provider_bind_failed", retryable=True) from exc

    def download_models(self, params: dict[str, Any]) -> dict[str, object]:
        model_dir = self._require_string(params, "model_dir")
        try:
            return self._local_provider_manager.download_models_and_configure(model_dir)
        except RuntimeError as exc:
            raise DesktopServiceError(str(exc), code="provider_download_unavailable") from exc
        except Exception as exc:
            logger.exception("下载模型并配置目录失败")
            raise DesktopServiceError(
                "下载模型并配置目录失败，请稍后重试。",
                code="provider_download_failed",
                retryable=True,
            ) from exc

    def set_preferred_model(self, params: dict[str, Any]) -> dict[str, object]:
        model_name = self._require_string(params, "model_name")
        try:
            return self._local_provider_manager.set_preferred_model(model_name)
        except RuntimeError as exc:
            raise DesktopServiceError(str(exc), code="provider_model_invalid") from exc
        except Exception as exc:
            logger.exception("切换本地模型失败")
            raise DesktopServiceError("切换本地模型失败，请稍后重试。", code="provider_model_switch_failed", retryable=True) from exc

    def submit_job(self, params: dict[str, Any]) -> dict[str, Any]:
        files = self._require_string_list(params, "files")
        api_key = self._optional_string(params, "api_key")
        model = self._optional_string(params, "model") or DEFAULT_ARK_MODEL_ID
        provider_preference = self._optional_string(params, "provider_preference") or "auto"

        if not files:
            raise DesktopServiceError("请先上传文件。", code="job_files_required")
        if len(files) > MAX_FILES_PER_JOB:
            raise DesktopServiceError(
                f"单次最多上传 {MAX_FILES_PER_JOB} 个文件，请减少后重试。",
                code="job_too_many_files",
                details={"max_files": MAX_FILES_PER_JOB},
            )

        try:
            selection = self._local_provider_manager.resolve_for_generation(
                api_key=api_key,
                ark_model=model,
                provider_preference=provider_preference,
            )
        except ValueError as exc:
            raise DesktopServiceError(str(exc), code="job_provider_unavailable") from exc

        try:
            saved_batch = save_selected_files(files, max_total_bytes=MAX_TOTAL_UPLOAD_BYTES)
        except ValueError as exc:
            raise DesktopServiceError(str(exc), code="job_file_validation_failed") from exc
        except Exception as exc:
            logger.exception("读取已选文件失败")
            raise DesktopServiceError("读取已选文件失败，请稍后重试。", code="job_file_read_failed", retryable=True) from exc

        if not saved_batch.sources:
            cleanup_saved_upload_batch(saved_batch)
            raise DesktopServiceError("暂时只支持 pdf、txt、md 文件。", code="job_file_type_unsupported")

        try:
            result = self._job_manager.submit_job(
                upload_batch=saved_batch,
                provider_mode=selection.provider_mode,
                api_key=selection.api_key,
                model=selection.model,
            )
        except ValueError as exc:
            cleanup_saved_upload_batch(saved_batch)
            raise DesktopServiceError(str(exc), code="job_submit_invalid") from exc
        except Exception as exc:
            cleanup_saved_upload_batch(saved_batch)
            logger.exception("创建图谱任务失败")
            raise DesktopServiceError("图谱任务创建失败，请稍后重试。", code="job_submit_failed", retryable=True) from exc

        result["provider_mode"] = selection.provider_mode
        result["detail"] = selection.detail
        return result

    def get_job_status(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = self._require_string(params, "job_id")
        try:
            return self._job_manager.get_public_job(job_id)
        except KeyError as exc:
            raise DesktopServiceError("任务不存在。", code="job_not_found") from exc

    @staticmethod
    def _optional_string(params: dict[str, Any], key: str) -> str:
        value = params.get(key, "")
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _require_string(params: dict[str, Any], key: str) -> str:
        value = str(params.get(key) or "").strip()
        if not value:
            raise DesktopServiceError(f"缺少参数：{key}", code="missing_parameter", details={"parameter": key})
        return value

    @staticmethod
    def _require_string_list(params: dict[str, Any], key: str) -> list[str]:
        value = params.get(key)
        if not isinstance(value, list):
            raise DesktopServiceError(f"参数格式错误：{key}", code="invalid_parameter_type", details={"parameter": key})
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return normalized
