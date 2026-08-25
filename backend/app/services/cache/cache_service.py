"""
In-memory TTL cache standing in for Redis in this lean MVP.

The interface (get/set/delete) intentionally mirrors what a Redis-backed
implementation would expose, so swapping in `redis.asyncio` later is a
drop-in replacement for this class — nothing above this layer needs to change.

Four logical cache namespaces are used (see CacheService.for_namespace):
  - doc_hash:      file_hash -> document_id            (dedup)
  - embedding:     chunk_hash -> embedding vector       (avoid re-embedding)
  - retrieval:     query+kb_version -> chunk_ids        (avoid re-searching)
  - response:      query+kb_version -> answer+citations (avoid re-generating)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass
class _Entry:
    value: Any
    expires_at: float


class CacheService:
    def __init__(self, default_ttl_s: int = 600):
        self._store: dict[str, _Entry] = {}
        self._lock = Lock()
        self.default_ttl_s = default_ttl_s
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            if entry.expires_at < time.time():
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        with self._lock:
            self._store[key] = _Entry(
                value=value, expires_at=time.time() + (ttl_s or self.default_ttl_s)
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear_prefix(self, prefix: str) -> None:
        with self._lock:
            for k in [k for k in self._store if k.startswith(prefix)]:
                del self._store[k]

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total else 0.0


_cache_singleton: CacheService | None = None


def get_cache_service(default_ttl_s: int = 600) -> CacheService:
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = CacheService(default_ttl_s=default_ttl_s)
    return _cache_singleton
