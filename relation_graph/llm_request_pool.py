from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from relation_graph.ark_client import ArkClient, ArkClientConfig
from relation_graph.ollama_client import OllamaClient, OllamaClientConfig
from relation_graph.pipeline.relation_prompts import (
    RELATION_SYSTEM_PROMPT,
    build_relation_response_schema,
    build_relation_user_prompt,
)
from relation_graph.kg_models import relation_items_from_batch
from relation_graph.settings import ARK_MAX_CONCURRENCY, ARK_MIN_REQUEST_INTERVAL_SECONDS


class LLMRequestPool:
    def __init__(self, *, max_concurrency: int = ARK_MAX_CONCURRENCY, min_interval_seconds: float = ARK_MIN_REQUEST_INTERVAL_SECONDS):
        self._executor = ThreadPoolExecutor(max_workers=max_concurrency, thread_name_prefix="llm-pool")
        self._min_interval_seconds = float(min_interval_seconds)
        self._rate_lock = threading.Lock()
        self._client_lock = threading.Lock()
        self._clients: dict[tuple[str, str, str], object] = {}
        self._ark_next_available_at = 0.0

    def submit_extract(self, text: str, *, chunk_id: str, model: str, api_key: str, provider_mode: str = "ark") -> Future:
        return self._executor.submit(
            self._run_extract,
            text,
            chunk_id=chunk_id,
            model=model,
            api_key=api_key,
            provider_mode=provider_mode,
        )

    def release(self, *, model: str, api_key: str, provider_mode: str = "ark") -> None:
        cache_key = (provider_mode, model, api_key)
        with self._client_lock:
            client = self._clients.pop(cache_key, None)
        if client is not None:
            client.close()

    def close(self) -> None:
        with self._client_lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            client.close()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _get_client(self, *, provider_mode: str, model: str, api_key: str):
        cache_key = (provider_mode, model, api_key)
        with self._client_lock:
            client = self._clients.get(cache_key)
            if client is None:
                if provider_mode == "local":
                    client = OllamaClient(OllamaClientConfig(model=model))
                else:
                    client = ArkClient(ArkClientConfig(api_key=api_key, model=model))
                self._clients[cache_key] = client
            return client

    def _throttle_ark(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            wait_seconds = self._ark_next_available_at - now
            if wait_seconds > 0:
                time.sleep(wait_seconds)
                now = time.monotonic()
            self._ark_next_available_at = now + self._min_interval_seconds

    def _run_extract(self, text: str, *, chunk_id: str, model: str, api_key: str, provider_mode: str):
        if provider_mode == "ark":
            self._throttle_ark()
        client = self._get_client(provider_mode=provider_mode, model=model, api_key=api_key)
        payload, usage = client.generate_json_with_usage(
            user_prompt=build_relation_user_prompt(text),
            system_prompt=RELATION_SYSTEM_PROMPT,
            response_schema=build_relation_response_schema(),
            schema_name="relation_graph_relations",
            schema_description="从输入文本中抽取可直接用于构建知识图谱的关系列表，只包含关键且明确的关系",
            model=model,
            request_label=f"chunk {chunk_id}",
        )
        return relation_items_from_batch(payload, chunk_id=chunk_id), usage.to_dict()

