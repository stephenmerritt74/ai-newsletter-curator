"""RAG query engine for the newsletter chat interface."""

import logging
from datetime import datetime, timedelta, timezone

from openai import OpenAI

from src.config import settings
from src.processing.embeddings import EmbeddingClient
from src.processing.link_fetcher import url_to_source_id
from src.storage.database import ArticleRecord, get_session
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

    def weekly_digest(self, days: int = 7) -> str:
        """Generate a structured summary of content ingested in the last *days* days.

        Pulls email chunks by date from ChromaDB (one per unique source email)
        plus article titles from SQLite, then asks the LLM to synthesize a digest.

        Returns:
            Markdown-formatted digest string.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        # --- Email chunks (one per unique source, first chunk only) -----------
        all_chunks = self._vector_store.get_since(cutoff_iso)
        seen_sources: set[str] = set()
        email_chunks: list[dict] = []
        for chunk in all_chunks:
            src = chunk["metadata"].get("email_message_id", chunk["id"])
            if src not in seen_sources:
                seen_sources.add(src)
                email_chunks.append(chunk)

        # --- Recent articles from SQLite + first chunk from ChromaDB -----------
        with get_session() as session:
            articles = (
                session.query(ArticleRecord)
                .filter(ArticleRecord.fetched_at >= cutoff)
                .order_by(ArticleRecord.fetched_at.desc())
                .all()
            )

        # Fetch the first chunk of each article so the LLM has actual content.
        chunk_ids = [f"{url_to_source_id(a.url)}__0" for a in articles if a.url]
        article_chunks = self._vector_store.get_chunks_by_ids(chunk_ids[:30])
        # Build a lookup: source_id → (title, chunk_text)
        article_lookup: dict[str, tuple[str, str]] = {}
        for a in articles:
            sid = url_to_source_id(a.url)
            article_lookup[sid] = (a.title or a.url, "")
        for chunk in article_chunks:
            sid = chunk["metadata"].get("email_message_id", "")
            if sid in article_lookup:
                article_lookup[sid] = (article_lookup[sid][0], chunk["document"])

        if not email_chunks and not article_lookup:
            return f"No content found in the last {days} days. Run ingestion first."

        # --- Build context ----------------------------------------------------
        context_parts: list[str] = []
        for chunk in email_chunks:
            meta = chunk["metadata"]
            header = f"Newsletter: {meta.get('subject', 'Unknown')} (from {meta.get('sender_email', '?')})"
            context_parts.append(f"[{header}]\n{chunk['document']}")

        for title, text in article_lookup.values():
            if text:
                context_parts.append(f"[Article: {title}]\n{text}")
            else:
                context_parts.append(f"[Article: {title}]")

        context = "\n\n---\n\n".join(context_parts)

        prompt = (
            f"The following content was ingested from AI newsletters over the last {days} days.\n\n"
            f"{context}\n\n"
            "Write a weekly digest in Markdown with these sections:\n\n"
            "## Key Themes\n"
            "2-4 bullet points on the dominant topics this week.\n\n"
            "## Notable Papers & Research\n"
            "For each paper: **Title** — 3-4 sentences covering the problem it addresses, "
            "the approach or method, the key finding or result, and why it matters. "
            "Include all papers you can find in the context.\n\n"
            "## Tools & Releases\n"
            "Bullet list of new models, products, or open-source releases with a 1-2 sentence description each.\n\n"
            "## Other Highlights\n"
            "Anything else worth noting (industry news, opinion, events).\n\n"
            "Be specific — name models, papers, and companies. Skip filler."
        )

        response = self._openai.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content or "Digest generation failed."
