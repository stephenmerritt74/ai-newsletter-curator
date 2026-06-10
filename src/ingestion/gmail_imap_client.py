"""Gmail IMAP client for fetching newsletter emails.

Uses App Password + IMAP — no OAuth, no token expiry.
Enable via: Google Account → Security → 2-Step Verification → App Passwords
"""

import logging
from datetime import datetime, timedelta, timezone

from imap_tools import AND, MailBox, MailMessage

from src.config import settings
from src.exceptions import CuratorError
from src.models import EmailSource, RawEmail

logger = logging.getLogger(__name__)

GMAIL_IMAP_SERVER = "imap.gmail.com"


class GmailImapClient:
    """Fetches emails from Gmail via IMAP using an App Password."""

    def __init__(
        self,
        email_address: str | None = None,
        app_password: str | None = None,
    ) -> None:
        self._email = email_address or settings.gmail_email
        self._password = app_password or settings.gmail_app_password

    def fetch_emails(self, days: int = 2, max_results: int = 500) -> list[RawEmail]:
        """Fetch emails from the last *days* days.

        Args:
            days: How many days back to search.
            max_results: Upper bound on messages returned.

        Returns:
            List of RawEmail objects.

        Raises:
            CuratorError: If credentials are missing or IMAP connection fails.
        """
        if not self._email or not self._password:
            raise CuratorError(
                "Gmail IMAP credentials not configured. "
                "Set GMAIL_EMAIL and GMAIL_APP_PASSWORD in your .env file."
            )

        since_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()

        try:
            with MailBox(GMAIL_IMAP_SERVER).login(
                self._email, self._password, "INBOX"
            ) as mailbox:
                criteria = AND(date_gte=since_date)
                messages = list(
                    mailbox.fetch(criteria, limit=max_results, reverse=True)
                )
        except Exception as exc:
            raise CuratorError(f"Gmail IMAP connection failed: {exc}") from exc

        logger.info(
            "Found %d Gmail messages in the last %d days", len(messages), days
        )

        return [self._parse_message(msg) for msg in messages]

    def _parse_message(self, msg: MailMessage) -> RawEmail:
        """Convert an imap_tools MailMessage to a RawEmail."""
        received_at = msg.date
        if received_at is None:
            received_at = datetime.now(timezone.utc)
        elif received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)

        return RawEmail(
            message_id=msg.uid or msg.message_id or "",
            source=EmailSource.GMAIL,
            subject=msg.subject or "(no subject)",
            sender=msg.from_ or "",
            sender_email=msg.from_ or "",
            received_at=received_at,
            body_html=msg.html or None,
            body_text=msg.text or None,
        )
