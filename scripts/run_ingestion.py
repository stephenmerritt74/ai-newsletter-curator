"""CLI entry-point for running the email ingestion pipeline.

Usage::

    python scripts/run_ingestion.py --source gmail --days 7
    python scripts/run_ingestion.py --source yahoo --days 14
    python scripts/run_ingestion.py --source all --days 7
"""

import argparse
import logging
import sys

from rich.console import Console
from rich.logging import RichHandler

from src.exceptions import CuratorError
from src.ingestion.gmail_client import GmailClient
from src.ingestion.whitelist import SenderWhitelist
from src.ingestion.yahoo_client import YahooClient
from src.models import RawEmail
from src.processing.classifier import classify
from src.processing.embeddings import EmbeddingClient
from src.processing.link_fetcher import fetch_articles_from_email, url_to_source_id
from src.processing.parser import parse_email
from src.storage.database import ArticleRecord, ChunkRecord, EmailRecord, get_session, init_db
from src.storage.vector_store import VectorStore

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)


def _ingest_emails(
    emails: list[RawEmail],
    embedder: EmbeddingClient,
    vector_store: VectorStore,
    skip_articles: bool = False,
) -> None:
    """Parse, classify, embed, and persist a batch of raw emails."""
    init_db()

    with get_session() as session:
        skipped = 0
        processed = 0
        articles_fetched = 0

        for raw in emails:
            # Skip already-ingested emails
            existing = (
                session.query(EmailRecord)
                .filter_by(message_id=raw.message_id)
                .first()
            )
            if existing:
                skipped += 1
                continue

            try:
                parsed = parse_email(raw)
            except CuratorError as exc:
                logger.warning("Skipping email %s: %s", raw.message_id, exc)
                continue

            content_type = classify(parsed)
            parsed.content_type = content_type

            # Persist email metadata
            record = EmailRecord(
                message_id=raw.message_id,
                source=raw.source.value,
                subject=raw.subject,
                sender_email=raw.sender_email,
                received_at=raw.received_at,
                content_type=content_type.value,
                word_count=parsed.word_count,
            )
            session.add(record)
            session.flush()  # Get record.id before chunk inserts

            # Embed email body chunks
            try:
                embedded_chunks = embedder.embed_email(parsed)
            except CuratorError as exc:
                logger.warning(
                    "Embedding failed for %s, storing without vectors: %s",
                    raw.message_id,
                    exc,
                )
                embedded_chunks = []

            if embedded_chunks:
                chroma_ids = vector_store.add_chunks(embedded_chunks)
                for ec, chroma_id in zip(embedded_chunks, chroma_ids):
                    session.add(
                        ChunkRecord(
                            email_id=record.id,
                            chunk_index=ec.chunk.chunk_index,
                            text=ec.chunk.text,
                            token_count=ec.chunk.token_count,
                            chroma_id=chroma_id,
                        )
                    )

            # Fetch and embed linked articles
            if not skip_articles and parsed.links:
                link_urls = [lnk.url for lnk in parsed.links]
                articles = fetch_articles_from_email(link_urls, raw.message_id)
                for article in articles:
                    # Skip already-fetched articles
                    if session.query(ArticleRecord).filter_by(url=article.url).first():
                        continue

                    source_id = url_to_source_id(article.url)
                    try:
                        art_chunks = embedder.embed_text(
                            source_id=source_id,
                            text=article.clean_text,
                            extra_metadata={
                                "type": "article",
                                "url": article.url,
                                "title": article.title,
                                "source_email_id": raw.message_id,
                            },
                        )
                    except CuratorError as exc:
                        logger.warning("Embedding article %s failed: %s", article.url, exc)
                        art_chunks = []

                    art_record = ArticleRecord(
                        url=article.url,
                        title=article.title,
                        email_id=record.id,
                        word_count=article.word_count,
                    )
                    session.add(art_record)

                    if art_chunks:
                        art_chroma_ids = vector_store.add_chunks(art_chunks)
                        logger.debug(
                            "Stored %d chunks for article %s", len(art_chunks), article.url
                        )

                    articles_fetched += 1

            processed += 1

        session.commit()

    summary = f"[green]Done.[/green] Emails processed: {processed}, skipped (duplicate): {skipped}"
    if not skip_articles:
        summary += f", articles fetched: {articles_fetched}"
    console.print(summary)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest newsletter emails into the curator database."
    )
    parser.add_argument(
        "--source",
        choices=["gmail", "yahoo", "all"],
        default="all",
        help="Which email source to ingest from (default: all)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many days back to fetch emails (default: 7)",
    )
    parser.add_argument(
        "--skip-articles",
        action="store_true",
        help="Skip fetching linked articles (faster, email bodies only)",
    )
    args = parser.parse_args()

    embedder = EmbeddingClient()
    vector_store = VectorStore()
    whitelist = SenderWhitelist()

    all_emails: list[RawEmail] = []

    if args.source in ("gmail", "all"):
        console.print("[bold]Fetching Gmail emails...[/bold]")
        try:
            client = GmailClient()
            emails = client.fetch_emails(days=args.days)
            filtered = [e for e in emails if whitelist.is_allowed(e.sender_email)]
            console.print(
                f"  Fetched [cyan]{len(emails)}[/cyan] Gmail emails, "
                f"[cyan]{len(filtered)}[/cyan] matched whitelist"
            )
            all_emails.extend(filtered)
        except CuratorError as exc:
            console.print(f"[red]Gmail ingestion failed:[/red] {exc}")
            if args.source == "gmail":
                sys.exit(1)

    if args.source in ("yahoo", "all"):
        console.print("[bold]Fetching Yahoo emails...[/bold]")
        try:
            client = YahooClient()
            emails = client.fetch_emails(days=args.days)
            filtered = [e for e in emails if whitelist.is_allowed(e.sender_email)]
            console.print(
                f"  Fetched [cyan]{len(emails)}[/cyan] Yahoo emails, "
                f"[cyan]{len(filtered)}[/cyan] matched whitelist"
            )
            all_emails.extend(filtered)
        except CuratorError as exc:
            console.print(f"[red]Yahoo ingestion failed:[/red] {exc}")
            if args.source == "yahoo":
                sys.exit(1)

    if not all_emails:
        console.print("[yellow]No emails fetched. Nothing to ingest.[/yellow]")
        return

    console.print(f"\n[bold]Processing {len(all_emails)} emails...[/bold]")
    _ingest_emails(all_emails, embedder, vector_store, skip_articles=args.skip_articles)


if __name__ == "__main__":
    main()
