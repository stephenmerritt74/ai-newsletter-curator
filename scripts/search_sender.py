"""Search Gmail for specific senders (all mail, not just INBOX)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.gmail_client import GmailClient


def search_sender(query: str, label: str = "") -> None:
    client = GmailClient()
    service = client._get_service()

    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=10)
        .execute()
    )
    msgs = result.get("messages", [])
    print(f"\n[{label or query}] — {len(msgs)} result(s)")
    for ref in msgs[:5]:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=ref["id"], format="metadata",
                 metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        print(f"  From   : {headers.get('From', '')}")
        print(f"  Subject: {headers.get('Subject', '')}")
        print(f"  Date   : {headers.get('Date', '')}")
        print()


if __name__ == "__main__":
    search_sender("from:lenny", "Lenny's Newsletter")
    search_sender("from:algorithm technologyreview", "The Algorithm (MIT Tech Review)")
    search_sender("from:technologyreview.com", "MIT Technology Review")
    search_sender("from:substack lenny", "Lenny on Substack")
