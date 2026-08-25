"""Builds citation metadata (document, page, excerpt) from the chunks that
were actually sent to the LLM as context, and formats the context block with
inline source tags so the model can reference them by number.

The context block is also whitespace-normalized before it goes into the
prompt: PDF/DOCX extraction routinely produces runs of spaces and blank
lines that cost real input tokens without adding any information.
"""
from __future__ import annotations

import re

from app.services.retrieval.retriever import RetrievedChunk

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _compact(text: str) -> str:
    text = _MULTI_SPACE.sub(" ", text)
    return _MULTI_BLANK.sub("\n\n", text).strip()


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    lines = []
    for i, c in enumerate(chunks, start=1):
        filename = c.metadata.get("filename", "unknown")
        page = c.metadata.get("page_number", "?")
        section = c.metadata.get("section")
        label = f"[Source {i}] {filename} (page {page}"
        label += f", section: {section})" if section else ")"
        lines.append(f"{label}:\n{_compact(c.text)}")
    return "\n\n".join(lines)


def build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    citations = []
    for c in chunks:
        excerpt = c.text.strip()
        if len(excerpt) > 280:
            excerpt = excerpt[:277] + "..."
        score = c.relevance_score if c.relevance_score is not None else c.fused_score
        citations.append({
            "document_id": c.metadata.get("document_id", ""),
            "filename": c.metadata.get("filename", "unknown"),
            "page_number": c.metadata.get("page_number"),
            "section": c.metadata.get("section"),
            "excerpt": excerpt,
            "score": round(score, 4),
        })
    return citations
