"""
Test script to verify Yahoo IMAP setup.

Run this from your project root:
    python test_yahoo_auth.py

This will:
1. Connect to Yahoo via IMAP using your app password
2. Fetch and display your 5 most recent emails as a test
"""

import os
from dotenv import load_dotenv
from imap_tools import MailBox, AND

# Load environment variables
load_dotenv()

YAHOO_IMAP_SERVER = "imap.mail.yahoo.com"


def test_fetch_emails(max_results: int = 5):
    """Connect to Yahoo and fetch recent emails."""
    
    email = os.getenv("YAHOO_EMAIL")
    password = os.getenv("YAHOO_APP_PASSWORD")
    folder = os.getenv("YAHOO_FOLDER", "INBOX")

    if not email or not password:
        print("✗ Missing environment variables!")
        print("\nMake sure your .env file contains:")
        print("  YAHOO_EMAIL=your-email@yahoo.com")
        print("  YAHOO_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx")
        return False

    print(f"Connecting to Yahoo IMAP as {email}...")
    print(f"Folder: {folder}\n")

    try:
        with MailBox(YAHOO_IMAP_SERVER).login(email, password, folder) as mailbox:
            print(f"✓ Connected successfully!\n")
            print(f"Fetching {max_results} most recent emails...\n")

            # Fetch recent emails (newest first)
            messages = list(mailbox.fetch(limit=max_results, reverse=True))

            if not messages:
                print("No messages found in inbox.")
                return True

            print(f"{'#':<3} {'From':<40} {'Subject':<50}")
            print("-" * 95)

            for i, msg in enumerate(messages, 1):
                from_addr = str(msg.from_)[:38]
                subject = (msg.subject or "(no subject)")[:48]
                print(f"{i:<3} {from_addr:<40} {subject:<50}")

            print("\n✓ Yahoo IMAP connection successful!")
            return True

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure 2-step verification is enabled on your Yahoo account")
        print("  2. Verify you're using an App Password, not your regular password")
        print("  3. Check that the app password doesn't have extra spaces")
        print("  4. Try generating a new app password if this one isn't working")
        return False


def main():
    print("=" * 60)
    print("Yahoo IMAP Test Script")
    print("=" * 60 + "\n")

    success = test_fetch_emails()

    print("\n" + "=" * 60)
    if success:
        print("Setup complete! Yahoo mail access is working.")
    else:
        print("Setup incomplete. See errors above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
