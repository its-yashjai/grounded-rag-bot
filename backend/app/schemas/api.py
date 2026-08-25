"""Request/response schemas for the API layer. Keeping these separate from
`models/domain.py` lets the wire format evolve independently of storage."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    document_id: str
    filename: str
    file_type: str
    file_size: int
    page_count: int
    chunk_count: int
    processing_status: str
    processing_duration_ms: float | None = None
    upload_time: str
    error: str | None = None


class UploadResponse(BaseModel):
    documents: list[DocumentOut]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    document_ids: list[str] | None = None
    conversation_id: str | None = None


class Citation(BaseModel):
    document_id: str
    filename: str
    page_number: int | None
    excerpt: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    request_id: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    cache_hit: bool
    retrieved_chunks: int
    reranked_chunks: int


class MetricsSummary(BaseModel):
    documents: int
    chunks: int
    questions: int
    avg_latency_ms: float
    cache_hit_rate: float
    total_tokens: int
    estimated_cost_usd: float


class RecentRequest(BaseModel):
    time: str
    question: str
    latency_ms: float
    tokens: int
    cost_usd: float
    cache_hit: bool
