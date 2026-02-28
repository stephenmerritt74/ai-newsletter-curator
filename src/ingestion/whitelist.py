"""Sender whitelist for filtering incoming emails to AI-relevant senders."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("ai_sender_whitelist.json")


def _extract_domain(email_address: str) -> str:
    """Return the domain portion of an email address."""
    if "@" in email_address:
        return email_address.split("@", 1)[1].lower()
    return email_address.lower()


class SenderWhitelist:
    """Loads the sender whitelist JSON and checks whether an email is allowed.

    Matching order:
    1. Exact sender email address (handles shared platforms like beehiiv.com)
    2. Sender domain (handles owned domains with dynamic addresses, e.g.
       ``no-reply-XXX@mail.anthropic.com``)
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._allowed_emails: set[str] = set()
        self._allowed_domains: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("Whitelist file not found: %s — all senders allowed", self._path)
            return

        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)

        for entry in data.get("senders", []):
            email = entry.get("email", "").strip().lower()
            domain = entry.get("domain", "").strip().lower()
            if email:
                self._allowed_emails.add(email)
            if domain:
                self._allowed_domains.add(domain)

        logger.info(
            "Whitelist loaded: %d emails, %d domains",
            len(self._allowed_emails),
            len(self._allowed_domains),
        )

    def is_allowed(self, sender_email: str) -> bool:
        """Return True if *sender_email* matches the whitelist.

        Args:
            sender_email: The sender's email address to check.

        Returns:
            True if the sender is whitelisted (or the whitelist file is missing).
            False otherwise.
        """
        if not self._allowed_emails and not self._allowed_domains:
            # Whitelist file missing — fail open so ingestion still works
            return True

        normalized = sender_email.strip().lower()

        if normalized in self._allowed_emails:
            return True

        domain = _extract_domain(normalized)
        return domain in self._allowed_domains
