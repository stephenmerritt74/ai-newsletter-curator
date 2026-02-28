"""Text chunking and embedding generation using OpenAI text-embedding-3-small."""

import logging

import tiktoken
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.exceptions import EmbeddingError
from src.models import EmbeddedChunk, ParsedEmail, TextChunk

logger = logging.getLogger(__name__)


def _chunk_text(text: str, message_id: str, chunk_size: int) -> list[TextChunk]:
    """Split *text* into token-bounded chunks.

    Args:
        text: The clean text to chunk.
        message_id: The email message ID for provenance tracking.
        chunk_size: Maximum tokens per chunk.

    Returns:
        List of TextChunk objects.
    """
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)

    chunks: list[TextChunk] = []
    for i, start in enumerate(range(0, len(tokens), chunk_size)):
        token_slice = tokens[start : start + chunk_size]
        chunk_text = enc.decode(token_slice)
        chunks.append(
            TextChunk(
                email_message_id=message_id,
                chunk_index=i,
                text=chunk_text,
                token_count=len(token_slice),
            )
        )

    return chunks


class EmbeddingClient:
    """Generates vector embeddings for text chunks via OpenAI."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        chunk_size: int | None = None,
    ) -> None:
        self._model = model or settings.embedding_model
        self._chunk_size = chunk_size or settings.chunk_size_tokens
        self._client = OpenAI(api_key=api_key or settings.openai_api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the OpenAI embeddings API for a batch of texts."""
        response = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]

    def embed_text(
        self,
        source_id: str,
        text: str,
        extra_metadata: dict | None = None,
    ) -> list[EmbeddedChunk]:
        """Chunk and embed arbitrary text.

        Args:
            source_id: Identifier stored on each chunk (email ID, URL hash, etc.).
            text: The text to chunk and embed.
            extra_metadata: Optional dict merged into each EmbeddedChunk's metadata.

        Returns:
            List of EmbeddedChunk objects (one per chunk).

        Raises:
            EmbeddingError: If the OpenAI API call fails after retries.
        """
        if not text.strip():
            return []

        chunks = _chunk_text(text, source_id, self._chunk_size)
        texts = [c.text for c in chunks]

        try:
            embeddings = self._embed_batch(texts)
        except Exception as exc:
            raise EmbeddingError(
                f"Failed to embed source {source_id}: {exc}"
            ) from exc

        return [
            EmbeddedChunk(
                chunk=chunk,
                embedding=emb,
                model=self._model,
                metadata=extra_metadata or {},
            )
            for chunk, emb in zip(chunks, embeddings)
        ]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for retrieval.

        Args:
            text: The query text.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            EmbeddingError: If the API call fails after retries.
        """
        try:
            return self._embed_batch([text])[0]
        except Exception as exc:
            raise EmbeddingError(f"Failed to embed query: {exc}") from exc

    def embed_email(self, parsed: ParsedEmail) -> list[EmbeddedChunk]:
        """Chunk and embed a parsed email."""
        if not parsed.clean_text.strip():
            logger.warning(
                "Email %s has no text to embed", parsed.raw_email.message_id
            )
            return []

        return self.embed_text(
            source_id=parsed.raw_email.message_id,
            text=parsed.clean_text,
            extra_metadata={
                "type": "email",
                "subject": parsed.raw_email.subject,
                "sender_email": parsed.raw_email.sender_email,
                "received_at": parsed.raw_email.received_at.isoformat(),
            },
        )
