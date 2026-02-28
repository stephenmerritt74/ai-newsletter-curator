"""Fetch and extract article content from URLs found in emails."""

import hashlib
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from src.models import FetchedArticle

logger = logging.getLogger(__name__)

# --- URL filtering -----------------------------------------------------------

_SKIP_PATH_RE = re.compile(
    r"(unsubscri|optout|opt.out|manage.pref|track|pixel|beacon|"
    r"click\.php|forward|view.in.browser|email.web|share\?|tweet\?)",
    re.IGNORECASE,
)

# Domains that are pure platforms / social / shorteners — not article sources
_SKIP_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "linkedin.com", "youtube.com", "youtu.be", "t.co",
    "bit.ly", "ow.ly", "tinyurl.com", "goo.gl",
    "mailchimp.com", "list-manage.com", "sendgrid.net",
    "constantcontact.com", "klaviyo.com", "beehiiv.com",
    "substack.com",
}

# File extensions that are definitely not articles
_SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".woff", ".woff2", ".mp4", ".mp3", ".zip",
}

_FETCH_TIMEOUT = 12.0  # seconds
_MIN_ARTICLE_CHARS = 200  # discard pages with almost no content
_FETCH_DELAY = 0.5  # seconds between requests (polite crawling)
_USER_AGENT = (
    "Mozilla/5.0 (compatible; AINewsletterCurator/1.0; +https://github.com)"
)


def is_article_url(url: str) -> bool:
    """Return True if *url* looks like a fetchable article.

    Filters out tracking links, unsubscribe pages, social profiles,
    media files, and bare homepages.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    domain = parsed.netloc.lower().removeprefix("www.")

    # Strip subdomain for domain matching (e.g. mail.beehiiv.com → beehiiv.com)
    domain_root = ".".join(domain.split(".")[-2:])
    if domain in _SKIP_DOMAINS or domain_root in _SKIP_DOMAINS:
        return False

    path = parsed.path.lower()
    if Path(path).suffix in _SKIP_EXTENSIONS:
        return False

    if _SKIP_PATH_RE.search(path + "?" + (parsed.query or "")):
        return False

    # Require at least one real path segment (skip bare homepages)
    path_parts = [p for p in path.split("/") if p]
    if not path_parts:
        return False

    return True


def url_to_source_id(url: str) -> str:
    """Return a short stable ID for a URL (used as ChromaDB chunk source ID)."""
    return "article__" + hashlib.md5(url.encode()).hexdigest()[:16]


# --- Content fetching --------------------------------------------------------


def _extract_title(html: str, url: str) -> str:
    """Pull the page title from HTML, falling back to the URL."""
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("title")
        if tag:
            return tag.get_text(strip=True)[:200]
    except Exception:
        pass
    return url


def fetch_article(url: str) -> FetchedArticle | None:
    """Fetch *url* and extract its main article text.

    Args:
        url: A URL that has already passed ``is_article_url``.

    Returns:
        A FetchedArticle on success, or None if the page couldn't be fetched
        or contained too little text.
    """
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None

    text = trafilatura.extract(
        html,
        include_links=False,
        include_images=False,
        no_fallback=False,
    )

    if not text or len(text) < _MIN_ARTICLE_CHARS:
        logger.debug("Skipping %s — insufficient content (%d chars)", url, len(text or ""))
        return None

    title = _extract_title(html, url)

    return FetchedArticle(
        url=url,
        title=title,
        clean_text=text,
        word_count=len(text.split()),
        source_email_message_id="",  # set by caller
    )


def fetch_articles_from_email(
    urls: list[str],
    source_email_message_id: str,
    fetch_delay: float = _FETCH_DELAY,
) -> list[FetchedArticle]:
    """Filter article URLs and fetch their content.

    Args:
        urls: Candidate URLs extracted from an email.
        source_email_message_id: The parent email's message ID.
        fetch_delay: Seconds to wait between requests.

    Returns:
        List of successfully fetched FetchedArticle objects.
    """
    article_urls = [u for u in urls if is_article_url(u)]
    logger.info(
        "%d / %d links look like articles for email %s",
        len(article_urls), len(urls), source_email_message_id,
    )

    results: list[FetchedArticle] = []
    for url in article_urls:
        article = fetch_article(url)
        if article:
            article.source_email_message_id = source_email_message_id
            results.append(article)
        if fetch_delay:
            time.sleep(fetch_delay)

    return results
