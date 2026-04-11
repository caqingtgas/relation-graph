from __future__ import annotations

import shutil
import threading
from pathlib import Path

from knowledge_graph.settings import GRAPH_ASSETS_DIR, STATIC_VENDOR_DIR


VIS_NETWORK_JS_FILE_NAME = "vis-network.min.js"
VIS_NETWORK_CSS_FILE_NAME = "vis-network.min.css"
_RUNTIME_ASSET_LOCK = threading.Lock()


def _required_asset_paths() -> list[Path]:
    return [
        GRAPH_ASSETS_DIR / VIS_NETWORK_JS_FILE_NAME,
        GRAPH_ASSETS_DIR / VIS_NETWORK_CSS_FILE_NAME,
    ]


def ensure_runtime_assets() -> None:
    with _RUNTIME_ASSET_LOCK:
        missing = [path for path in _required_asset_paths() if not path.exists()]
        if missing:
            missing_names = ", ".join(sorted(path.name for path in missing))
            raise RuntimeError(
                f"缺少图谱运行时静态资源：{missing_names}。请确认仓库内 graph_assets 资源完整。"
            )

        STATIC_VENDOR_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            GRAPH_ASSETS_DIR / VIS_NETWORK_JS_FILE_NAME,
            STATIC_VENDOR_DIR / VIS_NETWORK_JS_FILE_NAME,
        )
        shutil.copy2(
            GRAPH_ASSETS_DIR / VIS_NETWORK_CSS_FILE_NAME,
            STATIC_VENDOR_DIR / VIS_NETWORK_CSS_FILE_NAME,
        )
