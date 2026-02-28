"""SQLAlchemy ORM models and session factory for the curator database."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from src.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class EmailRecord(Base):
    """Persisted metadata for a fetched email."""

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), default="unknown")
    curation_status: Mapped[str] = mapped_column(String(50), default="unread")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    chunks: Mapped[list["ChunkRecord"]] = relationship(
        "ChunkRecord", back_populates="email", cascade="all, delete-orphan"
    )


class ArticleRecord(Base):
    """A web article fetched by following a link from an email."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    email_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("emails.id"), nullable=False
    )
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    email: Mapped[EmailRecord] = relationship("EmailRecord")


class ChunkRecord(Base):
    """A text chunk derived from an email, linked to its ChromaDB vector."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("emails.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chroma_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    email: Mapped[EmailRecord] = relationship("EmailRecord", back_populates="chunks")


def _get_engine(db_path: Path | None = None):
    """Create a SQLAlchemy engine for the given SQLite path."""
    path = db_path or settings.sqlite_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", echo=False)


def get_session(db_path: Path | None = None) -> Session:
    """Return a new SQLAlchemy session.

    The caller is responsible for committing and closing it.
    Prefer using it as a context manager::

        with get_session() as session:
            ...
    """
    engine = _get_engine(db_path)
    return Session(engine)


def init_db(db_path: Path | None = None) -> None:
    """Create all tables if they do not already exist.

    Args:
        db_path: Override the SQLite file path from settings.
    """
    engine = _get_engine(db_path)
    Base.metadata.create_all(engine)
    logger.info("Database initialised at %s", db_path or settings.sqlite_db_path)
