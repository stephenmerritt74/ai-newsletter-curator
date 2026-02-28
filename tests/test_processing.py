"""Tests for the processing pipeline: parser, classifier, embeddings."""

from datetime import datetime, timezone

import pytest

from src.models import ContentType, EmailSource, ParsedEmail, RawEmail


def _raw(subject="Newsletter", html=None, text=None) -> RawEmail:
    return RawEmail(
        message_id="test-001",
        source=EmailSource.GMAIL,
        subject=subject,
        sender="sender@example.com",
        sender_email="sender@example.com",
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        body_html=html,
        body_text=text,
    )


class TestParser:
    def test_placeholder_html_parsing(self):
        """Placeholder — parse_email returns a ParsedEmail from HTML input."""
        pass

    def test_placeholder_plain_text_fallback(self):
        """Placeholder — parse_email falls back to plain text when no HTML."""
        pass

    def test_placeholder_raises_on_no_body(self):
        """Placeholder — parse_email raises ParsingError when body is absent."""
        pass


class TestClassifier:
    def test_placeholder_paper_classification(self):
        """Placeholder — classify returns PAPER for arxiv-linked emails."""
        pass

    def test_placeholder_unknown_fallback(self):
        """Placeholder — classify returns UNKNOWN when no signals match."""
        pass

    def test_placeholder_news_classification(self):
        """Placeholder — classify returns NEWS for digest-style emails."""
        pass


class TestEmbeddingClient:
    def test_placeholder_embed_email(self):
        """Placeholder — embed_email returns EmbeddedChunk list (requires API key)."""
        pass

    def test_placeholder_empty_text_returns_empty(self):
        """Placeholder — embed_email returns [] for emails with no text."""
        pass
