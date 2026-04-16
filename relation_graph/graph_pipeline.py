from __future__ import annotations

from typing import Callable, Iterable
from uuid import uuid4

from relation_graph.pipeline.artifact_store import write_pipeline_result
from relation_graph.pipeline.chunking import CHUNK_OVERLAP, CHUNK_SIZE, prepare_chunks, split_documents, split_text
from relation_graph.pipeline.document_loader import ensure_uploaded_source, load_documents
from relation_graph.pipeline.graph_renderer import (
    GRAPH_DATA_FILE_NAME,
    STANDALONE_GRAPH_FILE_NAME,
    VIS_NETWORK_CSS_FILE_NAME,
    VIS_NETWORK_JS_FILE_NAME,
)
from relation_graph.pipeline.relation_aggregation import aggregate_relations, apply_communities, build_graph
from relation_graph.pipeline.relation_service import RelationRequestPool, extract_relations_for_chunks
from relation_graph.pipeline.types import (
    AggregatedRelation,
    ChunkExtractionSummary,
    DocumentChunk,
    GraphArtifacts,
    PipelineMetadata,
    PipelineResult,
    PreparedChunk,
    ProgressEvent,
    RawRelationRecord,
    SavedUploadBatch,
    UploadedSource,
)
from relation_graph.pipeline.types import JobStage
from relation_graph.settings import DEFAULT_MODEL_ID


def _emit_progress(progress_callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    if progress_callback:
        progress_callback(event)


def run_graph_pipeline(
    *,
    files: Iterable[UploadedSource],
    provider_mode: str,
    api_key: str,
    model: str = DEFAULT_MODEL_ID,
    request_pool: RelationRequestPool | None = None,
    max_total_chunks: int | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
) -> dict:
    file_list = [ensure_uploaded_source(item) for item in files]
    _emit_progress(progress_callback, ProgressEvent(JobStage.LOADING_DOCUMENTS, "正在读取文档。"))
    documents = load_documents(file_list)
    if not documents:
        raise ValueError("没有读取到可用文本内容。")

    _emit_progress(progress_callback, ProgressEvent(JobStage.SPLITTING_DOCUMENTS, "正在切分文本。"))
    chunks = split_documents(documents)
    if not chunks:
        raise ValueError("文档切块后为空。")
    if max_total_chunks is not None and len(chunks) > max_total_chunks:
        raise ValueError(f"文本切块数量为 {len(chunks)}，超过上限 {max_total_chunks}。请减少文件内容或拆分后重试。")

    prepared_chunks = prepare_chunks(chunks)
    total_chunks = len(prepared_chunks)
    _emit_progress(
        progress_callback,
        ProgressEvent(
            JobStage.EXTRACTING_RELATIONS,
            f"正在抽取关系（0/{total_chunks}）。",
            total_chunks=total_chunks,
            completed_chunks=0,
        ),
    )

    def extract_progress(completed: int, total: int) -> None:
        _emit_progress(
            progress_callback,
            ProgressEvent(
                JobStage.EXTRACTING_RELATIONS,
                f"正在抽取关系（{completed}/{total}）。",
                total_chunks=total,
                completed_chunks=completed,
            ),
        )

    raw_relations, token_usage, extraction_summary = extract_relations_for_chunks(
        prepared_chunks,
        provider_mode=provider_mode,
        model=model,
        api_key=api_key,
        request_pool=request_pool,
        progress_callback=extract_progress,
    )
    if extraction_summary.successful_chunks == 0:
        warning_prefix = extraction_summary.warnings[0] if extraction_summary.warnings else "所有文本块都处理失败。"
        raise ValueError(f"所有文本块抽取失败，无法生成图谱。{warning_prefix}")
    if not raw_relations:
        raise ValueError("所有文本块都没有抽取到可用关系，无法生成图谱。建议缩短单次输入内容，或检查文本是否可提取出明确实体关系。")

    aggregated_relations = aggregate_relations(raw_relations)
    if not aggregated_relations:
        raise ValueError("模型返回结果为空，无法生成图谱。")

    _emit_progress(progress_callback, ProgressEvent(JobStage.RENDERING_GRAPH, "正在渲染图谱产物。"))
    graph = build_graph(aggregated_relations)
    community_count = apply_communities(graph, aggregated_relations)
    result = write_pipeline_result(
        prepared_chunks=prepared_chunks,
        raw_relations=raw_relations,
        aggregated_relations=aggregated_relations,
        graph=graph,
        community_count=community_count,
        provider=provider_mode,
        model=model,
        input_files=[item.original_name for item in file_list],
        token_usage=token_usage,
        extraction_summary=extraction_summary,
        run_id=uuid4().hex[:12],
    )
    return result.to_legacy_dict()


__all__ = [
    "run_graph_pipeline",
]

