"""Fetch recent emails from a sender and inspect extracted URLs + body."""

import re
import sys
from pathlib import Path

import httpx
import trafilatura

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.gmail_client import GmailClient

_URL_RE = re.compile(r'https?://[^\s\'"<>]+', re.IGNORECASE)
_TIMEOUT = 12.0


def resolve_and_probe(url: str) -> tuple[str, str, str]:
    """Return (final_url, status, content_type) after following redirects."""
    try:
        with httpx.Client(follow_redirects=True, timeout=_TIMEOUT,
                          headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = client.get(url)
            ct = r.headers.get("content-type", "").split(";")[0].strip()
            text = trafilatura.extract(r.text) if "html" in ct else None
            preview = (text[:300] + "…") if text and len(text) > 300 else (text or "")
            return str(r.url), f"{r.status_code}", ct, preview
    except Exception as exc:
        return url, "ERR", str(exc), ""


def main() -> None:
    search_query = sys.argv[1] if len(sys.argv) > 1 else "from:nejm"
    label = sys.argv[2] if len(sys.argv) > 2 else search_query

    client = GmailClient()
    service = client._get_service()

    result = service.users().messages().list(
        userId="me", q=search_query, maxResults=5
    ).execute()
    msgs = result.get("messages", [])
    print(f"\n[{label}] — {len(msgs)} email(s) found\n")

    for ref in msgs[:1]:  # inspect most recent only
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="full"
        ).execute()
        raw = client._parse_message(msg)

        print(f"Subject : {raw.subject}")
        print(f"From    : {raw.sender}")
        print(f"Date    : {raw.received_at}")

        # Show email body text
        from bs4 import BeautifulSoup
        body_text = ""
        if raw.body_html:
            body_text = BeautifulSoup(raw.body_html, "lxml").get_text(separator="\n", strip=True)
        elif raw.body_text:
            body_text = raw.body_text
        print(f"\n--- Email body (first 1500 chars) ---")
        print(body_text[:1500])
        print("---\n")

        # Resolve the first 5 non-image tracking URLs
        body = raw.body_html or raw.body_text or ""
        urls = list(dict.fromkeys(_URL_RE.findall(body)))
        tracking_urls = [u for u in urls if "t.n.nejm.org" in u][:8]

        print(f"Resolving {len(tracking_urls)} tracking URLs…\n")
        for url in tracking_urls:
            final, status, ct, preview = resolve_and_probe(url)
            print(f"  Status : {status}  {ct}")
            print(f"  Final  : {final[:120]}")
            if preview:
                print(f"  Text   : {preview[:200]}")
            print()


if __name__ == "__main__":
    main()
