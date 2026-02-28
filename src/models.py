"""Pydantic data models for the AI Newsletter Curator."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EmailSource(StrEnum):
    GMAIL = "gmail"
    YAHOO = "yahoo"


class ContentType(StrEnum):
    PAPER = "paper"
    TUTORIAL = "tutorial"
    COURSE = "course"
    NEWS = "news"
    TOOL = "tool"
    UNKNOWN = "unknown"


class CurationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    STARRED = "starred"
    ARCHIVED = "archived"


class RawEmail(BaseModel):
    """An email as fetched directly from the mail provider."""

    message_id: str
    source: EmailSource
    subject: str
    sender: str
    sender_email: str
    received_at: datetime
    body_html: str | None = None
    body_text: str | None = None


class ExtractedLink(BaseModel):
    """A hyperlink extracted from an email body."""

    url: str
    anchor_text: str
    domain: str


class ParsedEmail(BaseModel):
    """An email after HTML parsing and link extraction."""

    raw_email: RawEmail
    clean_text: str
    links: list[ExtractedLink] = Field(default_factory=list)
    word_count: int
    content_type: ContentType = ContentType.UNKNOWN


class TextChunk(BaseModel):
    """A text chunk ready for embedding."""

    email_message_id: str
    chunk_index: int
    text: str
    token_count: int


class EmbeddedChunk(BaseModel):
    """A text chunk with its vector embedding."""

    chunk: TextChunk
    embedding: list[float]
    model: str = "text-embedding-3-small"
    # Extra metadata merged into ChromaDB on storage (e.g. type, title, url)
    metadata: dict = Field(default_factory=dict)


class FetchedArticle(BaseModel):
    """An article fetched by following a link from an email."""

    url: str
    title: str
    clean_text: str
    word_count: int
    source_email_message_id: str
