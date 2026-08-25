"""
Document metadata repository. In-memory for speed, backed by a JSON store on
disk so the knowledge base (documents + chunk corpus) survives restarts —
Chroma persists vectors, this file persists everything BM25 and the UI need.
The dataclass shape maps 1:1 to a future Postgres table.

Also tracks a single `knowledge_base_version` that increments whenever the
document set changes, which the cache layer uses as a cheap invalidation key.
"""
from __future__ import annotations

from datetime import datetime
from threading import Lock

from app.models.domain import DocumentRecord, ProcessingStatus
from app.services.persistence.json_store import JsonStore


class DocumentRepository:
    def __init__(self, store_path: str | None = None):
        self._docs: dict[str, DocumentRecord] = {}
        self._hash_index: dict[str, str] = {}  # content_hash -> document_id
        self._chunks: dict[str, dict] = {}  # chunk_id -> {text, metadata}
        self._lock = Lock()
        self.kb_version = 1
        self._store = JsonStore(store_path) if store_path else None
        if self._store:
            self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        data = self._store.load({"documents": [], "chunks": {}})
        for d in data.get("documents", []):
            try:
                rec = DocumentRecord(
                    document_id=d["document_id"],
                    filename=d["filename"],
                    file_type=d["file_type"],
                    file_size=d["file_size"],
                    content_hash=d["content_hash"],
                    upload_time=datetime.fromisoformat(d["upload_time"]),
                    page_count=d.get("page_count", 0),
                    chunk_count=d.get("chunk_count", 0),
                    processing_status=ProcessingStatus(d.get("processing_status", "ready")),
                    processing_duration_ms=d.get("processing_duration_ms"),
                    embedding_model=d.get("embedding_model", ""),
                    error=d.get("error"),
                )
            except Exception:  # noqa: BLE001 — skip corrupt rows, never block startup
                continue
            self._docs[rec.document_id] = rec
            self._hash_index[rec.content_hash] = rec.document_id
        self._chunks = data.get("chunks", {})

    def _save(self) -> None:
        if not self._store:
            return
        data = {
            "documents": [self._serialize(r) for r in self._docs.values()],
            "chunks": self._chunks,
        }
        try:
            self._store.save(data)
        except OSError:
            pass  # persistence is best-effort; serving never fails because of it

    @staticmethod
    def _serialize(rec: DocumentRecord) -> dict:
        return {
            "document_id": rec.document_id,
            "filename": rec.filename,
            "file_type": rec.file_type,
            "file_size": rec.file_size,
            "content_hash": rec.content_hash,
            "upload_time": rec.upload_time.isoformat(),
            "page_count": rec.page_count,
            "chunk_count": rec.chunk_count,
            "processing_status": rec.processing_status.value,
            "processing_duration_ms": rec.processing_duration_ms,
            "embedding_model": rec.embedding_model,
            "error": rec.error,
        }

    # ---------- documents ----------

    def find_by_hash(self, content_hash: str) -> DocumentRecord | None:
        with self._lock:
            doc_id = self._hash_index.get(content_hash)
            return self._docs.get(doc_id) if doc_id else None

    def upsert(self, record: DocumentRecord) -> None:
        with self._lock:
            self._docs[record.document_id] = record
            self._hash_index[record.content_hash] = record.document_id
            self.kb_version += 1
            self._save()

    def get(self, document_id: str) -> DocumentRecord | None:
        return self._docs.get(document_id)

    def list_all(self) -> list[DocumentRecord]:
        return sorted(self._docs.values(), key=lambda d: d.upload_time, reverse=True)

    def delete(self, document_id: str) -> None:
        with self._lock:
            rec = self._docs.pop(document_id, None)
            if rec:
                self._hash_index.pop(rec.content_hash, None)
                self.kb_version += 1
            self._chunks = {
                cid: c for cid, c in self._chunks.items()
                if c["metadata"].get("document_id") != document_id
            }
            self._save()

    @property
    def total_chunks(self) -> int:
        return sum(d.chunk_count for d in self._docs.values())

    # ---------- chunk corpus (rebuilds BM25 after restarts) ----------

    def add_chunks(self, document_id: str, chunks: list[tuple[str, str, dict]]) -> None:
        """Register (chunk_id, text, metadata) triples for the persisted corpus."""
        with self._lock:
            for cid, text, meta in chunks:
                self._chunks[cid] = {"text": text, "metadata": meta}
            self.kb_version += 1
            self._save()

    def all_chunks(self) -> list[tuple[str, str, dict]]:
        return [(cid, c["text"], c["metadata"]) for cid, c in self._chunks.items()]

    def set_chunk_filename(self, document_id: str, filename: str) -> None:
        """Propagate a rename into the persisted chunk corpus."""
        with self._lock:
            for c in self._chunks.values():
                if c["metadata"].get("document_id") == document_id:
                    c["metadata"]["filename"] = filename
            self._save()


_repo_singleton: DocumentRepository | None = None


def get_document_repository() -> DocumentRepository:
    global _repo_singleton
    if _repo_singleton is None:
        from app.config import get_settings
        settings = get_settings()
        import os
        store_path = os.path.join(settings.chroma_persist_dir, "..", "store", "knowledge_base.json")
        _repo_singleton = DocumentRepository(os.path.normpath(store_path))
    return _repo_singleton
