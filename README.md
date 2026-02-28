# AI Newsletter Curator

A personal knowledge management system that ingests AI newsletters from Gmail and Yahoo, follows article links, and lets you chat with your archive using semantic search and GPT-4o-mini.

## What it does

1. **Ingests** emails from whitelisted AI newsletter senders (Gmail OAuth2 + Yahoo IMAP)
2. **Fetches** linked articles from each email (blog posts, arXiv papers, GitHub repos, etc.)
3. **Embeds** all content into ChromaDB using OpenAI `text-embedding-3-small`
4. **Chat UI** — ask natural-language questions and get answers synthesized from your archive with source citations

## Current Status

- Email ingestion working (Gmail + Yahoo)
- Sender whitelist (`ai_sender_whitelist.json`) filters to AI-relevant senders
- Article fetching via `trafilatura` for quality content extraction
- RAG pipeline: embed → ChromaDB retrieval → GPT-4o-mini synthesis
- Chat UI with conversation history and source citations

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure environment

Create a `.env` file in the project root:

```bash
# Gmail OAuth
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json

# Yahoo IMAP
YAHOO_EMAIL=your-email@yahoo.com
YAHOO_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
YAHOO_FOLDER=INBOX

# OpenAI (embeddings + chat)
OPENAI_API_KEY=sk-...

# Storage (defaults shown)
CHROMA_DB_PATH=./chroma_db
SQLITE_DB_PATH=./data/curator.db

# Optional overrides
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
CHUNK_SIZE_TOKENS=500
```

### 3. Gmail OAuth setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the Gmail API
3. Create OAuth 2.0 credentials (Desktop app type)
4. Download the credentials JSON → save as `credentials.json` in the project root
5. Add yourself as a test user in the OAuth consent screen
6. Run `python test_gmail_auth.py` — a browser window will open for authentication
7. `token.json` will be created for future runs

> **Note:** OAuth tokens for apps in Testing mode expire after 7 days. Delete `token.json` and re-run the test script to refresh.

### 4. Yahoo IMAP setup

1. Enable 2-step verification on your Yahoo account
2. Generate an App Password: Account Security → Generate app password
3. Set `YAHOO_EMAIL` and `YAHOO_APP_PASSWORD` in `.env`
4. Run `python test_yahoo_auth.py` to verify

## Usage

### Run ingestion

```bash
# Ingest last 7 days from all sources (email bodies + linked articles)
python scripts/run_ingestion.py --source all --days 7

# Gmail only, last 14 days, skip article fetching (faster)
python scripts/run_ingestion.py --source gmail --days 14 --skip-articles

# Yahoo only
python scripts/run_ingestion.py --source yahoo --days 7
```

### Launch the chat UI

```bash
streamlit run src/app/streamlit_app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

Example questions:
- *"What's the latest research on RAG architectures?"*
- *"Summarise recent papers on LLM fine-tuning"*
- *"What AI tools were released this week?"*
- *"Tell me more about that last paper"* ← follow-up questions work

### Manage the sender whitelist

Edit `ai_sender_whitelist.json` to add or remove newsletter senders. Each entry needs a `name`, `email`, and `domain`. The ingestion script will log how many emails matched the whitelist per run.

## Project Structure

```
├── src/
│   ├── config.py               # pydantic-settings (.env loader)
│   ├── models.py               # Pydantic data models
│   ├── exceptions.py           # Custom exception hierarchy
│   ├── ingestion/
│   │   ├── gmail_client.py     # Gmail API client
│   │   ├── yahoo_client.py     # Yahoo IMAP client
│   │   └── whitelist.py        # Sender whitelist filter
│   ├── processing/
│   │   ├── parser.py           # HTML → clean text + link extraction
│   │   ├── classifier.py       # Heuristic content-type classifier
│   │   ├── embeddings.py       # Chunking + OpenAI embeddings
│   │   └── link_fetcher.py     # Article URL detection + fetching
│   ├── storage/
│   │   ├── database.py         # SQLAlchemy ORM (emails, articles, chunks)
│   │   └── vector_store.py     # ChromaDB interface
│   └── app/
│       ├── chat.py             # RAG query engine
│       └── streamlit_app.py    # Chat UI
├── scripts/
│   └── run_ingestion.py        # Ingestion CLI
├── tests/                      # Pytest test suite
├── ai_sender_whitelist.json    # Whitelisted newsletter senders
├── pyproject.toml
└── .env                        # Not committed
```

## Architecture

```
Email providers (Gmail / Yahoo)
        ↓ fetch_emails()
   RawEmail objects
        ↓ parse_email()
  ParsedEmail + links
        ↓ classify()         ↓ fetch_articles_from_email()
  ContentType assigned     FetchedArticle objects
        ↓                          ↓
        └──── embed_text() ────────┘
              (tiktoken chunks)
                    ↓
              OpenAI embeddings
                    ↓
         ChromaDB (vectors) + SQLite (metadata)
                    ↓
         Streamlit chat UI
         embed query → search → GPT-4o-mini → answer + sources
```

## Development

```bash
# Format
black .

# Lint
ruff check .

# Tests
pytest tests/ -v
```
