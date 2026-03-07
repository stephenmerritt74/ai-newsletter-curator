"""ChromaDB vector store interface."""

import logging
from pathlib import Path

import chromadb
from chromadb import Collection

from src.config import settings
from src.exceptions import StorageError
from src.models import EmbeddedChunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "newsletter_chunks"


class VectorStore:
    """Thin wrapper around a ChromaDB collection for newsletter chunks."""

    def __init__(self, db_path: Path | None = None) -> None:
        path = db_path or settings.chroma_db_path
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._collection: Collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[EmbeddedChunk]) -> list[str]:
        """Insert embedded chunks into the collection.

        Args:
            chunks: List of EmbeddedChunk objects to persist.

        Returns:
            List of ChromaDB IDs assigned to the inserted chunks.

        Raises:
            StorageError: If the ChromaDB upsert fails.
        """
        if not chunks:
            return []

        ids = [
            f"{c.chunk.email_message_id}__{c.chunk.chunk_index}" for c in chunks
        ]
        embeddings = [c.embedding for c in chunks]
        documents = [c.chunk.text for c in chunks]
        metadatas = [
            {
                "email_message_id": c.chunk.email_message_id,
                "chunk_index": c.chunk.chunk_index,
                "token_count": c.chunk.token_count,
                "model": c.model,
                **c.metadata,  # merge extra metadata (type, title, url, etc.)
            }
            for c in chunks
        ]

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        except Exception as exc:
            raise StorageError(f"Failed to upsert chunks into ChromaDB: {exc}") from exc

        logger.info("Upserted %d chunks into ChromaDB", len(chunks))
        return ids

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        """Search for the nearest chunks to a query embedding.

        Args:
            query_embedding: The query vector.
            n_results: Number of results to return.
            filters: Optional ChromaDB where-clause filter dict.

        Returns:
            List of result dicts with keys: id, document, metadata, distance.

        Raises:
            StorageError: If the ChromaDB query fails.
        """
        kwargs: dict = {"query_embeddings": [query_embedding], "n_results": n_results}
        if filters:
            kwargs["where"] = filters

        try:
            results = self._collection.query(**kwargs)
        except Exception as exc:
            raise StorageError(f"ChromaDB query failed: {exc}") from exc

        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            output.append(
                {
                    "id": doc_id,
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                }
            )
        return output

    def get_since(self, cutoff_iso: str, limit: int = 80) -> list[dict]:
        """Return email chunks received on or after *cutoff_iso*.

        Args:
            cutoff_iso: ISO-format datetime string (e.g. "2026-02-28T00:00:00").
            limit: Maximum chunks to return (deduplication by source happens
                in the caller).

        Returns:
            List of dicts with keys: id, document, metadata.
        """
        try:
            results = self._collection.get(
                where={
                    "$and": [
                        {"type": {"$eq": "email"}},
                        {"received_at": {"$gte": cutoff_iso}},
                    ]
                },
                limit=limit,
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            raise StorageError(f"ChromaDB get_since failed: {exc}") from exc

        output = []
        for doc_id, doc, meta in zip(
            results["ids"], results["documents"], results["metadatas"]
        ):
            output.append({"id": doc_id, "document": doc, "metadata": meta})
        return output

    def count(self) -> int:
        """Return the total number of chunks stored."""
        return self._collection.count()
