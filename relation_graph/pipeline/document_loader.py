from __future__ import annotations

from pathlib import Path
from typing import Iterable
import unicodedata

from pypdf import PdfReader

from relation_graph.pipeline.types import DocumentChunk, UploadedSource


def ensure_uploaded_source(item: UploadedSource | Path) -> UploadedSource:
    if isinstance(item, UploadedSource):
        return item
    return UploadedSource(path=item, original_name=item.name)


def _normalize_line(line: str) -> str:
    return " ".join(str(line or "").replace("\u00a0", " ").split()).strip()


def _clean_pdf_text(raw_text: str) -> str:
    lines = [line.rstrip() for line in str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned_lines: list[str] = []
    blank_streak = 0
    for line in lines:
        normalized = _normalize_line(line)
        if not normalized:
            blank_streak += 1
            if blank_streak <= 1:
                cleaned_lines.append("")
            continue
        blank_streak = 0
        if _should_drop_short_line(normalized):
            continue
        cleaned_lines.append(normalized)

    text = "\n".join(cleaned_lines).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def _should_drop_short_line(line: str) -> bool:
    if len(line) != 1:
        return False
    if line in {"-", "*", "•"}:
        return False
    category = unicodedata.category(line)
    return category.startswith(("P", "S"))


def _load_pdf(source: UploadedSource) -> list[DocumentChunk]:
    reader = PdfReader(str(source.path))
    documents: list[DocumentChunk] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = _clean_pdf_text(page.extract_text() or "")
        if text:
            documents.append(
                DocumentChunk(
                    page_content=text,
                    metadata={"source": source.original_name, "page": page_number},
                )
            )
    return documents


def _load_text(source: UploadedSource) -> list[DocumentChunk]:
    raw = source.path.read_bytes()
    text = None
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(
            f"无法识别文本文件编码：{source.original_name}。请将文件保存为 UTF-8 或 GBK/GB18030 后重试。"
        )
    normalized = text.strip()
    if not normalized:
        return []
    return [DocumentChunk(page_content=normalized, metadata={"source": source.original_name})]


def load_documents(files: Iterable[UploadedSource | Path]) -> list[DocumentChunk]:
    documents: list[DocumentChunk] = []
    for item in files:
        source = ensure_uploaded_source(item)
        suffix = source.path.suffix.lower()
        if suffix == ".pdf":
            documents.extend(_load_pdf(source))
        elif suffix in {".txt", ".md"}:
            documents.extend(_load_text(source))
    return documents

