"""
Reranking stage.

`Reranker` (base): dedup (near-identical chunks) + selecting the top-N by
fused RRF score, staying within the token budget. No relevance judgment of
its own — RRF's fused_score reflects rank position across retrieval lists,
not whether a chunk actually answers the query.

`CrossEncoderReranker`: rescores every candidate against the query with a
cross-encoder and sorts on that instead. This is the actual precision
improvement — RRF decides who gets *considered*, the cross-encoder decides
who's *relevant*. Its raw output is an unbounded logit, not a 0-1 score, so
it's passed through a sigmoid into `relevance_score` before sorting/dedup,
making it interpretable (0.5 = model finds it more likely relevant than
not) and giving the grounding guard a stable scale to threshold on
regardless of the underlying model's logit range.
"""
from __future__ import annotations

import math

from app.services.retrieval.retriever import RetrievedChunk
from app.utils.hashing import sha256_text
from app.utils.tokens import count_tokens


class Reranker:
    def rerank(
        self, chunks: list[RetrievedChunk], top_k: int, max_context_tokens: int, query: str = ""
    ) -> list[RetrievedChunk]:
        seen_hashes: set[str] = set()
        deduped: list[RetrievedChunk] = []
        for c in chunks:
            h = sha256_text(c.text.strip().lower())
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            deduped.append(c)

        selected: list[RetrievedChunk] = []
        token_budget = max_context_tokens
        # Scan the full deduped candidate pool, not an arbitrary multiple of
        # top_k — with a wide candidate pool (e.g. top_k=40 at retrieval),
        # capping the scan window here would silently discard most of it
        # before it's ever considered.
        for c in deduped:
            if len(selected) >= top_k:
                break
            t = count_tokens(c.text)
            if t > token_budget and selected:
                continue
            selected.append(c)
            token_budget -= t

        return selected


class CrossEncoderReranker(Reranker):
    """Cross-encoder reranker using sentence-transformers. The model is
    downloaded from Hugging Face on first use unless pre-cached — see
    scripts/warm_models.py, which the Dockerfile runs at build time so the
    container never needs network access for this at runtime."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, chunks, top_k, max_context_tokens, query: str = ""):  # type: ignore[override]
        if not chunks or not query:
            return super().rerank(chunks, top_k, max_context_tokens)

        model = self._get_model()
        pairs = [(query, c.text) for c in chunks]
        raw_scores = model.predict(pairs)

        for c, s in zip(chunks, raw_scores):
            c.relevance_score = 1.0 / (1.0 + math.exp(-float(s)))

        chunks.sort(key=lambda c: c.relevance_score, reverse=True)

        return super().rerank(chunks, top_k, max_context_tokens)