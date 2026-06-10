#!/usr/bin/env python3
"""
send_digest.py — Mon/Thu newsletter digest via Telegram.

Queries SQLite for emails ingested since the last digest, synthesizes
highlights using Claude Haiku (one API call, ~$0.001), sends to Telegram.

Usage:
    python scripts/send_digest.py            # auto window based on today
    python scripts/send_digest.py --days 4   # override lookback window
    python scripts/send_digest.py --dry-run  # print digest, don't send
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.storage.database import EmailRecord, get_session, init_db

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# Mon digest covers Thu→Mon (4 days), Thu digest covers Mon→Thu (3 days)
DEFAULT_DAYS = {0: 4, 3: 3}  # 0=Monday, 3=Thursday


def get_lookback_days(override: int | None = None) -> int:
    if override:
        return override
    today = datetime.now().weekday()
    return DEFAULT_DAYS.get(today, 4)


def fetch_recent_emails(since: datetime) -> list[dict]:
    """Pull email subject + sender + first chunk text from SQLite."""
    init_db()
    results = []
    with get_session() as session:
        emails = (
            session.query(EmailRecord)
            .filter(EmailRecord.received_at >= since)
            .order_by(EmailRecord.received_at.desc())
            .all()
        )
        for email in emails:
            # Grab first chunk text for context (already stored, zero API cost)
            first_chunk = (
                min(email.chunks, key=lambda c: c.chunk_index)
                if email.chunks
                else None
            )
            results.append({
                "subject": email.subject,
                "sender": email.sender_email,
                "received_at": email.received_at.strftime("%a %b %d"),
                "snippet": (first_chunk.text[:400] if first_chunk else "")
            })
    return results


def synthesize_digest(emails: list[dict], api_key: str) -> str:
    """One GPT-4o-mini call — synthesize highlights from stored email data."""
    if not emails:
        return "No new newsletters since last digest."

    # Build compact input — subjects + snippets only (not full articles)
    email_lines = []
    for i, e in enumerate(emails, 1):
        email_lines.append(
            f"{i}. [{e['received_at']}] {e['subject']} (from {e['sender']})\n"
            f"   {e['snippet'][:300]}"
        )

    prompt = (
        "You are summarizing AI newsletters for a data scientist who wants "
        "signal over noise. Below are newsletters ingested since the last digest.\n\n"
        "Write a tight digest with:\n"
        "- A one-line intro (how many issues, date range)\n"
        "- 5-7 bullet highlights — the most interesting/actionable items only\n"
        "- Keep each bullet to 1-2 sentences. No fluff.\n"
        "- End with: 'Open the Streamlit app to dive deeper on anything above.'\n\n"
        f"Newsletters:\n\n" + "\n\n".join(email_lines)
    )

    payload = json.dumps({
        "model": settings.chat_model or "gpt-4o-mini",
        "max_tokens": 600,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        OPENAI_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("OpenAI API call failed: %s", exc)
        return None


def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    """Send message via Telegram Bot API."""
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()

    url = TELEGRAM_API_URL.format(token=bot_token)
    req = urllib.request.Request(
        url, data=payload, headers={"content-type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


def main():
    parser = argparse.ArgumentParser(description="Send AI newsletter digest to Telegram")
    parser.add_argument("--days", type=int, help="Override lookback window (days)")
    parser.add_argument("--dry-run", action="store_true", help="Print digest, don't send")
    args = parser.parse_args()

    days = get_lookback_days(args.days)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    logger.info("Fetching emails since %s (%d days)...", since.strftime("%Y-%m-%d"), days)
    emails = fetch_recent_emails(since)
    logger.info("Found %d emails to digest", len(emails))

    if not emails:
        logger.info("Nothing new — skipping digest")
        return

    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)

    logger.info("Synthesizing digest via GPT-4o-mini...")
    digest = synthesize_digest(emails, api_key)

    if not digest:
        logger.error("Digest synthesis failed")
        sys.exit(1)

    header = f"📰 *AI Newsletter Digest* — {datetime.now().strftime('%a %b %d')}\n\n"
    full_message = header + digest

    if args.dry_run:
        print("\n" + "="*60)
        print(full_message)
        print("="*60)
        return

    bot_token = settings.telegram_bot_token if hasattr(settings, "telegram_bot_token") else os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = settings.telegram_chat_id if hasattr(settings, "telegram_chat_id") else os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        sys.exit(1)

    logger.info("Sending to Telegram...")
    ok = send_telegram(full_message, bot_token, chat_id)

    if ok:
        logger.info("✅ Digest sent successfully")
    else:
        logger.error("❌ Telegram delivery failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
