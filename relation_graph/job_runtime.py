from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Queue
from typing import Any
from uuid import uuid4

from relation_graph.ark_client import ArkAuthenticationError, ArkClientError
from relation_graph.graph_pipeline import run_graph_pipeline
from relation_graph.llm_request_pool import LLMRequestPool
from relation_graph.pipeline.artifact_store import cleanup_saved_upload_batch, cleanup_stale_runtime_files, prune_run_directories
from relation_graph.ollama_client import OllamaClientError
from relation_graph.pipeline.types import JobStage, JobStatus, ProgressEvent, SavedUploadBatch
from relation_graph.settings import (
    COMPLETED_JOB_TTL_SECONDS,
    MAX_COMPLETED_JOB_RECORDS,
    MAX_PENDING_JOBS,
    MAX_SUCCESSFUL_RUNS,
    MAX_TOTAL_CHUNKS_PER_JOB,
)


logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class JobRecord:
    job_id: str
    provider_mode: str
    api_key: str
    model: str
    upload_batch: SavedUploadBatch | None
    status: JobStatus = JobStatus.QUEUED
    created_at: str = field(default_factory=_utcnow)
    started_at: str | None = None
    finished_at: str | None = None
    total_chunks: int = 0
    completed_chunks: int = 0
    current_stage: JobStage = JobStage.QUEUED
    detail: str = "任务已排队，等待处理。"
    result: dict[str, Any] | None = None


class JobManager:
    def __init__(
        self,
        *,
        request_pool: LLMRequestPool | None = None,
        max_pending_jobs: int = MAX_PENDING_JOBS,
        max_total_chunks: int = MAX_TOTAL_CHUNKS_PER_JOB,
        max_successful_runs: int = MAX_SUCCESSFUL_RUNS,
        completed_job_ttl_seconds: int = COMPLETED_JOB_TTL_SECONDS,
        max_completed_job_records: int = MAX_COMPLETED_JOB_RECORDS,
    ):
        cleanup_stale_runtime_files()
        self._request_pool = request_pool or LLMRequestPool()
        self._max_pending_jobs = max_pending_jobs
        self._max_total_chunks = max_total_chunks
        self._max_successful_runs = max_successful_runs
        self._completed_job_ttl_seconds = completed_job_ttl_seconds
        self._max_completed_job_records = max_completed_job_records
        self._jobs: dict[str, JobRecord] = {}
        self._queue: Queue[str | None] = Queue()
        self._lock = threading.Lock()
        self._shutdown = False
        self._worker = threading.Thread(target=self._worker_loop, name="kg-job-worker", daemon=True)
        self._worker.start()

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        self._queue.put(None)
        self._worker.join(timeout=10)
        self._request_pool.close()

    def submit_job(self, *, upload_batch: SavedUploadBatch, provider_mode: str, api_key: str, model: str) -> dict[str, Any]:
        with self._lock:
            self._prune_finished_jobs_locked()
            if self._shutdown:
                raise ValueError("任务系统已关闭，无法继续提交。")
            pending_jobs = sum(1 for job in self._jobs.values() if job.status in {JobStatus.QUEUED, JobStatus.RUNNING})
            if pending_jobs >= self._max_pending_jobs:
                raise ValueError("当前排队任务较多，请稍后再试。")
            job = JobRecord(
                job_id=uuid4().hex[:12],
                provider_mode=provider_mode,
                api_key=api_key,
                model=model,
                upload_batch=upload_batch,
            )
            self._jobs[job.job_id] = job
        self._queue.put(job.job_id)
        payload = self.get_public_job(job.job_id)
        payload["status_url"] = f"/jobs/{job.job_id}"
        return payload

    def get_public_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            queue_position = self._queue_position_locked(job_id) if job.status == JobStatus.QUEUED else None
            return {
                "job_id": job.job_id,
                "status": job.status.value,
                "provider_mode": job.provider_mode,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "total_chunks": job.total_chunks,
                "completed_chunks": job.completed_chunks,
                "current_stage": job.current_stage.value,
                "detail": job.detail,
                "queue_position": queue_position,
                "result": job.result,
            }

    def _queue_position_locked(self, job_id: str) -> int | None:
        queued_jobs = [job.job_id for job in self._jobs.values() if job.status == JobStatus.QUEUED]
        if job_id not in queued_jobs:
            return None
        return queued_jobs.index(job_id) + 1

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                if job_id is None:
                    return
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = JobStatus.RUNNING
            job.started_at = _utcnow()
            job.current_stage = JobStage.LOADING_DOCUMENTS
            job.detail = "正在读取文档。"
            upload_batch = job.upload_batch
            provider_mode = job.provider_mode
            api_key = job.api_key
            model = job.model

        def progress_callback(event: ProgressEvent) -> None:
            with self._lock:
                active_job = self._jobs[job_id]
                active_job.current_stage = event.current_stage
                active_job.detail = event.detail
                if event.total_chunks is not None:
                    active_job.total_chunks = int(event.total_chunks)
                if event.completed_chunks is not None:
                    active_job.completed_chunks = int(event.completed_chunks)

        try:
            result = run_graph_pipeline(
                files=upload_batch.sources,
                provider_mode=provider_mode,
                api_key=api_key,
                model=model,
                request_pool=self._request_pool,
                max_total_chunks=self._max_total_chunks,
                progress_callback=progress_callback,
            )
        except (ValueError, ArkAuthenticationError, ArkClientError, OllamaClientError) as exc:
            self._mark_failed(job_id, str(exc))
        except Exception:
            logger.exception("图谱任务执行失败: %s", job_id)
            self._mark_failed(job_id, "图谱生成失败，请稍后重试或检查输入文件。")
        else:
            prune_run_directories(max_runs=self._max_successful_runs)
            with self._lock:
                active_job = self._jobs[job_id]
                self._finalize_job_locked(
                    active_job,
                    status=JobStatus.SUCCEEDED,
                    current_stage=JobStage.COMPLETED,
                    detail=(
                        "图谱生成完成，存在部分文本块抽取失败。"
                        if int((result.get("metadata") or {}).get("failed_chunk_count") or 0) > 0
                        else "图谱生成完成。"
                    ),
                    result=self._build_result_payload(result),
                )
        finally:
            cleanup_saved_upload_batch(upload_batch)
            self._request_pool.release(model=model, api_key=api_key, provider_mode=provider_mode)

    def _mark_failed(self, job_id: str, detail: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._finalize_job_locked(
                job,
                status=JobStatus.FAILED,
                current_stage=JobStage.FAILED,
                detail=detail,
                result=None,
            )

    def _finalize_job_locked(
        self,
        job: JobRecord,
        *,
        status: JobStatus,
        current_stage: JobStage,
        detail: str,
        result: dict[str, Any] | None,
    ) -> None:
        job.status = status
        job.finished_at = _utcnow()
        job.current_stage = current_stage
        job.detail = detail
        job.result = result
        job.api_key = ""
        job.upload_batch = None
        self._prune_finished_jobs_locked()

    def _prune_finished_jobs_locked(self) -> None:
        finished_jobs = [
            job for job in self._jobs.values() if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED} and job.finished_at
        ]
        if not finished_jobs:
            return

        now = datetime.now(timezone.utc)
        expired_ids = []
        for job in finished_jobs:
            finished_at = datetime.fromisoformat(job.finished_at)
            if (now - finished_at).total_seconds() > self._completed_job_ttl_seconds:
                expired_ids.append(job.job_id)
        for expired_id in expired_ids:
            self._jobs.pop(expired_id, None)

        remaining_finished = [
            job for job in self._jobs.values() if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED} and job.finished_at
        ]
        if len(remaining_finished) <= self._max_completed_job_records:
            return
        overflow = len(remaining_finished) - self._max_completed_job_records
        stale_jobs = sorted(remaining_finished, key=lambda item: (item.finished_at or "", item.created_at))[:overflow]
        for job in stale_jobs:
            self._jobs.pop(job.job_id, None)

    @staticmethod
    def _build_result_payload(result: dict[str, Any]) -> dict[str, Any]:
        run_id = str(result["run_id"])
        metadata = dict(result["metadata"])
        return {
            "run_id": run_id,
            "provider_mode": metadata.get("provider", "ark"),
            "runDir": str(result["run_dir"]),
            "graphFilePath": str(result["graph_html"]),
            "graphDataFilePath": str(result["graph_data_js"]),
            "standaloneGraphFilePath": str(result["standalone_graph_html"]),
            "chunksCsvFilePath": str(result["chunks_csv"]),
            "graphCsvFilePath": str(result["graph_csv"]),
            "groupedGraphCsvFilePath": str(result["grouped_graph_csv"]),
            "metadataFilePath": str(result["metadata_json"]),
            "metadata": metadata,
        }

