from fastapi import APIRouter, Depends

from app.deps import get_doc_repo
from app.repositories.documents import DocumentRepository
from app.services.observability.metrics_service import get_metrics_service

router = APIRouter(prefix="/api/v1/metrics", tags=["Metrics"])


@router.delete("", summary="Clear recent request log (observability)")
def clear_metrics():
    metrics = get_metrics_service()
    with metrics._lock:
        metrics._recent.clear()
    return {"cleared": True}


@router.get("/summary", summary="Aggregate metrics for the observability panel")
def summary(doc_repo: DocumentRepository = Depends(get_doc_repo)):
    metrics = get_metrics_service()
    return metrics.summary(documents=len(doc_repo.list_all()), chunks=doc_repo.total_chunks)


@router.get("", summary="Recent request log")
def recent_requests():
    metrics = get_metrics_service()
    return [
        {
            "time": r.timestamp,
            "question": r.question,
            "latency_ms": r.latency_ms,
            "tokens": r.input_tokens + r.output_tokens,
            "cost_usd": r.estimated_cost_usd,
            "cache_hit": r.cache_hit,
            "model": r.model,
        }
        for r in metrics.recent
    ]
