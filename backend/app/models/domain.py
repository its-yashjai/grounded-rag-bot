"""In-process data models for documents/chunks. Kept as plain dataclasses so the
storage layer (currently in-memory + Chroma) can be swapped for Postgres later
without touching business logic (see repositories/documents.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ProcessingStatus(str, Enum):
    UPLOADING = "uploading"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class DocumentRecord:
    document_id: str
    filename: str
    file_type: str
    file_size: int
    content_hash: str
    upload_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    page_count: int = 0
    chunk_count: int = 0
    processing_status: ProcessingStatus = ProcessingStatus.UPLOADING
    processing_duration_ms: float | None = None
    embedding_model: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["upload_time"] = self.upload_time.isoformat()
        d["processing_status"] = self.processing_status.value
        return d
