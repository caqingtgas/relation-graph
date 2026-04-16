from __future__ import annotations

import json
import shutil
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Sequence

import networkx as nx

from relation_graph.pipeline.types import AggregatedRelation
from relation_graph.runtime_assets import ensure_runtime_assets
from relation_graph.settings import GRAPH_ASSETS_DIR, GRAPH_VENDOR_DIR_NAME


GRAPH_DATA_FILE_NAME = "graph_data.js"
STANDALONE_GRAPH_FILE_NAME = "graph_standalone.html"
VIS_NETWORK_CSS_FILE_NAME = "vis-network.min.css"
VIS_NETWORK_JS_FILE_NAME = "vis-network.min.js"


@lru_cache(maxsize=None)
def _read_graph_asset(filename: str) -> str:
    path = GRAPH_ASSETS_DIR / filename
    if filename in {VIS_NETWORK_CSS_FILE_NAME, VIS_NETWORK_JS_FILE_NAME} and not path.exists():
        ensure_runtime_assets()
    if not path.exists():
        raise RuntimeError(f"缺少图谱运行时资源：{filename}")
    return path.read_text(encoding="utf-8")


def _json_script_dumps(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _viewer_options() -> dict:
    return {
        "autoResize": True,
        "interaction": {"hover": True, "navigationButtons": False, "keyboard": False},
        "configure": {"enabled": False},
        "nodes": {
            "shape": "dot",
            "font": {
                "size": 16,
                "face": "Microsoft YaHei, sans-serif",
                "strokeWidth": 3,
                "strokeColor": "#ffffff",
                "color": "#1d2736",
            },
            "borderWidth": 2,
            "borderWidthSelected": 4,
        },
        "edges": {
            "color": {"inherit": "both"},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}},
            "smooth": {"type": "continuous", "forceDirection": "none"},
            "font": {"size": 4, "strokeWidth": 0.5, "align": "middle"},
            "scaling": {"label": {"enabled": False}},
        },
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -180,
                "centralGravity": 0.008,
                "springLength": 240,
                "springConstant": 0.07,
                "avoidOverlap": 1.15,
            },
            "minVelocity": 0.75,
            "solver": "forceAtlas2Based",
            "stabilization": {"enabled": True, "iterations": 1000},
        },
    }


def _build_graph_payload(graph: nx.DiGraph, relations: Sequence[AggregatedRelation]) -> dict[str, list[dict]]:
    def safe_tooltip(value: object) -> str:
        return escape(str(value), quote=False)

    node_ids = {node_label: f"node-{index}" for index, node_label in enumerate(graph.nodes(), start=1)}
    nodes_payload: list[dict] = []
    for node_label, attrs in graph.nodes(data=True):
        nodes_payload.append(
            {
                "id": node_ids[node_label],
                "label": str(node_label),
                "title": safe_tooltip(attrs.get("title", str(node_label))),
                "color": attrs.get("color"),
                "size": attrs.get("size"),
                "group": attrs.get("group"),
            }
        )

    edges_payload: list[dict] = []
    for index, relation in enumerate(relations, start=1):
        edge_mode = str(relation.edge_mode or "undirected").strip().lower()
        edges_payload.append(
            {
                "id": f"edge-{index}",
                "from": node_ids[relation.node_1],
                "to": node_ids[relation.node_2],
                "title": safe_tooltip(relation.tooltip_text()),
                "label_text": relation.primary_edge,
                "value": float(relation.count),
                "width": max(1.0, float(relation.count)),
                "arrows": "to" if edge_mode == "directed" else "",
            }
        )
    return {"nodes": nodes_payload, "edges": edges_payload}


def _render_viewer_html(*, vis_network_css: str, graph_data_script: str, options: dict, vis_network_js: str) -> str:
    template = _read_graph_asset("graph_viewer_template.html")
    runtime = _read_graph_asset("graph_viewer_runtime.js")
    return (
        template.replace("__VIS_NETWORK_CSS__", vis_network_css)
        .replace("__GRAPH_DATA_SCRIPT__", graph_data_script)
        .replace("__GRAPH_OPTIONS__", _json_script_dumps(options))
        .replace("__VIS_NETWORK_JS__", vis_network_js)
        .replace("__GRAPH_VIEWER_RUNTIME__", runtime)
    )


def write_graph_bundle(graph: nx.DiGraph, relations: Sequence[AggregatedRelation], run_dir: Path) -> tuple[Path, Path, Path]:
    html_path = run_dir / "graph.html"
    data_path = run_dir / GRAPH_DATA_FILE_NAME
    standalone_html_path = run_dir / STANDALONE_GRAPH_FILE_NAME
    vendor_dir = run_dir / GRAPH_VENDOR_DIR_NAME
    graph_payload = _build_graph_payload(graph, relations)
    options = _viewer_options()
    css_content = _read_graph_asset(VIS_NETWORK_CSS_FILE_NAME)
    js_content = _read_graph_asset(VIS_NETWORK_JS_FILE_NAME)
    vendor_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GRAPH_ASSETS_DIR / VIS_NETWORK_CSS_FILE_NAME, vendor_dir / VIS_NETWORK_CSS_FILE_NAME)
    shutil.copy2(GRAPH_ASSETS_DIR / VIS_NETWORK_JS_FILE_NAME, vendor_dir / VIS_NETWORK_JS_FILE_NAME)
    data_path.write_text("window.KG_GRAPH_DATA = " + _json_script_dumps(graph_payload) + ";", encoding="utf-8")
    html_path.write_text(
        _render_viewer_html(
            vis_network_css=f'<link rel="stylesheet" href="./{GRAPH_VENDOR_DIR_NAME}/{VIS_NETWORK_CSS_FILE_NAME}">',
            graph_data_script=f'<script src="./{GRAPH_DATA_FILE_NAME}"></script>',
            options=options,
            vis_network_js=f'<script src="./{GRAPH_VENDOR_DIR_NAME}/{VIS_NETWORK_JS_FILE_NAME}"></script>',
        ),
        encoding="utf-8",
    )
    standalone_html_path.write_text(
        _render_viewer_html(
            vis_network_css=f"<style>\n{css_content}\n</style>",
            graph_data_script=f"<script>window.KG_GRAPH_DATA = {_json_script_dumps(graph_payload)};</script>",
            options=options,
            vis_network_js=f"<script>\n{js_content}\n</script>",
        ),
        encoding="utf-8",
    )
    return html_path, data_path, standalone_html_path
