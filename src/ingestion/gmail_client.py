"""Gmail API client for fetching newsletter emails."""

import base64
import email
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import settings
from src.exceptions import GmailError
from src.models import EmailSource, RawEmail

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailClient:
    """Fetches emails from Gmail using OAuth2."""

    def __init__(
        self,
        credentials_path: Path | None = None,
        token_path: Path | None = None,
    ) -> None:
        self._credentials_path = credentials_path or settings.gmail_credentials_path
        self._token_path = token_path or settings.gmail_token_path
        self._service = None

    def _get_credentials(self) -> Credentials:
        """Load or refresh Gmail OAuth2 credentials."""
        creds: Credentials | None = None

        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self._token_path), SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Gmail token")
                creds.refresh(Request())
            else:
                if not self._credentials_path.exists():
                    raise GmailError(
                        f"Gmail credentials file not found: {self._credentials_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self._token_path, "w") as f:
                f.write(creds.to_json())
            logger.info("Saved Gmail token to %s", self._token_path)

        return creds

    def _get_service(self):
        """Return a cached Gmail API service instance."""
        if self._service is None:
            creds = self._get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def _decode_body(self, payload: dict) -> tuple[str | None, str | None]:
        """Extract HTML and plain-text bodies from a message payload."""
        html_body: str | None = None
        text_body: str | None = None

        def _extract(part: dict) -> None:
            nonlocal html_body, text_body
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if data:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                if mime == "text/html":
                    html_body = decoded
                elif mime == "text/plain":
                    text_body = decoded
            for sub in part.get("parts", []):
                _extract(sub)

        _extract(payload)
        return html_body, text_body

    def fetch_emails(self, days: int = 7, max_results: int = 500) -> list[RawEmail]:
        """Fetch emails from the last *days* days.

        Args:
            days: How many days back to search.
            max_results: Upper bound on messages returned.

        Returns:
            List of RawEmail objects.

        Raises:
            GmailError: If the API call fails.
        """
        service = self._get_service()
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = f"after:{since.strftime('%Y/%m/%d')}"

        try:
            result = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results, labelIds=["INBOX"])
                .execute()
            )
        except Exception as exc:
            raise GmailError(f"Failed to list Gmail messages: {exc}") from exc

        message_refs = result.get("messages", [])
        logger.info("Found %d Gmail messages in the last %d days", len(message_refs), days)

        emails: list[RawEmail] = []
        for ref in message_refs:
            try:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=ref["id"], format="full")
                    .execute()
                )
                raw = self._parse_message(msg)
                emails.append(raw)
            except Exception as exc:
                logger.warning("Skipping message %s: %s", ref["id"], exc)

        return emails

    def _parse_message(self, msg: dict) -> RawEmail:
        """Convert a raw Gmail API message to a RawEmail."""
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "")
        date_str = headers.get("Date", "")

        # Parse sender email from "Name <email>" format
        parsed = email.utils.parseaddr(sender)
        sender_email = parsed[1] or sender

        # Parse date
        try:
            received_at = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            received_at = datetime.now(timezone.utc)

        html_body, text_body = self._decode_body(msg["payload"])

        return RawEmail(
            message_id=msg["id"],
            source=EmailSource.GMAIL,
            subject=subject,
            sender=sender,
            sender_email=sender_email,
            received_at=received_at,
            body_html=html_body,
            body_text=text_body,
        )
