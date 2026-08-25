"""Pre-download models that would otherwise be fetched lazily on first
request (embedding model, cross-encoder reranker, and — if enabled — the
unstructured hi_res table-layout model). Run this at `docker build` time,
not at container startup: build time has normal internet egress and a
build-time failure is visible immediately, whereas a runtime download
failure would surface as a broken answer live in front of a judge.

Usage: python scripts/warm_models.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings  # noqa: E402


def warm_embedding_model(model_name: str) -> None:
    from sentence_transformers import SentenceTransformer
    print(f"[warm_models] downloading embedding model: {model_name}")
    SentenceTransformer(model_name)


def warm_cross_encoder(model_name: str) -> None:
    from sentence_transformers import CrossEncoder
    print(f"[warm_models] downloading cross-encoder: {model_name}")
    CrossEncoder(model_name)


def warm_table_layout_model() -> None:
    # Triggers the same hi_res layout-model download that
    # partition_pdf(infer_table_structure=True) would trigger lazily.
    from unstructured.partition.pdf import partition_pdf
    import tempfile

    print("[warm_models] downloading unstructured hi_res layout model")
    # A minimal blank PDF is enough to force model initialization; content
    # doesn't matter, only that the hi_res code path runs once. Built with
    # pypdf rather than a heavier PDF library, since pypdf is already a
    # guaranteed transitive dependency of unstructured[pdf] — no new
    # dependency needed just to build a throwaway warm-up file.
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        writer.write(f.name)
        path = f.name
    partition_pdf(path, strategy="hi_res", infer_table_structure=True)


if __name__ == "__main__":
    settings = get_settings()
    warm_embedding_model(settings.embedding_model)
    if settings.enable_cross_encoder_reranker:
        warm_cross_encoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    if settings.enable_table_extraction:
        warm_table_layout_model()
    print("[warm_models] done")
