"""Extracts structured blocks from PDF/DOCX/TXT via `unstructured`, so
downstream chunking can retain page numbers, section headings, and element
type (paragraph vs. table vs. list) for citations and section-aware chunking.

Strategy choice matters for two reasons, both verified against the installed
`unstructured` version rather than assumed:
  - `strategy="auto"` without `infer_table_structure` stays on the fast
    (pdfminer-based) path when a text layer exists, and falls back to OCR
    (tesseract) automatically when it doesn't. No network access required.
  - `infer_table_structure=True` forces the "hi_res" path, which downloads a
    layout-detection model from huggingface.co on first use. If the
    deployment environment has no egress to Hugging Face (or the model
    isn't pre-cached into the image at build time), table extraction fails
    at request time. It is therefore opt-in via `enable_table_extraction`,
    not the default.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


@dataclass
class Block:
    text: str
    page_number: int
    category: str = "NarrativeText"  # Title, NarrativeText, ListItem, Table, ...
    section: str | None = None        # nearest enclosing section title, if any
    is_table: bool = False


class ExtractionError(Exception):
    pass


def _elements_to_blocks(elements) -> list[Block]:
    """Flatten unstructured Elements into Blocks, resolving each element's
    section title via its parent_id chain back to the nearest Title."""
    by_id = {el.id: el for el in elements}

    def _section_for(el) -> str | None:
        pid = getattr(el.metadata, "parent_id", None)
        seen = set()
        while pid and pid in by_id and pid not in seen:
            seen.add(pid)
            parent = by_id[pid]
            if parent.category == "Title":
                return str(parent).strip()
            pid = getattr(parent.metadata, "parent_id", None)
        return None

    blocks: list[Block] = []
    for el in elements:
        text = str(el).strip()
        if not text:
            continue
        page_number = getattr(el.metadata, "page_number", None) or 1
        is_table = el.category == "Table"
        if is_table:
            # Prefer the HTML table representation when the hi_res path
            # produced one (only present if infer_table_structure=True);
            # otherwise fall back to the plain extracted text.
            html = getattr(el.metadata, "text_as_html", None)
            text = html or text
        blocks.append(Block(
            text=text,
            page_number=page_number,
            category=el.category,
            section=_section_for(el),
            is_table=is_table,
        ))
    return blocks


def extract_pdf(path: str, enable_table_extraction: bool = False) -> list[Block]:
    from unstructured.partition.pdf import partition_pdf

    try:
        elements = partition_pdf(
            path,
            strategy="auto",
            infer_table_structure=enable_table_extraction,
        )
    except Exception as e:
        raise ExtractionError(f"Failed to extract PDF: {e}") from e
    return _elements_to_blocks(elements)


def extract_docx(path: str) -> list[Block]:
    from unstructured.partition.docx import partition_docx

    try:
        elements = partition_docx(path)
    except Exception as e:
        raise ExtractionError(f"Failed to extract DOCX: {e}") from e
    blocks = _elements_to_blocks(elements)
    # DOCX has no native pagination; keep the existing "page 1" convention
    # so citations don't regress to showing "page None".
    for b in blocks:
        b.page_number = b.page_number or 1
    return blocks


def extract_txt(path: str) -> list[Block]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        raise ExtractionError(f"Failed to read TXT: {e}") from e
    if not text.strip():
        return []
    # No title/section structure available for plain text, but the chunker
    # now expects pre-split, roughly-atomic blocks (matching what PDF/DOCX
    # extraction produces via unstructured), so paragraphs are split here.
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    return [Block(text=p, page_number=1, category="NarrativeText") for p in paragraphs]


def extract(path: str, file_type: str, enable_table_extraction: bool = False) -> list[Block]:
    file_type = file_type.lower().lstrip(".")
    if file_type == "pdf":
        return extract_pdf(path, enable_table_extraction=enable_table_extraction)
    if file_type == "docx":
        return extract_docx(path)
    if file_type == "txt":
        return extract_txt(path)
    raise ExtractionError(f"Unsupported file type: {file_type}")
