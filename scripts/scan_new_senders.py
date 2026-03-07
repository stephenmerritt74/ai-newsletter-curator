"""Scan Gmail for senders not yet in the whitelist."""

import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.gmail_client import GmailClient

WHITELIST_PATH = Path(__file__).parent.parent / "ai_sender_whitelist.json"


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    whitelist = json.loads(WHITELIST_PATH.read_text())
    known_emails = {s["email"].lower() for s in whitelist["senders"]}
    known_domains = {s["domain"].lower() for s in whitelist["senders"]}

    print(f"Fetching Gmail messages from the last {days} days…")
    client = GmailClient()
    emails = client.fetch_emails(days=days, max_results=500)
    print(f"Fetched {len(emails)} messages.")

    # Collect unique senders
    seen: dict[str, dict] = {}  # email -> {name, email, domain}
    for e in emails:
        addr = e.sender_email.lower().strip()
        if not addr:
            continue
        domain = addr.split("@")[-1] if "@" in addr else ""
        seen[addr] = {"from_header": e.sender, "email": addr, "domain": domain}

    new_senders = [
        info
        for addr, info in sorted(seen.items())
        if addr not in known_emails and info["domain"] not in known_domains
    ]

    print(f"\n{len(new_senders)} sender(s) not in whitelist:\n")
    for s in new_senders:
        print(f"  From   : {s['from_header']}")
        print(f"  Email  : {s['email']}")
        print(f"  Domain : {s['domain']}")
        print()


if __name__ == "__main__":
    main()
