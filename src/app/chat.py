"""RAG query engine for the newsletter chat interface."""

import logging

from openai import OpenAI

from src.config import settings
from src.processing.embeddings import EmbeddingClient
from src.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a research assistant that helps the user explore their personal AI newsletter archive.

Answer questions based on the context retrieved from the user's newsletters and linked articles.
- Cite your sources: mention the article title or email subject when referencing specific content.
- If multiple sources discuss the same topic, synthesize them into a coherent answer.
- If the retrieved context is insufficient to answer well, say so clearly and suggest refining the query.
- Be concise but complete. Prefer bullet points for lists of findings or papers.
"""


class NewsletterRAG:
    """Retrieval-augmented generation over the newsletter vector store."""

    def __init__(self) -> None:
        self._openai = OpenAI(api_key=settings.openai_api_key)
        self._embedder = EmbeddingClient()
        self._vector_store = VectorStore()

    def _retrieve(self, query: str, n_results: int = 8) -> list[dict]:
        """Embed *query* and return the nearest chunks from ChromaDB."""
        query_embedding = self._embedder.embed_query(query)
        return self._vector_store.search(query_embedding, n_results=n_results)

    def _build_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        parts = []
        for chunk in chunks:
            meta = chunk["metadata"]
            chunk_type = meta.get("type", "email")
            if chunk_type == "article":
                source = f"Article: {meta.get('title', meta.get('url', 'Unknown'))}"
            else:
                source = f"Newsletter: {meta.get('subject', meta.get('email_message_id', 'Unknown'))}"
                if meta.get("sender_email"):
                    source += f" (from {meta['sender_email']})"
            parts.append(f"[{source}]\n{chunk['document']}")
        return "\n\n---\n\n".join(parts)

    def answer(
        self,
        query: str,
        conversation_history: list[dict],
        n_results: int = 8,
    ) -> tuple[str, list[dict]]:
        """Answer *query* using RAG, incorporating prior conversation context.

        Args:
            query: The user's current question.
            conversation_history: Prior turns as OpenAI message dicts
                (role: "user" | "assistant", content: str).
            n_results: Number of chunks to retrieve.

        Returns:
            (answer_text, retrieved_chunks) — the answer string and the
            source chunks used to generate it.
        """
        chunks = self._retrieve(query, n_results=n_results)
        context = self._build_context(chunks)

        messages = [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT + f"\n\nRetrieved context:\n\n{context}",
            },
            *conversation_history,
            {"role": "user", "content": query},
        ]

        response = self._openai.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            temperature=0.3,
        )

        answer_text = response.choices[0].message.content or ""
        return answer_text, chunks
