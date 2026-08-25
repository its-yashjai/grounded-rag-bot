"""
Structure-aware chunking: packs blocks (paragraphs, list items, tables) into
chunks up to `chunk_size` tokens, only falling back to a hard character split
for single blocks that exceed the limit on their own.

Two structure signals now come from extraction (via `unstructured`) rather
than being inferred from raw text:
  - `section`: a block never merges into a chunk started under a different
    section heading, so a chunk can't silently straddle two unrelated
    sections of the document.
  - `is_table`: a table block is treated as atomic — it is never merged with
    surrounding paragraphs (mixing prose and tabular data in one chunk hurts
    retrieval for both), and never split by the overlap logic. It can still
    be hard-split if it alone exceeds chunk_size.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.ingestion.extractor import Block
from app.utils.tokens import count_tokens


@dataclass
class Chunk:
    text: str
    page_number: int
    chunk_index: int
    section: str | None = None
    is_table: bool = False


def chunk_pages(blocks: list[Block], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    buffer = ""
    buffer_page: int | None = None
    buffer_section: str | None = None

    def flush() -> str:
        """Flush the buffer to a Chunk and return its text (for computing
        the overlap tail *before* the buffer is cleared)."""
        nonlocal buffer, buffer_page, buffer_section, idx
        flushed_text = buffer
        if buffer.strip():
            chunks.append(Chunk(
                text=buffer.strip(), page_number=buffer_page or 1,
                chunk_index=idx, section=buffer_section,
            ))
            idx += 1
        buffer = ""
        return flushed_text

    def flush_table(block: Block) -> None:
        nonlocal idx
        for piece in ([block.text] if count_tokens(block.text) <= chunk_size
                       else _hard_split(block.text, chunk_size)):
            chunks.append(Chunk(
                text=piece.strip(), page_number=block.page_number,
                chunk_index=idx, section=block.section, is_table=True,
            ))
            idx += 1

    for block in blocks:
        if block.is_table:
            if buffer:
                flush()
                buffer_page = None
                buffer_section = None
            flush_table(block)
            continue

        if buffer_page is None:
            buffer_page = block.page_number
            buffer_section = block.section

        section_changed = buffer and block.section != buffer_section
        candidate = f"{buffer}\n\n{block.text}".strip() if buffer else block.text

        if not section_changed and count_tokens(candidate) <= chunk_size:
            buffer = candidate
            continue

        # Buffer is full, or the section changed — flush, then start a new
        # buffer, carrying an overlap tail forward *unless* the section
        # changed (overlapping across unrelated sections isn't useful).
        if buffer:
            flushed_text = flush()
            overlap_text = (
                _tail_by_tokens(flushed_text, chunk_overlap)
                if chunk_overlap and not section_changed else ""
            )
            buffer = f"{overlap_text}\n\n{block.text}".strip() if overlap_text else block.text
            buffer_page = block.page_number
            buffer_section = block.section
        else:
            # single block bigger than chunk_size on its own: hard split
            for piece in _hard_split(block.text, chunk_size):
                chunks.append(Chunk(
                    text=piece, page_number=block.page_number,
                    chunk_index=idx, section=block.section,
                ))
                idx += 1
            buffer = ""
            buffer_page = None
            buffer_section = None

    flush()
    return chunks


def _tail_by_tokens(text: str, max_tokens: int) -> str:
    words = text.split()
    tail: list[str] = []
    for w in reversed(words):
        tail.insert(0, w)
        if count_tokens(" ".join(tail)) >= max_tokens:
            break
    return " ".join(tail)


def _hard_split(text: str, chunk_size: int) -> list[str]:
    words = text.split()
    pieces, cur = [], []
    for w in words:
        cur.append(w)
        if count_tokens(" ".join(cur)) >= chunk_size:
            pieces.append(" ".join(cur))
            cur = []
    if cur:
        pieces.append(" ".join(cur))
    return pieces
