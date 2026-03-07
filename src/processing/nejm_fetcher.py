"""Fetch full article text from NEJM AI using a saved Playwright session.

NEJM AI articles require an authenticated session and JavaScript rendering.
Use ``scripts/save_nejm_session.py`` once to save credentials, then this
module will reuse that session on every run.
"""

import logging
from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from src.models import FetchedArticle

logger = logging.getLogger(__name__)

_SIGNIN_HOSTNAMES = {"myaccount.nejm.org", "login.nejm.org"}
_MIN_ARTICLE_CHARS = 200


def fetch_nejm_article(url: str, session_path: Path) -> FetchedArticle | None:
    """Fetch a NEJM AI article using a saved browser session.

    Args:
        url: A ``ai.nejm.org`` article URL.
        session_path: Path to the Playwright storage-state JSON created by
            ``scripts/save_nejm_session.py``.

    Returns:
        A FetchedArticle on success, or None if content extraction failed.

    Raises:
        FileNotFoundError: If *session_path* does not exist.
        RuntimeError: If the browser redirects to a sign-in page (session
            expired — re-run ``scripts/save_nejm_session.py``).
    """
    if not session_path.exists():
        raise FileNotFoundError(
            f"NEJM session file not found: {session_path}\n"
            "Run `python scripts/save_nejm_session.py` to create it."
        )

    with sync_playwright() as p:
        # Must use real Chrome (channel="chrome") — headless Chromium is
        # fingerprinted and blocked by Cloudflare even with valid session cookies.
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            storage_state=str(session_path),
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            logger.debug("Navigating to %s", url)
            page.goto(url, wait_until="load", timeout=30_000)
            # Give JS a moment to render the article body after the load event.
            page.wait_for_timeout(2_000)

            final_hostname = page.url.split("/")[2] if "//" in page.url else ""
            if final_hostname in _SIGNIN_HOSTNAMES:
                raise RuntimeError(
                    "NEJM session has expired. Re-run `python scripts/save_nejm_session.py`."
                )

            html = page.content()
        finally:
            browser.close()

    # Extract clean body text via trafilatura
    text = trafilatura.extract(
        html,
        include_links=False,
        include_images=False,
        no_fallback=False,
    )

    if not text or len(text) < _MIN_ARTICLE_CHARS:
        logger.debug(
            "Skipping %s — insufficient content (%d chars)", url, len(text or "")
        )
        return None

    # Extract title via BeautifulSoup fallback
    title = url
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("title")
        if tag:
            title = tag.get_text(strip=True)[:200]
    except Exception:
        pass

    return FetchedArticle(
        url=url,
        title=title,
        clean_text=text,
        word_count=len(text.split()),
        source_email_message_id="",  # set by caller
    )
