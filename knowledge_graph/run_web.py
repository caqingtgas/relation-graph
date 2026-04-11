import uvicorn

from knowledge_graph.runtime_assets import ensure_runtime_assets


if __name__ == "__main__":
    ensure_runtime_assets()
    uvicorn.run("knowledge_graph.webapp:app", host="127.0.0.1", port=8000, reload=False)
