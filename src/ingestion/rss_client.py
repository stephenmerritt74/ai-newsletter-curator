"""RSS/Atom feed client for fetching newsletter content."""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx
from dateutil import parser as dateutil_parser

from src.exceptions import RssError
from src.models import EmailSource, RawEmail

logger = logging.getLogger(__name__)

_ATOM_NS = "http://www.w3.org/2005/Atom"


def _ns(tag: str) -> str:
    return f"{{{_ATOM_NS}}}{tag}"


def _child_text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text if child is not None else None


def _parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        dt = dateutil_parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OverflowError):
        return None


class RssFeedClient:
    """Fetches entries from an RSS/Atom feed and returns them as RawEmail objects."""

    def __init__(self, feed_url: str, feed_name: str = "") -> None:
        self._url = feed_url
        self._name = feed_name or urlparse(feed_url).netloc or feed_url

    def fetch_emails(self, days: int = 7) -> list[RawEmail]:
        """Fetch feed entries published within the last *days* days.

        Args:
            days: How many days back to include.

        Returns:
            List of RawEmail objects, one per feed entry.

        Raises:
            RssError: If the feed cannot be fetched or parsed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            response = httpx.get(self._url, follow_redirects=True, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RssError(f"Failed to fetch feed {self._url}: {exc}") from exc

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise RssError(f"Failed to parse XML from {self._url}: {exc}") from exc

        root_tag = root.tag
        if root_tag == _ns("feed"):
            results = self._parse_atom(root, cutoff)
        elif root_tag in ("rss", "channel"):
            channel = root.find("channel") if root_tag == "rss" else root
            results = self._parse_rss(channel or root, cutoff)
        else:
            raise RssError(f"Unrecognized feed root element: {root_tag!r}")

        logger.info("RSS %s: %d entries within %d days", self._name, len(results), days)
        return results

    def _parse_atom(self, root: ET.Element, cutoff: datetime) -> list[RawEmail]:
        results = []
        for entry in root.findall(_ns("entry")):
            published_str = (
                _child_text(entry, _ns("published"))
                or _child_text(entry, _ns("updated"))
                or ""
            )
            published = _parse_date(published_str)
            if published and published < cutoff:
                continue

            entry_id = _child_text(entry, _ns("id")) or ""
            title = _child_text(entry, _ns("title")) or "(no title)"
            body_html, body_text = self._atom_body(entry)

            results.append(
                RawEmail(
                    message_id=entry_id or title,
                    source=EmailSource.RSS,
                    subject=title,
                    sender=self._name,
                    sender_email=self._url,
                    received_at=published or datetime.now(timezone.utc),
                    body_html=body_html,
                    body_text=body_text,
                )
            )
        return results

    def _atom_body(self, entry: ET.Element) -> tuple[str | None, str | None]:
        for tag in (_ns("content"), _ns("summary")):
            el = entry.find(tag)
            if el is None or not el.text:
                continue
            ctype = el.get("type", "text")
            if "html" in ctype:
                return el.text, None
            return None, el.text
        return None, None

    def _parse_rss(self, channel: ET.Element, cutoff: datetime) -> list[RawEmail]:
        results = []
        for item in channel.findall("item"):
            pub_str = _child_text(item, "pubDate") or ""
            published = _parse_date(pub_str)
            if published and published < cutoff:
                continue

            guid = _child_text(item, "guid") or _child_text(item, "link") or ""
            title = _child_text(item, "title") or "(no title)"
            description = _child_text(item, "description") or ""
            body_html = description if "<" in description else None
            body_text = description if "<" not in description else None

            results.append(
                RawEmail(
                    message_id=guid or title,
                    source=EmailSource.RSS,
                    subject=title,
                    sender=self._name,
                    sender_email=self._url,
                    received_at=published or datetime.now(timezone.utc),
                    body_html=body_html,
                    body_text=body_text,
                )
            )
        return results
