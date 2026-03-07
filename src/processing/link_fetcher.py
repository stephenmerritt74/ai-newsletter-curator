"""Fetch and extract article content from URLs found in emails."""

import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import fitz  # pymupdf
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
    "amazonaws.com",  # S3 links are attachments/assets, not articles
}

# File extensions that are definitely not articles
_SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".woff", ".woff2", ".mp4", ".mp3", ".zip",
}
# Note: .pdf is intentionally excluded — PDFs are handled via Content-Type detection

_FETCH_TIMEOUT = 12.0  # seconds
_RESOLVE_TIMEOUT = 8.0  # seconds for redirect resolution HEAD requests
_RESOLVE_WORKERS = 10  # parallel HEAD requests when resolving redirects
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


def resolve_url(url: str) -> str:
    """Follow redirects via HEAD and return the final destination URL.

    Newsletter tracking links (beehiiv, mailchimp, substack, etc.) wrap the
    real article URL in a click-tracker redirect. This resolves those to the
    actual URL before filtering so ``is_article_url`` sees the real domain.

    Falls back to the original URL if the request fails (e.g. the server
    doesn't support HEAD) — the URL will still be attempted later by
    ``fetch_article`` which uses a full GET with ``follow_redirects=True``.
    """
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_RESOLVE_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = client.head(url)
            final = str(resp.url)
            if final != url:
                logger.debug("Redirect resolved: %s → %s", url, final)
            return final
    except Exception:
        return url


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


def _extract_pdf_text(content: bytes) -> str | None:
    """Extract text from PDF bytes using pymupdf."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        pages = [page.get_text() for page in doc]
        text = "\n\n".join(p for p in pages if p.strip())
        return text if len(text) >= _MIN_ARTICLE_CHARS else None
    except Exception:
        return None


def _fetch_arxiv_title(arxiv_id: str) -> str | None:
    """Look up a paper title from the arXiv API (no auth required)."""
    import xml.etree.ElementTree as ET

    try:
        with httpx.Client(timeout=5.0, headers={"User-Agent": _USER_AGENT}) as client:
            resp = client.get(
                f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
            )
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        tag = root.find(".//atom:entry/atom:title", ns)
        if tag is not None and tag.text:
            return tag.text.strip().replace("\n", " ")[:200]
    except Exception:
        pass
    return None


def _extract_pdf_title(content: bytes, url: str) -> str:
    """Extract title from PDF metadata, falling back to the URL."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        title = doc.metadata.get("title", "").strip()
        if title:
            return title[:200]
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
    # Rewrite to arXiv PDF for full paper text.
    arxiv_id: str | None = None
    parsed = urlparse(url)
    if parsed.netloc.endswith("arxiv.org") and parsed.path.startswith("/abs/"):
        arxiv_id = parsed.path.removeprefix("/abs/")
        url = f"https://arxiv.org/pdf/{arxiv_id}"
        logger.debug("arXiv abs → pdf: %s", url)
    elif parsed.netloc == "huggingface.co" and parsed.path.startswith("/papers/"):
        arxiv_id = parsed.path.removeprefix("/papers/")
        url = f"https://arxiv.org/pdf/{arxiv_id}"
        logger.debug("HuggingFace paper → arXiv pdf: %s", url)

    # NEJM AI articles require JS rendering + an authenticated session.
    if "nejm.org" in urlparse(url).netloc:
        from src.config import settings
        from src.processing.nejm_fetcher import fetch_nejm_article

        try:
            return fetch_nejm_article(url, settings.nejm_session_path)
        except (FileNotFoundError, RuntimeError) as exc:
            logger.warning("NEJM fetch skipped for %s: %s", url, exc)
            return None

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None

    content_type = response.headers.get("content-type", "").lower()
    is_pdf = "application/pdf" in content_type or response.content[:4] == b"%PDF"
    if is_pdf:
        text = _extract_pdf_text(response.content)
        if not text:
            logger.debug("Skipping %s — PDF extraction failed or insufficient content", url)
            return None
        title = (
            (arxiv_id and _fetch_arxiv_title(arxiv_id))
            or _extract_pdf_title(response.content, url)
        )
    else:
        html = response.text
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
    # Resolve tracking redirects in parallel before filtering.
    with ThreadPoolExecutor(max_workers=_RESOLVE_WORKERS) as pool:
        resolved = list(pool.map(resolve_url, urls))

    # Deduplicate resolved URLs (two tracking links may point to the same article).
    seen: set[str] = set()
    unique_resolved: list[str] = []
    for u in resolved:
        if u not in seen:
            seen.add(u)
            unique_resolved.append(u)

    article_urls = [u for u in unique_resolved if is_article_url(u)]
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
