from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from knowledge_graph.job_runtime import JobManager
from knowledge_graph.local_provider import LocalProviderManager
from knowledge_graph.pipeline.artifact_store import cleanup_saved_upload_batch, save_uploaded_files
from knowledge_graph.runtime_assets import ensure_runtime_assets
from knowledge_graph.settings import (
    DEFAULT_ARK_MODEL_ID,
    MAX_FILES_PER_JOB,
    MAX_TOTAL_UPLOAD_BYTES,
    RUNS_DIR,
    STATIC_DIR,
    TEMPLATES_DIR,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_runtime_assets()
    try:
        yield
    finally:
        job_manager.shutdown()
        local_provider_manager.shutdown()


app = FastAPI(title="知识关系图谱引擎", lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
RUNS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/runs", StaticFiles(directory=str(RUNS_DIR)), name="runs")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

logger = logging.getLogger(__name__)
job_manager = JobManager()
local_provider_manager = LocalProviderManager()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/provider-status")
def get_provider_status():
    return JSONResponse(local_provider_manager.get_public_status(auto_start=False))


@app.post("/local-provider/download-and-configure")
def download_and_configure_local_model_dir():
    try:
        return JSONResponse(local_provider_manager.download_models_and_configure())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("下载模型并配置目录失败")
        raise HTTPException(status_code=500, detail="下载模型并配置目录失败，请稍后重试。")


@app.post("/local-provider/select-existing-dir")
def select_existing_local_model_dir():
    try:
        return JSONResponse(local_provider_manager.select_existing_model_dir())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("绑定已有模型目录失败")
        raise HTTPException(status_code=500, detail="绑定已有模型目录失败，请稍后重试。")


@app.post("/local-provider/ensure-started")
def ensure_started_local_provider():
    try:
        return JSONResponse(local_provider_manager.ensure_started())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("启动本地模型失败")
        raise HTTPException(status_code=500, detail="启动本地模型失败，请稍后重试。")


@app.post("/local-provider/preferred-model")
def update_preferred_local_model(model_name: str = Form(...)):
    try:
        return JSONResponse(local_provider_manager.set_preferred_model(model_name))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("切换本地模型失败")
        raise HTTPException(status_code=500, detail="切换本地模型失败，请稍后重试。")


@app.post("/generate")
def generate_graph(
    api_key: str = Form(""),
    model: str = Form(DEFAULT_ARK_MODEL_ID),
    provider_preference: str = Form("auto"),
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="请先上传文件。")
    if len(files) > MAX_FILES_PER_JOB:
        raise HTTPException(status_code=400, detail=f"单次最多上传 {MAX_FILES_PER_JOB} 个文件，请减少后重试。")

    try:
        selection = local_provider_manager.resolve_for_generation(
            api_key=api_key,
            ark_model=model or DEFAULT_ARK_MODEL_ID,
            provider_preference=provider_preference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        saved_batch = save_uploaded_files(files, max_total_bytes=MAX_TOTAL_UPLOAD_BYTES)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("保存上传文件失败")
        raise HTTPException(status_code=500, detail="上传文件保存失败，请稍后重试。")

    if not saved_batch.sources:
        cleanup_saved_upload_batch(saved_batch)
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
