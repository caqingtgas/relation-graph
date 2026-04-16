from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from relation_graph.job_runtime import JobManager
from relation_graph.local_provider import LocalProviderManager
from relation_graph.pipeline.artifact_store import cleanup_saved_upload_batch, save_selected_files
from relation_graph.runtime_assets import ensure_runtime_assets
from relation_graph.settings import DEFAULT_ARK_MODEL_ID, MAX_FILES_PER_JOB, MAX_TOTAL_UPLOAD_BYTES


logger = logging.getLogger(__name__)
job_manager = JobManager()
local_provider_manager = LocalProviderManager()


class ModelDirPayload(BaseModel):
    model_dir: str


class PreferredModelPayload(BaseModel):
    model_name: str


class SubmitJobPayload(BaseModel):
    api_key: str = ""
    model: str = DEFAULT_ARK_MODEL_ID
    provider_preference: str = "auto"
    files: list[str] = Field(default_factory=list)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_runtime_assets()
    try:
        yield
    finally:
        job_manager.shutdown()
        local_provider_manager.shutdown()


app = FastAPI(title="RelationGraph Desktop Backend", lifespan=lifespan)


@app.get("/health")
def health_check():
    return JSONResponse({"ok": True})


@app.get("/provider/status")
def get_provider_status():
    return JSONResponse(local_provider_manager.get_public_status(auto_start=False))


@app.post("/provider/bind-model-dir")
def bind_existing_model_dir(payload: ModelDirPayload):
    try:
        return JSONResponse(local_provider_manager.select_existing_model_dir(payload.model_dir))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("绑定已有模型目录失败")
        raise HTTPException(status_code=500, detail="绑定已有模型目录失败，请稍后重试。")


@app.post("/provider/download-models")
def download_models_and_configure(payload: ModelDirPayload):
    try:
        return JSONResponse(local_provider_manager.download_models_and_configure(payload.model_dir))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("下载模型并配置目录失败")
        raise HTTPException(status_code=500, detail="下载模型并配置目录失败，请稍后重试。")


@app.post("/provider/ensure-started")
def ensure_started_local_provider():
    try:
        return JSONResponse(local_provider_manager.ensure_started())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("启动本地模型失败")
        raise HTTPException(status_code=500, detail="启动本地模型失败，请稍后重试。")


@app.post("/provider/preferred-model")
def update_preferred_local_model(payload: PreferredModelPayload):
    try:
        return JSONResponse(local_provider_manager.set_preferred_model(payload.model_name))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("切换本地模型失败")
        raise HTTPException(status_code=500, detail="切换本地模型失败，请稍后重试。")


@app.post("/jobs")
def submit_job(payload: SubmitJobPayload):
    if not payload.files:
        raise HTTPException(status_code=400, detail="请先上传文件。")
    if len(payload.files) > MAX_FILES_PER_JOB:
        raise HTTPException(status_code=400, detail=f"单次最多上传 {MAX_FILES_PER_JOB} 个文件，请减少后重试。")

    try:
        selection = local_provider_manager.resolve_for_generation(
            api_key=payload.api_key,
            ark_model=payload.model or DEFAULT_ARK_MODEL_ID,
            provider_preference=payload.provider_preference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        saved_batch = save_selected_files(payload.files, max_total_bytes=MAX_TOTAL_UPLOAD_BYTES)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("读取已选文件失败")
        raise HTTPException(status_code=500, detail="读取已选文件失败，请稍后重试。")

    if not saved_batch.sources:
        raise HTTPException(status_code=400, detail="暂时只支持 pdf、txt、md 文件。")

    try:
        result = job_manager.submit_job(
            upload_batch=saved_batch,
            provider_mode=selection.provider_mode,
            api_key=selection.api_key,
            model=selection.model,
        )
    except ValueError as exc:
        cleanup_saved_upload_batch(saved_batch)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        cleanup_saved_upload_batch(saved_batch)
        logger.exception("创建图谱任务失败")
        raise HTTPException(status_code=500, detail="图谱任务创建失败，请稍后重试。")

    result["provider_mode"] = selection.provider_mode
    result["detail"] = selection.detail
    return JSONResponse(result, status_code=202)


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    try:
        return JSONResponse(job_manager.get_public_job(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在。") from exc
