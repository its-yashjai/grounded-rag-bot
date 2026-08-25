"""
Lightweight structured logging + in-memory metrics collection, standing in
for a full OpenTelemetry exporter pipeline in this lean MVP. Every field
tracked here (latency, tokens, cache_hit, retrieved/reranked counts) maps
directly to what an `rag.request` OTel span would carry — swapping to real
OTel later means wrapping `record_request` with a span instead of an append.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from threading import Lock

logger = logging.getLogger("rag")
logging.basicConfig(level=logging.INFO)


@dataclass
class RequestLog:
    request_id: str
    question: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    cache_hit: bool
    retrieved_chunks: int
    reranked_chunks: int
    model: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


class MetricsService:
    def __init__(self, max_recent: int = 50):
        self._recent: list[RequestLog] = []
        self._lock = Lock()
        self.max_recent = max_recent

    def record_request(self, log: RequestLog) -> None:
        with self._lock:
            self._recent.insert(0, log)
            self._recent = self._recent[: self.max_recent]

        # Structured log line — never includes document text or API keys.
        logger.info(json.dumps({
            "event": "rag_request",
            "request_id": log.request_id,
            "latency_ms": log.latency_ms,
            "cache_hit": log.cache_hit,
            "retrieved_chunks": log.retrieved_chunks,
            "final_chunks": log.reranked_chunks,
            "input_tokens": log.input_tokens,
            "output_tokens": log.output_tokens,
            "estimated_cost_usd": log.estimated_cost_usd,
            "model": log.model,
        }))

    def clear(self) -> None:
        with self._lock:
            self._recent.clear()

    @property
    def recent(self) -> list[RequestLog]:
        return list(self._recent)

    def summary(self, documents: int, chunks: int) -> dict:
        with self._lock:
            n = len(self._recent)
            if n == 0:
                return {
                    "documents": documents, "chunks": chunks, "questions": 0,
                    "avg_latency_ms": 0.0, "cache_hit_rate": 0.0,
                    "total_tokens": 0, "estimated_cost_usd": 0.0,
                }
            avg_latency = sum(r.latency_ms for r in self._recent) / n
            hits = sum(1 for r in self._recent if r.cache_hit)
            total_tokens = sum(r.input_tokens + r.output_tokens for r in self._recent)
            total_cost = sum(r.estimated_cost_usd for r in self._recent)
            return {
                "documents": documents, "chunks": chunks, "questions": n,
                "avg_latency_ms": round(avg_latency, 1),
                "cache_hit_rate": round(hits / n, 3),
                "total_tokens": total_tokens,
                "estimated_cost_usd": round(total_cost, 6),
            }


_metrics_singleton: MetricsService | None = None


def get_metrics_service() -> MetricsService:
    global _metrics_singleton
    if _metrics_singleton is None:
        _metrics_singleton = MetricsService()
    return _metrics_singleton
