from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path

from fastapi.testclient import TestClient

from relation_graph import desktop_api
from relation_graph.pipeline.chunking import split_text
from relation_graph.pipeline.document_loader import _clean_pdf_text
from relation_graph.pipeline.artifact_store import cleanup_stale_runtime_files, write_pipeline_result
from relation_graph.pipeline.graph_renderer import write_graph_bundle
from relation_graph.pipeline.relation_aggregation import aggregate_relations, build_graph
from relation_graph.pipeline.relation_service import extract_relations_for_chunks
from relation_graph.pipeline.types import AggregatedRelation, ChunkExtractionSummary, PreparedChunk, RawRelationRecord, WarningDetail
from relation_graph import runtime_assets
from relation_graph.kg_models import canonical_text_key


def test_clean_pdf_text_preserves_paragraph_breaks():
    raw = "第一段  内容\n\n\n第二段    内容\n\n第三段"
    cleaned = _clean_pdf_text(raw)

    assert "第一段 内容" in cleaned
    assert "第二段 内容" in cleaned
    assert "第三段" in cleaned
    assert "\n\n" in cleaned


def test_canonical_text_key_normalizes_full_width_variants():
    assert canonical_text_key("OpenAI ２０２６") == canonical_text_key("OpenAI 2026")


def test_clean_pdf_text_preserves_meaningful_single_char_lines():
    raw = "一\n项目背景\n甲\n方案说明\n。\n"
    cleaned = _clean_pdf_text(raw)

    assert "一" in cleaned
    assert "甲" in cleaned
    assert "项目背景" in cleaned
    assert "方案说明" in cleaned
    assert "。\n" not in cleaned


def test_split_text_merges_tiny_tail_chunk():
    text = ("甲" * 1250) + "\n\n" + ("乙" * 80)
    chunks = split_text(text, chunk_size=1500, chunk_overlap=150)

    assert len(chunks) == 1
    assert "乙" * 20 in chunks[0]


def test_split_text_keeps_tiny_tail_when_merge_would_exceed_limit():
    text = ("甲" * 1499) + "\n\n" + ("乙" * 80)
    chunks = split_text(text, chunk_size=1500, chunk_overlap=150)

    assert len(chunks) == 2
    assert "乙" * 20 in chunks[-1]


class _FakeRequestPool:
    def __init__(self):
        self._futures: list[Future] = []

    def submit_extract(self, text: str, *, chunk_id: str, model: str, api_key: str, provider_mode: str):
        future: Future = Future()
        if text == "boom":
            future.set_exception(RuntimeError("failure"))
        else:
            future.set_result(([], {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}))
        self._futures.append(future)
        return future

    def release(self, *, model: str, api_key: str, provider_mode: str):
        return None

    def close(self):
        return None


def test_extract_relations_for_chunks_tolerates_partial_failure():
    chunks = [
        PreparedChunk(text="ok", source="a", page=1, chunk_index=0, chunk_id="c1"),
        PreparedChunk(text="boom", source="b", page=1, chunk_index=1, chunk_id="c2"),
    ]

    rows, usage, summary = extract_relations_for_chunks(
        chunks,
        provider_mode="ark",
        model="demo",
        api_key="demo",
        request_pool=_FakeRequestPool(),
    )

    assert rows == []
    assert usage["total_tokens"] == 3
    assert summary.successful_chunks == 1
    assert summary.failed_chunks == 1
    assert any("c2" in item for item in summary.warnings)
    assert len(summary.warning_details) == 1
    assert summary.warning_details[0].source == "b"
    assert summary.warning_details[0].page == 1
    assert summary.warning_details[0].chunk_index == 1


def test_aggregate_relations_prefers_directed_for_same_pair():
    relations = [
        RawRelationRecord("A", "Concept", "B", "Concept", "关联", "undirected", "c1"),
        RawRelationRecord("A", "Concept", "B", "Concept", "影响", "directed", "c2"),
    ]

    aggregated = aggregate_relations(relations)

    assert len(aggregated) == 1
    assert aggregated[0].edge_mode == "directed"
    assert aggregated[0].count == 2
    assert "关联" in aggregated[0].edge_variants
    assert aggregated[0].primary_edge == "影响"


def test_aggregate_relations_keeps_reverse_directed_edges_separate():
    relations = [
        RawRelationRecord("A", "Concept", "B", "Concept", "影响", "directed", "c1"),
        RawRelationRecord("B", "Concept", "A", "Concept", "依赖", "directed", "c2"),
    ]

    aggregated = aggregate_relations(relations)

    assert len(aggregated) == 2
    assert {(item.node_1, item.node_2, item.primary_edge) for item in aggregated} == {
        ("A", "B", "影响"),
        ("B", "A", "依赖"),
    }


def test_graph_html_uses_local_vendor_assets(tmp_path: Path):
    graph = build_graph(
        [
            AggregatedRelation(
                node_1="A",
                node_2="B",
                node_1_type="Concept",
                node_2_type="Concept",
                chunk_ids=("c1",),
                edge_mode="directed",
                primary_edge="影响",
                edge_variants=("影响",),
                count=1,
            )
        ]
    )

    html_path, _, standalone_path = write_graph_bundle(graph, [], tmp_path)
    html = html_path.read_text(encoding="utf-8")
    standalone = standalone_path.read_text(encoding="utf-8")

    assert './vendor/vis-network.min.css' in html
    assert './vendor/vis-network.min.js' in html
    assert '/static/vendor/' not in html
    assert '/static/vendor/' not in standalone


def test_write_pipeline_result_persists_warning_details(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("relation_graph.pipeline.artifact_store.RUNS_DIR", tmp_path)
    graph = build_graph([])
    summary = ChunkExtractionSummary(
        successful_chunks=1,
        failed_chunks=1,
        warnings=("demo warning",),
        warning_details=(
            WarningDetail(
                source="demo.txt",
                page=2,
                chunk_index=3,
                chunk_id="chunk-1",
                error="boom",
            ),
        ),
    )

    result = write_pipeline_result(
        prepared_chunks=[],
        raw_relations=[],
        aggregated_relations=[],
        graph=graph,
        community_count=0,
        provider="local",
        model="qwen3.5:9b",
        input_files=["demo.txt"],
        token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        extraction_summary=summary,
        run_id="demo-run",
    )

    metadata = result.metadata.to_dict()
    assert metadata["warnings"] == ["demo warning"]
    assert metadata["warning_details"] == [
        {
            "source": "demo.txt",
            "page": 2,
            "chunk_index": 3,
            "chunk_id": "chunk-1",
            "error": "boom",
        }
    ]


def test_cleanup_stale_runtime_files_uses_stable_prefixes(tmp_path: Path, monkeypatch):
    upload_dir = tmp_path / "kg-ui-old-123"
    upload_dir.mkdir()
    runs_dir = tmp_path / "runs"
    temp_run_dir = runs_dir / ".tmp-kg-run-old-123"
    temp_run_dir.mkdir(parents=True)

    monkeypatch.setattr("relation_graph.pipeline.artifact_store.RUNS_DIR", runs_dir)
    monkeypatch.setattr("relation_graph.pipeline.artifact_store.UPLOAD_TEMP_PREFIX", "kg-ui-")
    monkeypatch.setattr("relation_graph.pipeline.artifact_store.RUN_TEMP_PREFIX", ".tmp-kg-run-")
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    cleanup_stale_runtime_files()

    assert not upload_dir.exists()
    assert not temp_run_dir.exists()


def test_ensure_runtime_assets_validates_repo_assets_only(tmp_path: Path, monkeypatch):
    graph_assets_dir = tmp_path / "graph_assets"
    graph_assets_dir.mkdir()
    (graph_assets_dir / runtime_assets.VIS_NETWORK_JS_FILE_NAME).write_text("ok", encoding="utf-8")
    (graph_assets_dir / runtime_assets.VIS_NETWORK_CSS_FILE_NAME).write_text("ok", encoding="utf-8")

    monkeypatch.setattr(runtime_assets, "GRAPH_ASSETS_DIR", graph_assets_dir)

    runtime_assets.ensure_runtime_assets()


def test_provider_status_endpoint_is_read_only(monkeypatch):
    captured = {}

    def fake_status(*, auto_start=False):
        captured["auto_start"] = auto_start
        return {
            "provider_mode": "ark",
            "local_runtime_status": "stopped",
            "local_model_name": None,
            "local_model_dir": "models",
            "detail": "stopped",
            "preferred_local_model": "qwen3.5:9b",
            "available_local_models": ["qwen3.5:9b"],
            "local_model_candidates": ["qwen3.5:9b", "qwen3.5:4b"],
        }

    monkeypatch.setattr(desktop_api.local_provider_manager, "get_public_status", fake_status)

    client = TestClient(desktop_api.app)
    response = client.get("/provider/status")

    assert response.status_code == 200
    assert captured["auto_start"] is False


def test_ensure_started_endpoint_routes_to_manager(monkeypatch):
    monkeypatch.setattr(
        desktop_api.local_provider_manager,
        "ensure_started",
        lambda: {
            "provider_mode": "local",
            "local_runtime_status": "ready",
            "local_model_name": "qwen3.5:9b",
            "local_model_dir": "models",
            "detail": "ready",
            "preferred_local_model": "qwen3.5:9b",
            "available_local_models": ["qwen3.5:9b"],
            "local_model_candidates": ["qwen3.5:9b", "qwen3.5:4b"],
        },
    )

    client = TestClient(desktop_api.app)
    response = client.post("/provider/ensure-started")

    assert response.status_code == 200
    assert response.json()["local_runtime_status"] == "ready"


