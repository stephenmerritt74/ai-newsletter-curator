"""
Test script to verify Gmail OAuth setup.

Run this from your project root:
    python test_gmail_auth.py

On first run, it will:
1. Open your browser to authenticate with Google
2. Ask you to grant permissions
3. Save a token.json file for future use
4. Fetch and display your 5 most recent emails as a test
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

# Gmail API scopes - readonly is sufficient for fetching newsletters
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_credentials() -> Credentials:
    """Get or refresh Gmail API credentials."""
    creds_path = Path(os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"))
    token_path = Path(os.getenv("GMAIL_TOKEN_PATH", "token.json"))

    creds = None

    # Load existing token if available
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        print(f"✓ Loaded existing token from {token_path}")

    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("↻ Refreshing expired token...")
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print(f"✗ Credentials file not found: {creds_path}")
                print("\nMake sure you've:")
                print("  1. Downloaded your OAuth credentials from Google Cloud Console")
                print("  2. Renamed the file to 'credentials.json'")
                print("  3. Placed it in your project root")
                raise FileNotFoundError(f"Missing {creds_path}")

            print("Opening browser for authentication...")
            print("(If browser doesn't open, check the terminal for a URL)\n")

            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the token for future runs
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        print(f"✓ Saved token to {token_path}")

    return creds


def test_fetch_emails(creds: Credentials, max_results: int = 5):
    """Fetch recent emails to verify the connection works."""
    print(f"\nFetching {max_results} most recent emails...\n")

    service = build("gmail", "v1", credentials=creds)

    # Get list of messages
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["INBOX"]
    ).execute()

    messages = results.get("messages", [])

    if not messages:
        print("No messages found in inbox.")
        return

    print(f"{'#':<3} {'From':<40} {'Subject':<50}")
    print("-" * 95)

    for i, msg in enumerate(messages, 1):
        # Fetch full message details
        message = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["From", "Subject"]
        ).execute()

        headers = {h["name"]: h["value"] for h in message["payload"]["headers"]}
        from_addr = headers.get("From", "Unknown")[:38]
        subject = headers.get("Subject", "(no subject)")[:48]

        print(f"{i:<3} {from_addr:<40} {subject:<50}")

    print("\n✓ Gmail API connection successful!")


def main():
    print("=" * 60)
    print("Gmail OAuth Test Script")
    print("=" * 60 + "\n")

    try:
        creds = get_credentials()
        test_fetch_emails(creds)

        print("\n" + "=" * 60)
        print("Setup complete! You're ready to start building.")
        print("=" * 60)

    except FileNotFoundError:
        exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nIf you're seeing permission errors, make sure you:")
        print("  1. Added yourself as a test user in the OAuth consent screen")
        print("  2. Enabled the Gmail API in your Google Cloud project")
        exit(1)


if __name__ == "__main__":
    main()
