"""Email parser: HTML → clean text + link extraction."""

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.exceptions import ParsingError
from src.models import ContentType, ExtractedLink, ParsedEmail, RawEmail

logger = logging.getLogger(__name__)


def _extract_domain(url: str) -> str:
    """Return the netloc of a URL, stripping the www. prefix."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or ""
        return domain.removeprefix("www.")
    except Exception:
        return ""


def _html_to_text(html: str) -> str:
    """Strip HTML tags and return clean plain text."""
    soup = BeautifulSoup(html, "lxml")

    # Remove script/style noise
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_links(html: str) -> list[ExtractedLink]:
    """Extract all hyperlinks from HTML."""
    soup = BeautifulSoup(html, "lxml")
    links: list[ExtractedLink] = []
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True):
        url: str = tag["href"].strip()
        if not url or url.startswith(("mailto:", "tel:", "#")):
            continue
        if url in seen:
            continue
        seen.add(url)

        anchor = tag.get_text(strip=True) or ""
        links.append(
            ExtractedLink(
                url=url,
                anchor_text=anchor,
                domain=_extract_domain(url),
            )
        )

    return links


def parse_email(raw: RawEmail) -> ParsedEmail:
    """Parse a RawEmail into clean text and extracted links.

    Args:
        raw: The raw email fetched from a mail provider.

    Returns:
        ParsedEmail with clean text, links, and word count.

    Raises:
        ParsingError: If neither HTML nor plain text body is available.
    """
    try:
        if raw.body_html:
            clean_text = _html_to_text(raw.body_html)
            links = _extract_links(raw.body_html)
        elif raw.body_text:
            clean_text = raw.body_text.strip()
            links = []
        else:
            raise ParsingError(
                f"Email {raw.message_id} has no body content to parse."
            )

        word_count = len(clean_text.split())

        return ParsedEmail(
            raw_email=raw,
            clean_text=clean_text,
            links=links,
            word_count=word_count,
            content_type=ContentType.UNKNOWN,
        )
    except ParsingError:
        raise
    except Exception as exc:
        raise ParsingError(
            f"Failed to parse email {raw.message_id}: {exc}"
        ) from exc
