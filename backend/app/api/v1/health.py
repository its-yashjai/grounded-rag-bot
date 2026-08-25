from fastapi import APIRouter, Depends

from app.deps import get_vector_store
from app.repositories.vectors import VectorStore

router = APIRouter(prefix="/api/v1/health", tags=["Health"])


@router.get("/live", summary="Liveness probe (never depends on external services)")
def live():
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe (checks vector store connectivity)")
def ready(vector_store: VectorStore = Depends(get_vector_store)):
    healthy = vector_store.health_check()
    return {"status": "ok" if healthy else "degraded", "vector_store": healthy}


@router.get("", summary="Basic health status")
def health():
    return {"status": "ok"}
