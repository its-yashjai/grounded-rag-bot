"""
Document endpoints. Upload validates each file, computes a content hash for
dedup, then runs ingestion. Files are processed concurrently via a bounded
thread pool (ingestion is CPU-bound: PDF/DOCX parsing via `unstructured` +
embedding), since neither the embedding model nor `unstructured` is
async-native.
"""
from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.agents.ingestion_agent import IngestionAgent
from app.config import Settings, get_settings
from app.deps import get_bm25_index, get_doc_repo, get_ingestion_agent, get_vector_store
from app.models.domain import DocumentRecord, ProcessingStatus
from app.repositories.documents import DocumentRepository
from app.repositories.vectors import VectorStore
from app.schemas.api import DocumentOut, UploadResponse
from app.services.retrieval.retriever import BM25Index
from app.utils.hashing import new_id, sha256_bytes

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])

ALLOWED_TYPES = {"pdf", "docx", "txt"}
_executor = ThreadPoolExecutor(max_workers=4)


class DocumentRenameIn(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)


def _to_out(record: DocumentRecord) -> DocumentOut:
    d = record.to_dict()
    return DocumentOut(**d)


@router.post("/upload", response_model=UploadResponse, summary="Upload one or more documents")
async def upload_documents(
    files: list[UploadFile],
    settings: Settings = Depends(get_settings),
    doc_repo: DocumentRepository = Depends(get_doc_repo),
    ingestion_agent: IngestionAgent = Depends(get_ingestion_agent),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    os.makedirs(settings.upload_dir, exist_ok=True)
    loop = asyncio.get_event_loop()
    tasks = []

    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else ""
        if ext not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {f.filename}")

        content = await f.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > settings.max_file_size_mb:
            raise HTTPException(
                status_code=400,
                detail=f"{f.filename} exceeds max size of {settings.max_file_size_mb}MB.",
            )

        content_hash = sha256_bytes(content)
        existing = doc_repo.find_by_hash(content_hash)
        if existing:
            tasks.append(asyncio.sleep(0, result=existing))
            continue

        safe_name = os.path.basename(f.filename or "upload")
        document_id = new_id("doc")
        dest_path = os.path.join(settings.upload_dir, f"{document_id}_{safe_name}")
        with open(dest_path, "wb") as out:
            out.write(content)

        record = DocumentRecord(
            document_id=document_id,
            filename=safe_name,
            file_type=ext,
            file_size=len(content),
            content_hash=content_hash,
            processing_status=ProcessingStatus.UPLOADING,
        )
        tasks.append(
            loop.run_in_executor(_executor, ingestion_agent.ingest, record, dest_path)
        )

    results = await asyncio.gather(*tasks)
    return UploadResponse(documents=[_to_out(r) for r in results])


@router.get("", response_model=list[DocumentOut], summary="List all uploaded documents")
def list_documents(doc_repo: DocumentRepository = Depends(get_doc_repo)):
    return [_to_out(r) for r in doc_repo.list_all()]


@router.get("/{document_id}", response_model=DocumentOut, summary="Get one document")
def get_document(document_id: str, doc_repo: DocumentRepository = Depends(get_doc_repo)):
    rec = doc_repo.get(document_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _to_out(rec)


@router.get("/{document_id}/status", summary="Poll processing status for a document")
def get_status(document_id: str, doc_repo: DocumentRepository = Depends(get_doc_repo)):
    rec = doc_repo.get(document_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"document_id": document_id, "status": rec.processing_status.value, "error": rec.error}


@router.delete("/{document_id}", summary="Delete a document and its vectors")
def delete_document(
    document_id: str,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
    vector_store: VectorStore = Depends(get_vector_store),
    bm25: BM25Index = Depends(get_bm25_index),
):
    rec = doc_repo.get(document_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found.")
    vector_store.delete(document_id)
    bm25.remove_document(document_id)
    doc_repo.delete(document_id)
    return {"deleted": document_id}


@router.patch("/{document_id}", summary="Rename a document across all indexes")
def rename_document(
    document_id: str,
    payload: DocumentRenameIn,
    doc_repo: DocumentRepository = Depends(get_doc_repo),
    vector_store: VectorStore = Depends(get_vector_store),
    bm25: BM25Index = Depends(get_bm25_index),
):
    rec = doc_repo.get(document_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found.")
    new_name = os.path.basename(payload.filename.strip())
    if not new_name:
        raise HTTPException(status_code=400, detail="Filename cannot be empty.")
    rec.filename = new_name
    doc_repo.upsert(rec)
    doc_repo.set_chunk_filename(document_id, new_name)  # persisted corpus
    bm25.set_filename(document_id, new_name)            # keyword index
    vector_store.patch_metadata(document_id, "filename", new_name)  # vectors
    return _to_out(rec)
