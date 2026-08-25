"""
Embedding generation, batched, with a content-hash cache in front of it so an
identical chunk of text (across documents, or re-uploaded) never gets
re-embedded. Model loads lazily on first use and is reused for the process
lifetime.
"""
from __future__ import annotations

from app.services.cache.cache_service import CacheService
from app.utils.hashing import sha256_text

_model = None


def _get_model(model_name: str):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(model_name)
    return _model


class EmbeddingService:
    def __init__(self, model_name: str, cache: CacheService, enable_cache: bool = True):
        self.model_name = model_name
        self.cache = cache
        self.enable_cache = enable_cache

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        to_embed_idx: list[int] = []
        to_embed_texts: list[str] = []

        for i, text in enumerate(texts):
            if self.enable_cache:
                key = f"embedding:{self.model_name}:{sha256_text(text)}"
                cached = self.cache.get(key)
                if cached is not None:
                    results[i] = cached
                    continue
            to_embed_idx.append(i)
            to_embed_texts.append(text)

        if to_embed_texts:
            model = _get_model(self.model_name)
            vectors = model.encode(to_embed_texts, batch_size=32, show_progress_bar=False)
            for idx, text, vec in zip(to_embed_idx, to_embed_texts, vectors):
                vec_list = vec.tolist()
                results[idx] = vec_list
                if self.enable_cache:
                    key = f"embedding:{self.model_name}:{sha256_text(text)}"
                    self.cache.set(key, vec_list, ttl_s=None)

        return results  # type: ignore[return-value]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]
