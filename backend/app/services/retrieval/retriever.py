"""
Hybrid retrieval: semantic search (via the VectorStore) run alongside a
keyword search (BM25 over the in-memory chunk corpus), combined with
Reciprocal Rank Fusion. RRF is used instead of a weighted score blend because
semantic (cosine similarity) and BM25 scores live on different scales — RRF
sidesteps normalization issues by fusing on rank position instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from app.repositories.vectors import VectorStore
from app.services.embeddings.embedding_service import EmbeddingService


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    fused_score: float = 0.0
    # Set only by a reranker that scores actual query-chunk relevance (e.g.
    # CrossEncoderReranker), on a calibrated 0-1 scale. None when no such
    # reranker ran — callers should treat that as "no relevance signal",
    # not as "score of 0".
    relevance_score: float | None = None


class BM25Index:
    """Lightweight in-memory keyword index, rebuilt when the corpus changes.
    Adequate for hackathon-scale corpora; would move to Elasticsearch/OpenSearch
    at production scale."""

    def __init__(self):
        self._corpus_ids: list[str] = []
        self._corpus_texts: list[str] = []
        self._corpus_meta: list[dict] = []
        self._bm25: BM25Okapi | None = None

    def add(self, chunk_id: str, text: str, metadata: dict) -> None:
        self._corpus_ids.append(chunk_id)
        self._corpus_texts.append(text)
        self._corpus_meta.append(metadata)
        self._bm25 = None  # invalidate; rebuilt lazily on next search

    def remove_document(self, document_id: str) -> None:
        keep = [
            i for i, m in enumerate(self._corpus_meta)
            if m.get("document_id") != document_id
        ]
        self._corpus_ids = [self._corpus_ids[i] for i in keep]
        self._corpus_texts = [self._corpus_texts[i] for i in keep]
        self._corpus_meta = [self._corpus_meta[i] for i in keep]
        self._bm25 = None

    def set_filename(self, document_id: str, filename: str) -> None:
        """Keep citation labels correct after a document rename."""
        for m in self._corpus_meta:
            if m.get("document_id") == document_id:
                m["filename"] = filename
        # metadata is not part of the index; no invalidation needed

    def _ensure_index(self):
        if self._bm25 is None and self._corpus_texts:
            tokenized = [t.lower().split() for t in self._corpus_texts]
            self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if not self._corpus_texts:
            return []
        self._ensure_index()
        scores = self._bm25.get_scores(query.lower().split())
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        out = []
        max_score = max(scores) if len(scores) else 1.0
        for i in ranked:
            if scores[i] <= 0:
                continue
            out.append(RetrievedChunk(
                chunk_id=self._corpus_ids[i],
                text=self._corpus_texts[i],
                metadata=self._corpus_meta[i],
                keyword_score=float(scores[i] / max_score) if max_score else 0.0,
            ))
        return out


def reciprocal_rank_fusion(
    semantic: list[RetrievedChunk], keyword: list[RetrievedChunk], k: int = 60
) -> list[RetrievedChunk]:
    fused: dict[str, RetrievedChunk] = {}

    for rank, item in enumerate(semantic):
        entry = fused.setdefault(item.chunk_id, item)
        entry.semantic_score = item.semantic_score
        entry.fused_score += 1.0 / (k + rank + 1)

    for rank, item in enumerate(keyword):
        entry = fused.get(item.chunk_id)
        if entry is None:
            entry = item
            fused[item.chunk_id] = entry
        entry.keyword_score = item.keyword_score
        entry.fused_score += 1.0 / (k + rank + 1)

    return sorted(fused.values(), key=lambda c: c.fused_score, reverse=True)


class HybridRetriever:
    def __init__(self, vector_store: VectorStore, embedder: EmbeddingService, bm25: BM25Index):
        self.vector_store = vector_store
        self.embedder = embedder
        self.bm25 = bm25

    def retrieve(self, query: str, top_k: int, document_ids: list[str] | None = None) -> list[RetrievedChunk]:
        where = {"document_id": {"$in": document_ids}} if document_ids else None

        query_embedding = self.embedder.embed_query(query)
        semantic_hits = [
            RetrievedChunk(
                chunk_id=r["chunk_id"], text=r["text"], metadata=r["metadata"],
                semantic_score=r["semantic_score"],
            )
            for r in self.vector_store.search(query_embedding, top_k=top_k, where=where)
        ]

        keyword_hits = self.bm25.search(query, top_k=top_k)
        if document_ids:
            keyword_hits = [h for h in keyword_hits if h.metadata.get("document_id") in document_ids]

        return reciprocal_rank_fusion(semantic_hits, keyword_hits)[:top_k]
