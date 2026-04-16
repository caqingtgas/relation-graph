from __future__ import annotations

from concurrent.futures import as_completed
from typing import Callable, Protocol, Sequence

from relation_graph.llm_request_pool import LLMRequestPool
from relation_graph.pipeline.types import ChunkExtractionSummary, PreparedChunk, RawRelationRecord, WarningDetail
from relation_graph.settings import ARK_MAX_CONCURRENCY


class RelationRequestPool(Protocol):
    def submit_extract(
        self,
        text: str,
        *,
        chunk_id: str,
        model: str,
        api_key: str,
        provider_mode: str,
    ):
        ...

    def release(self, *, model: str, api_key: str, provider_mode: str):
        ...

    def close(self):
        ...


def empty_token_usage() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def merge_token_usage(target: dict[str, int], addition: dict | None) -> None:
    if not isinstance(addition, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        target[key] = int(target.get(key, 0)) + int(addition.get(key) or 0)


def extract_relations_for_chunks(
    chunks: Sequence[PreparedChunk],
    *,
    provider_mode: str,
    model: str,
    api_key: str,
    request_pool: RelationRequestPool | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[RawRelationRecord], dict[str, int], ChunkExtractionSummary]:
    total = len(chunks)
    relation_rows: list[RawRelationRecord] = []
    usage_totals = empty_token_usage()
    warnings: list[str] = []
    warning_details: list[WarningDetail] = []
    if total == 0:
        return relation_rows, usage_totals, ChunkExtractionSummary(successful_chunks=0, failed_chunks=0)

    completed = 0
    successful = 0
    failed = 0

    def notify_progress() -> None:
        if progress_callback:
            progress_callback(completed, total)

    def collect_result(result) -> None:
        nonlocal completed, successful
        items, usage = result
        relation_rows.extend(
            RawRelationRecord(
                node_1=item.node_1,
                node_1_type=item.node_1_type,
                node_2=item.node_2,
                node_2_type=item.node_2_type,
                edge=item.edge,
                edge_mode=item.edge_mode,
                chunk_id=item.chunk_id,
            )
            for item in items
        )
        merge_token_usage(usage_totals, usage)
        successful += 1
        completed += 1
        notify_progress()

    owned_pool = None
    active_pool = request_pool
    if active_pool is None:
        owned_pool = LLMRequestPool(max_concurrency=ARK_MAX_CONCURRENCY)
        active_pool = owned_pool

    try:
        futures = {
            active_pool.submit_extract(
                chunk.text,
                chunk_id=chunk.chunk_id,
                model=model,
                api_key=api_key,
                provider_mode=provider_mode,
            ): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk = futures[future]
            try:
                collect_result(future.result())
            except Exception as exc:
                failed += 1
                completed += 1
                detail = WarningDetail(
                    source=chunk.source,
                    page=chunk.page,
                    chunk_index=chunk.chunk_index,
                    chunk_id=chunk.chunk_id,
                    error=str(exc),
                )
                warning_details.append(detail)
                warnings.append(detail.to_text())
                notify_progress()
    finally:
        if owned_pool is not None:
            owned_pool.release(model=model, api_key=api_key, provider_mode=provider_mode)
            owned_pool.close()

    return relation_rows, usage_totals, ChunkExtractionSummary(
        successful_chunks=successful,
        failed_chunks=failed,
        warnings=tuple(warnings),
        warning_details=tuple(warning_details),
    )

