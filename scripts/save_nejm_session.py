"""One-time helper: log in to NEJM AI interactively and save browser session.

Usage:
    python scripts/save_nejm_session.py

Your real Chrome browser will open (bypassing Cloudflare bot detection).
Log in, navigate to ai.nejm.org, then press Enter here. The session state
(cookies + localStorage) is saved to data/nejm_session.json.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

SESSION_PATH = Path("data/nejm_session.json")
SIGNIN_URL = "https://myaccount.nejm.org/signin"


def main() -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # Use system Chrome — Cloudflare trusts it; Playwright's Chromium gets blocked.
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            # Realistic viewport + UA so the session looks like a normal browser.
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print(f"Opening {SIGNIN_URL} in Chrome …")
        page.goto(SIGNIN_URL)

        print("\n1. Log in with your NEJM credentials.")
        print("2. Then navigate to https://ai.nejm.org and confirm you can see articles.")
        input("3. Press Enter here to save the session: ")

        context.storage_state(path=str(SESSION_PATH))
        browser.close()

    print(f"\nSession saved to {SESSION_PATH}")
    print(
        "Verify with:\n"
        "  python -c \"from src.processing.nejm_fetcher import fetch_nejm_article; "
        "from pathlib import Path; "
        "a = fetch_nejm_article('https://ai.nejm.org/doi/full/10.1056/AIoa2500487', "
        "Path('data/nejm_session.json')); print(a.title, len(a.clean_text))\""
    )


if __name__ == "__main__":
    main()
