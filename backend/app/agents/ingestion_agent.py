"""
Ingestion Agent — deterministic pipeline, no LLM calls. Validates, extracts,
chunks, embeds (batched), and stores into both the vector store and the BM25
keyword index, updating document metadata/status at each stage so the
frontend can show live progress.
"""
from __future__ import annotations

import time

from app.config import Settings
from app.models.domain import DocumentRecord, ProcessingStatus
from app.repositories.documents import DocumentRepository
from app.repositories.vectors import VectorStore
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.ingestion.chunker import chunk_pages
from app.services.ingestion.extractor import ExtractionError, extract
from app.services.retrieval.retriever import BM25Index
from app.utils.hashing import new_id


class IngestionAgent:
    def __init__(
        self,
        settings: Settings,
        doc_repo: DocumentRepository,
        vector_store: VectorStore,
        embedder: EmbeddingService,
        bm25: BM25Index,
    ):
        self.settings = settings
        self.doc_repo = doc_repo
        self.vector_store = vector_store
        self.embedder = embedder
        self.bm25 = bm25

    def ingest(self, record: DocumentRecord, file_path: str) -> DocumentRecord:
        start = time.perf_counter()
        try:
            record.processing_status = ProcessingStatus.EXTRACTING
            self.doc_repo.upsert(record)
            blocks = extract(
                file_path, record.file_type,
                enable_table_extraction=self.settings.enable_table_extraction,
            )
            record.page_count = len({b.page_number for b in blocks})

            record.processing_status = ProcessingStatus.CHUNKING
            self.doc_repo.upsert(record)
            chunks = chunk_pages(blocks, self.settings.chunk_size, self.settings.chunk_overlap)
            if not chunks:
                raise ExtractionError("No extractable text found in document.")

            record.processing_status = ProcessingStatus.EMBEDDING
            self.doc_repo.upsert(record)
            texts = [c.text for c in chunks]
            embeddings = self.embedder.embed_batch(texts)

            record.processing_status = ProcessingStatus.INDEXING
            self.doc_repo.upsert(record)

            ids, metadatas = [], []
            for c in chunks:
                chunk_id = new_id("chunk")
                meta = {
                    "document_id": record.document_id,
                    "filename": record.filename,
                    "page_number": c.page_number,
                    "chunk_index": c.chunk_index,
                    "is_table": c.is_table,
                }
                # Chroma's metadata typing rejects None outright (confirmed:
                # raises TypeError on collection.add), so section is only
                # included when a chunk actually has one — e.g. TXT-derived
                # chunks and top-of-document chunks before any heading never
                # will. citation_service already treats a missing "section"
                # key the same as one present-but-empty, so this is safe.
                if c.section is not None:
                    meta["section"] = c.section
                ids.append(chunk_id)
                metadatas.append(meta)
                self.bm25.add(chunk_id, c.text, meta)

            # Persisted corpus: lets BM25 be rebuilt after a restart
            # (Chroma persists its own vectors; this covers the keyword side).
            self.doc_repo.add_chunks(
                record.document_id, list(zip(ids, texts, metadatas))
            )

            self.vector_store.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=texts)

            record.chunk_count = len(chunks)
            record.embedding_model = self.settings.embedding_model
            record.processing_status = ProcessingStatus.READY
            record.processing_duration_ms = round((time.perf_counter() - start) * 1000, 1)
            self.doc_repo.upsert(record)
            return record

        except Exception as e:  # noqa: BLE001 — surfaced to the user via record.error
            record.processing_status = ProcessingStatus.FAILED
            record.error = str(e)
            record.processing_duration_ms = round((time.perf_counter() - start) * 1000, 1)
            self.doc_repo.upsert(record)
            return record
