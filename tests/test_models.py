"""Tests for Pydantic data models."""

from datetime import datetime, timezone

import pytest

from src.models import (
    ContentType,
    CurationStatus,
    EmailSource,
    EmbeddedChunk,
    ExtractedLink,
    ParsedEmail,
    RawEmail,
    TextChunk,
)


def _make_raw_email(**kwargs) -> RawEmail:
    defaults = dict(
        message_id="msg-001",
        source=EmailSource.GMAIL,
        subject="Test Subject",
        sender="Test Sender <test@example.com>",
        sender_email="test@example.com",
        received_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    return RawEmail(**{**defaults, **kwargs})


class TestRawEmail:
    def test_valid_creation(self):
        email = _make_raw_email()
        assert email.message_id == "msg-001"
        assert email.source == EmailSource.GMAIL

    def test_optional_bodies_default_none(self):
        email = _make_raw_email()
        assert email.body_html is None
        assert email.body_text is None

    def test_with_html_body(self):
        email = _make_raw_email(body_html="<p>Hello</p>")
        assert email.body_html == "<p>Hello</p>"


class TestContentType:
    def test_all_values_exist(self):
        expected = {"paper", "tutorial", "course", "news", "tool", "unknown"}
        assert {ct.value for ct in ContentType} == expected


class TestCurationStatus:
    def test_all_values_exist(self):
        expected = {"unread", "read", "starred", "archived"}
        assert {cs.value for cs in CurationStatus} == expected


class TestExtractedLink:
    def test_valid_link(self):
        link = ExtractedLink(
            url="https://arxiv.org/abs/2301.00001",
            anchor_text="Read paper",
            domain="arxiv.org",
        )
        assert link.domain == "arxiv.org"


class TestParsedEmail:
    def test_default_content_type_is_unknown(self):
        raw = _make_raw_email()
        parsed = ParsedEmail(
            raw_email=raw,
            clean_text="some text",
            word_count=2,
        )
        assert parsed.content_type == ContentType.UNKNOWN

    def test_links_default_empty(self):
        raw = _make_raw_email()
        parsed = ParsedEmail(raw_email=raw, clean_text="text", word_count=1)
        assert parsed.links == []


class TestTextChunk:
    def test_valid_chunk(self):
        chunk = TextChunk(
            email_message_id="msg-001",
            chunk_index=0,
            text="hello world",
            token_count=2,
        )
        assert chunk.chunk_index == 0


class TestEmbeddedChunk:
    def test_default_model(self):
        chunk = TextChunk(
            email_message_id="msg-001",
            chunk_index=0,
            text="hello",
            token_count=1,
        )
        embedded = EmbeddedChunk(chunk=chunk, embedding=[0.1, 0.2, 0.3])
        assert embedded.model == "text-embedding-3-small"
