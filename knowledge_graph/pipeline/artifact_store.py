from __future__ import annotations

import csv
import json
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

import networkx as nx

from knowledge_graph.pipeline.graph_renderer import (
    GRAPH_DATA_FILE_NAME,
    STANDALONE_GRAPH_FILE_NAME,
    write_graph_bundle,
)
from knowledge_graph.pipeline.types import (
    AggregatedRelation,
    ChunkExtractionSummary,
    GraphArtifacts,
    PipelineMetadata,
    PipelineResult,
    PreparedChunk,
    RawRelationRecord,
    SavedUploadBatch,
    UploadedSource,
)
from knowledge_graph.settings import MAX_SUCCESSFUL_RUNS, RUNS_DIR, RUN_TEMP_PREFIX, UPLOAD_TEMP_PREFIX


def save_uploaded_files(upload_files, *, max_total_bytes: int | None = None) -> SavedUploadBatch:
    temp_dir = Path(tempfile.mkdtemp(prefix=UPLOAD_TEMP_PREFIX))
    saved_sources: list[UploadedSource] = []
    total_bytes = 0
    try:
        for upload in upload_files:
            original_name = Path((upload.filename or "").replace("\\", "/")).name
            suffix = Path(original_name).suffix.lower()
            if suffix not in {".pdf", ".txt", ".md"}:
                continue
            safe_name = original_name or f"upload{suffix}"
            payload = upload.file.read()
            total_bytes += len(payload)
            if max_total_bytes is not None and total_bytes > max_total_bytes:
                raise ValueError(f"上传文件总大小超过上限 {max_total_bytes // (1024 * 1024)} MB，请减少文件后重试。")
            target = temp_dir / f"{uuid4().hex}_{safe_name}"
            with target.open("wb") as handle:
                handle.write(payload)
            saved_sources.append(UploadedSource(path=target, original_name=safe_name))
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return SavedUploadBatch(temp_dir=temp_dir, sources=saved_sources, total_bytes=total_bytes)


def cleanup_saved_upload_batch(batch: SavedUploadBatch | None) -> None:
    if batch is None:
        return
    shutil.rmtree(batch.temp_dir, ignore_errors=True)


def prune_run_directories(*, max_runs: int = MAX_SUCCESSFUL_RUNS) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_dirs = [path for path in RUNS_DIR.iterdir() if path.is_dir() and not path.name.startswith(RUN_TEMP_PREFIX)]
    if len(run_dirs) <= max_runs:
        return
    for stale_dir in sorted(run_dirs, key=lambda item: item.stat().st_mtime, reverse=True)[max_runs:]:
        shutil.rmtree(stale_dir, ignore_errors=True)


def cleanup_stale_runtime_files() -> None:
    temp_root = Path(tempfile.gettempdir())
    for stale_dir in temp_root.glob(f"{UPLOAD_TEMP_PREFIX}*"):
        if stale_dir.is_dir():
            shutil.rmtree(stale_dir, ignore_errors=True)
    if RUNS_DIR.exists():
        for stale_dir in RUNS_DIR.glob(f"{RUN_TEMP_PREFIX}*"):
            if stale_dir.is_dir():
                shutil.rmtree(stale_dir, ignore_errors=True)


def _write_csv_rows(path: Path, fieldnames: Sequence[str], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="|", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_pipeline_result(
    *,
    prepared_chunks: Sequence[PreparedChunk],
    raw_relations: Sequence[RawRelationRecord],
    aggregated_relations: Sequence[AggregatedRelation],
    graph: nx.DiGraph,
    community_count: int,
    provider: str,
    model: str,
    input_files: Sequence[str],
    token_usage: dict[str, int],
    extraction_summary: ChunkExtractionSummary,
    run_id: str,
) -> PipelineResult:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS_DIR / run_id
    temp_run_dir = RUNS_DIR / f"{RUN_TEMP_PREFIX}{run_id}"
    if temp_run_dir.exists():
        shutil.rmtree(temp_run_dir, ignore_errors=True)
    temp_run_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = temp_run_dir / "chunks.csv"
    graph_path = temp_run_dir / "graph.csv"
    grouped_graph_path = temp_run_dir / "graph_grouped.csv"
    metadata_path = temp_run_dir / "metadata.json"

    try:
        _write_csv_rows(
            chunks_path,
            ["text", "source", "page", "chunk_index", "chunk_id"],
            [chunk.to_csv_row() for chunk in prepared_chunks],
        )
        _write_csv_rows(
            graph_path,
            ["node_1", "node_1_type", "node_2", "node_2_type", "edge", "edge_mode", "chunk_id", "count"],
            [relation.to_csv_row() for relation in raw_relations],
        )
        _write_csv_rows(
            grouped_graph_path,
            ["node_1", "node_2", "node_1_type", "node_2_type", "chunk_id", "edge_mode", "edge", "edge_variants", "count"],
            [relation.to_csv_row() for relation in aggregated_relations],
        )
        html_path, graph_data_path, standalone_html_path = write_graph_bundle(graph, aggregated_relations, temp_run_dir)

        metadata = PipelineMetadata(
            run_id=run_id,
            provider=provider,
            model=model,
            input_files=list(input_files),
            source_file_count=len(input_files),
            chunk_count=len(prepared_chunks),
            raw_edge_count=len(raw_relations),
            final_edge_count=len(aggregated_relations),
            node_count=graph.number_of_nodes(),
            community_count=community_count,
            artifact_mode="bundle",
            render_data_file=GRAPH_DATA_FILE_NAME,
            standalone_graph_file=STANDALONE_GRAPH_FILE_NAME,
            token_usage={key: int(value) for key, value in token_usage.items()},
            successful_chunk_count=extraction_summary.successful_chunks,
            failed_chunk_count=extraction_summary.failed_chunks,
            warnings=list(extraction_summary.warnings),
            warning_details=list(extraction_summary.warning_details),
        )
        metadata_path.write_text(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        temp_run_dir.replace(run_dir)
    except Exception:
        shutil.rmtree(temp_run_dir, ignore_errors=True)
        raise

    artifacts = GraphArtifacts(
        run_dir=run_dir,
        graph_html=run_dir / "graph.html",
        graph_data_js=run_dir / GRAPH_DATA_FILE_NAME,
        standalone_graph_html=run_dir / STANDALONE_GRAPH_FILE_NAME,
        chunks_csv=run_dir / "chunks.csv",
        graph_csv=run_dir / "graph.csv",
        grouped_graph_csv=run_dir / "graph_grouped.csv",
        metadata_json=run_dir / "metadata.json",
    )
    return PipelineResult(run_id=run_id, artifacts=artifacts, metadata=metadata)
