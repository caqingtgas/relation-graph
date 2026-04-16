from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobStage(str, Enum):
    QUEUED = "queued"
    LOADING_DOCUMENTS = "loading_documents"
    SPLITTING_DOCUMENTS = "splitting_documents"
    EXTRACTING_RELATIONS = "extracting_relations"
    RENDERING_GRAPH = "rendering_graph"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class UploadedSource:
    path: Path
    original_name: str


@dataclass(frozen=True)
class SavedUploadBatch:
    temp_dir: Path | None
    sources: list[UploadedSource]
    total_bytes: int


@dataclass(frozen=True)
class DocumentChunk:
    page_content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class PreparedChunk:
    text: str
    source: str
    page: int | None
    chunk_index: int
    chunk_id: str

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "chunk_id": self.chunk_id,
        }


@dataclass(frozen=True)
class ProgressEvent:
    current_stage: JobStage
    detail: str
    total_chunks: int | None = None
    completed_chunks: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "current_stage": self.current_stage.value,
            "detail": self.detail,
        }
        if self.total_chunks is not None:
            payload["total_chunks"] = self.total_chunks
        if self.completed_chunks is not None:
            payload["completed_chunks"] = self.completed_chunks
        return payload


@dataclass(frozen=True)
class WarningDetail:
    source: str
    page: int | None
    chunk_index: int
    chunk_id: str
    error: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_text(self) -> str:
        location_parts = []
        if self.source:
            location_parts.append(self.source)
        if self.page is not None:
            location_parts.append(f"第 {self.page} 页")
        location_parts.append(f"块 {self.chunk_index}")
        location = " / ".join(location_parts)
        return f"{location}（{self.chunk_id}）抽取失败：{self.error}" if location else f"chunk {self.chunk_id} 抽取失败：{self.error}"


@dataclass(frozen=True)
class ChunkExtractionSummary:
    successful_chunks: int
    failed_chunks: int
    warnings: tuple[str, ...] = ()
    warning_details: tuple[WarningDetail, ...] = ()


@dataclass(frozen=True)
class RawRelationRecord:
    node_1: str
    node_1_type: str
    node_2: str
    node_2_type: str
    edge: str
    edge_mode: str
    chunk_id: str
    count: int = 1

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "node_1": self.node_1,
            "node_1_type": self.node_1_type,
            "node_2": self.node_2,
            "node_2_type": self.node_2_type,
            "edge": self.edge,
            "edge_mode": self.edge_mode,
            "chunk_id": self.chunk_id,
            "count": self.count,
        }


@dataclass(frozen=True)
class AggregatedRelation:
    node_1: str
    node_2: str
    node_1_type: str
    node_2_type: str
    chunk_ids: tuple[str, ...]
    edge_mode: str
    primary_edge: str
    edge_variants: tuple[str, ...]
    count: int

    @property
    def chunk_id(self) -> str:
        return ",".join(self.chunk_ids)

    @property
    def edge(self) -> str:
        return self.primary_edge

    @property
    def edge_variants_text(self) -> str:
        return " | ".join(self.edge_variants)

    def tooltip_text(self) -> str:
        extra_edges = [edge for edge in self.edge_variants if edge != self.primary_edge]
        lines = [f"主关系: {self.primary_edge}"]
        if extra_edges:
            lines.append(f"其他关系: {' | '.join(extra_edges)}")
        lines.append(f"出现次数: {self.count}")
        return "\n".join(lines)

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "node_1": self.node_1,
            "node_2": self.node_2,
            "node_1_type": self.node_1_type,
            "node_2_type": self.node_2_type,
            "chunk_id": self.chunk_id,
            "edge_mode": self.edge_mode,
            "edge": self.primary_edge,
            "edge_variants": self.edge_variants_text,
            "count": self.count,
        }


@dataclass(frozen=True)
class GraphArtifacts:
    run_dir: Path
    graph_html: Path
    graph_data_js: Path
    standalone_graph_html: Path
    chunks_csv: Path
    graph_csv: Path
    grouped_graph_csv: Path
    metadata_json: Path


@dataclass(frozen=True)
class PipelineMetadata:
    run_id: str
    provider: str
    model: str
    input_files: list[str]
    chunk_count: int
    raw_edge_count: int
    final_edge_count: int
    node_count: int
    community_count: int
    artifact_mode: str
    render_data_file: str
    standalone_graph_file: str
    token_usage: dict[str, int]
    source_file_count: int
    successful_chunk_count: int = 0
    failed_chunk_count: int = 0
    warnings: list[str] | None = None
    warning_details: list[WarningDetail] | None = None
    artifact_version: int = 3
    edge_label_mode: str = "primary_with_variants"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["warnings"] is None:
            payload["warnings"] = []
        if payload["warning_details"] is None:
            payload["warning_details"] = []
        return payload


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    artifacts: GraphArtifacts
    metadata: PipelineMetadata

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": self.artifacts.run_dir,
            "graph_html": self.artifacts.graph_html,
            "graph_data_js": self.artifacts.graph_data_js,
            "standalone_graph_html": self.artifacts.standalone_graph_html,
            "chunks_csv": self.artifacts.chunks_csv,
            "graph_csv": self.artifacts.graph_csv,
            "grouped_graph_csv": self.artifacts.grouped_graph_csv,
            "metadata_json": self.artifacts.metadata_json,
            "metadata": self.metadata.to_dict(),
        }
