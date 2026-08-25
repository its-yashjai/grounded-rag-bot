"""
VectorStore abstraction. Business logic never touches Chroma directly — it
goes through this interface, so swapping Chroma for Qdrant/pgvector later
only means writing a new class that implements the same four methods.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    @abstractmethod
    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str],
    ) -> None:
        ...

    @abstractmethod
    def search(
        self,
        embedding: list[float],
        top_k: int,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def delete(self, document_id: str) -> None:
        ...

    @abstractmethod
    def patch_metadata(self, document_id: str, key: str, value) -> None:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...


class ChromaVectorStore(VectorStore):
    def __init__(
        self,
        persist_dir: str,
        collection_name: str = "chunks",
    ):
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids,
        embeddings,
        metadatas,
        documents,
    ) -> None:
        if not ids:
            return

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    def search(
        self,
        embedding,
        top_k,
        where=None,
    ) -> list[dict[str, Any]]:
        if self._collection.count() == 0:
            return []

        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, self._collection.count()),
            where=where,
        )

        out = []

        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        for i in range(len(ids)):
            # Cosine distance -> similarity score in [0, 1]
            similarity = max(0.0, 1.0 - dists[i])

            out.append(
                {
                    "chunk_id": ids[i],
                    "text": docs[i],
                    "metadata": metas[i],
                    "semantic_score": similarity,
                }
            )

        return out

    def delete(self, document_id: str) -> None:
        self._collection.delete(
            where={"document_id": document_id}
        )

    def patch_metadata(
        self,
        document_id: str,
        key: str,
        value,
    ) -> None:
        got = self._collection.get(
            where={"document_id": document_id}
        )

        ids = got.get("ids", [])

        if not ids:
            return

        metas = [
            dict(m or {}, **{key: value})
            for m in got.get("metadatas", [])
        ]

        self._collection.update(
            ids=ids,
            metadatas=metas,
        )

    def health_check(self) -> bool:
        try:
            self._collection.count()
            return True
        except Exception:
            return False