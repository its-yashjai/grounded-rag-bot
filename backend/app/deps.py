"""Singleton wiring for FastAPI dependency injection. Keeping construction in
one place makes the service graph easy to see and easy to swap (e.g. Chroma
-> Qdrant) without hunting through route files."""
from __future__ import annotations

from functools import lru_cache

from app.agents.ingestion_agent import IngestionAgent
from app.config import Settings, get_settings
from app.repositories.documents import DocumentRepository, get_document_repository
from app.repositories.vectors import ChromaVectorStore, VectorStore
from app.services.cache.cache_service import CacheService, get_cache_service
from app.services.cost.cost_service import CostService
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.groq_service import GroqProvider
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.retriever import BM25Index, HybridRetriever


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return ChromaVectorStore(persist_dir=settings.chroma_persist_dir)


@lru_cache
def get_bm25_index() -> BM25Index:
    return BM25Index()


def get_cache(settings: Settings | None = None) -> CacheService:
    settings = settings or get_settings()
    return get_cache_service(default_ttl_s=settings.cache_ttl)


@lru_cache
def get_embedding_service() -> EmbeddingService:
    settings = get_settings()
    return EmbeddingService(
        model_name=settings.embedding_model,
        cache=get_cache(settings),
        enable_cache=settings.enable_embedding_cache,
    )


@lru_cache
def get_retriever() -> HybridRetriever:
    return HybridRetriever(get_vector_store(), get_embedding_service(), get_bm25_index())


@lru_cache
def get_reranker() -> Reranker:
    settings = get_settings()
    if settings.enable_cross_encoder_reranker:
        return Reranker()
    return Reranker()


@lru_cache
def get_cost_service() -> CostService:
    return CostService(get_settings())


@lru_cache
def get_llm_provider() -> GroqProvider:
    settings = get_settings()
    return GroqProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        fast_model=settings.groq_fast_model if settings.enable_model_routing else None,
        timeout_s=settings.groq_timeout_s,
        max_retries=settings.groq_max_retries,
    )


def get_doc_repo() -> DocumentRepository:
    return get_document_repository()


@lru_cache
def get_ingestion_agent() -> IngestionAgent:
    settings = get_settings()
    return IngestionAgent(
        settings=settings,
        doc_repo=get_doc_repo(),
        vector_store=get_vector_store(),
        embedder=get_embedding_service(),
        bm25=get_bm25_index(),
    )
