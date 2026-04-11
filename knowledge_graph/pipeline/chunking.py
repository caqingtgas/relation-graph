from __future__ import annotations

from typing import Sequence
from uuid import uuid4

from knowledge_graph.pipeline.types import DocumentChunk, PreparedChunk


CHUNK_SIZE = 1500
CHUNK_OVERLAP = 150
MIN_LAST_CHUNK_RATIO = 0.35


def split_text(text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0。")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap 不能为负数。")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size。")
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", "。", "！", "？", ".", "；", ";", " ", ""]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            for separator in separators:
                if not separator:
                    break
                index = text.rfind(separator, start + chunk_size // 2, end)
                if index != -1:
                    end = index + len(separator)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    if len(chunks) >= 2 and len(chunks[-1]) < int(chunk_size * MIN_LAST_CHUNK_RATIO):
        merged_tail = f"{chunks[-2].rstrip()}\n{chunks[-1].lstrip()}".strip()
        if len(merged_tail) <= chunk_size:
            chunks[-2] = merged_tail
            chunks.pop()
    return chunks


def split_documents(documents: Sequence[DocumentChunk]) -> list[DocumentChunk]:
    pages: list[DocumentChunk] = []
    for document in documents:
        for index, chunk_text in enumerate(split_text(document.page_content)):
            metadata = dict(document.metadata)
            metadata["chunk_index"] = index
            pages.append(DocumentChunk(page_content=chunk_text, metadata=metadata))
    return pages


def prepare_chunks(chunks: Sequence[DocumentChunk]) -> list[PreparedChunk]:
    prepared: list[PreparedChunk] = []
    for chunk in chunks:
        metadata = dict(chunk.metadata)
        prepared.append(
            PreparedChunk(
                text=chunk.page_content,
                source=str(metadata.get("source", "")),
                page=int(metadata["page"]) if metadata.get("page") is not None else None,
                chunk_index=int(metadata.get("chunk_index", 0)),
                chunk_id=uuid4().hex,
            )
        )
    return prepared
