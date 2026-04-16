from __future__ import annotations

import uvicorn

from relation_graph.desktop_api import app
from relation_graph.runtime_assets import ensure_runtime_assets


if __name__ == "__main__":
    ensure_runtime_assets()
    uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
