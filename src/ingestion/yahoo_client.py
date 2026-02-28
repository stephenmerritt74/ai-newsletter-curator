"""Yahoo IMAP client for fetching newsletter emails."""

import logging
from datetime import datetime, timedelta, timezone

from imap_tools import AND, MailBox, MailMessage

from src.config import settings
from src.exceptions import YahooError
from src.models import EmailSource, RawEmail

logger = logging.getLogger(__name__)

YAHOO_IMAP_SERVER = "imap.mail.yahoo.com"


class YahooClient:
    """Fetches emails from Yahoo Mail via IMAP."""

    def __init__(
        self,
        email_address: str | None = None,
        app_password: str | None = None,
        folder: str | None = None,
    ) -> None:
        self._email = email_address or settings.yahoo_email
        self._password = app_password or settings.yahoo_app_password
        self._folder = folder or settings.yahoo_folder

    def fetch_emails(self, days: int = 7, max_results: int = 500) -> list[RawEmail]:
        """Fetch emails from the last *days* days.

        Args:
            days: How many days back to search.
            max_results: Upper bound on messages returned.

        Returns:
            List of RawEmail objects.

        Raises:
            YahooError: If credentials are missing or the IMAP connection fails.
        """
        if not self._email or not self._password:
            raise YahooError(
                "Yahoo credentials not configured. Set YAHOO_EMAIL and "
                "YAHOO_APP_PASSWORD in your .env file."
            )

        since_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()

        try:
            with MailBox(YAHOO_IMAP_SERVER).login(
                self._email, self._password, self._folder
            ) as mailbox:
                criteria = AND(date_gte=since_date)
                messages = list(
                    mailbox.fetch(criteria, limit=max_results, reverse=True)
                )
        except Exception as exc:
            raise YahooError(f"Yahoo IMAP connection failed: {exc}") from exc

        logger.info(
            "Found %d Yahoo messages in the last %d days", len(messages), days
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
            source=EmailSource.YAHOO,
            subject=msg.subject or "(no subject)",
            sender=msg.from_ or "",
            sender_email=msg.from_ or "",
            received_at=received_at,
            body_html=msg.html or None,
            body_text=msg.text or None,
        )
