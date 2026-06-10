#!/bin/bash
# ============================================================================
# curator-env.sh — Load newsletter curator secrets from macOS Keychain
# ============================================================================
# Reads secrets stored under service "autopilot" in macOS Keychain and
# exports them as environment variables. Source this before running any
# curator script, or use it to regenerate the .env file.
#
# Usage:
#   source scripts/curator-env.sh          # export to current shell
#   bash scripts/curator-env.sh --write    # write/update .env file
# ============================================================================

KEYCHAIN_SERVICE="autopilot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

get_secret() {
  security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$1" -w 2>/dev/null
}

GMAIL_APP_PASSWORD=$(get_secret GMAIL_APP_PASSWORD)
GMAIL2_APP_PASSWORD=$(get_secret GMAIL2_APP_PASSWORD)
YAHOO_APP_PASSWORD=$(get_secret YAHOO_APP_PASSWORD)
OPENAI_API_KEY=$(get_secret OPENAI_API_KEY)
ANTHROPIC_API_KEY=$(get_secret ANTHROPIC_API_KEY)
TELEGRAM_BOT_TOKEN=$(get_secret TELEGRAM_BOT_TOKEN)

if [ "${1:-}" = "--write" ]; then
  cat > "$PROJECT_DIR/.env" <<EOF
# Gmail IMAP (App Password — no OAuth)
GMAIL_EMAIL=stephen.merritt74@gmail.com
GMAIL_APP_PASSWORD=${GMAIL_APP_PASSWORD}

# Gmail IMAP (secondary account)
GMAIL2_EMAIL=themerrittocractic@gmail.com
GMAIL2_APP_PASSWORD=${GMAIL2_APP_PASSWORD}

# Yahoo IMAP
YAHOO_EMAIL=s_merritt03@yahoo.com
YAHOO_APP_PASSWORD=${YAHOO_APP_PASSWORD}
YAHOO_FOLDER=INBOX

# OpenAI (embeddings + chat)
OPENAI_API_KEY=${OPENAI_API_KEY}

# Anthropic (digest synthesis)
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

# Telegram (digest delivery)
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=8676616323

# Storage
CHROMA_DB_PATH=${PROJECT_DIR}/chroma_db
SQLITE_DB_PATH=${PROJECT_DIR}/data/curator.db

# Model settings
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
CHUNK_SIZE_TOKENS=500
EOF
  echo "✅ .env written to $PROJECT_DIR/.env"
else
  export GMAIL_EMAIL="stephen.merritt74@gmail.com"
  export GMAIL_APP_PASSWORD
  export GMAIL2_EMAIL="themerrittocractic@gmail.com"
  export GMAIL2_APP_PASSWORD
  export YAHOO_EMAIL="s_merritt03@yahoo.com"
  export YAHOO_APP_PASSWORD
  export YAHOO_FOLDER="INBOX"
  export OPENAI_API_KEY
  export ANTHROPIC_API_KEY
  export TELEGRAM_BOT_TOKEN
  export TELEGRAM_CHAT_ID="8676616323"
  export CHROMA_DB_PATH="/Users/merrittocracyclaw/ai-newsletter-curator/chroma_db"
  export SQLITE_DB_PATH="/Users/merrittocracyclaw/ai-newsletter-curator/data/curator.db"
fi
