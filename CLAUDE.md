# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is an early-stage project for building an AI newsletter curator. Currently in the authentication/setup phase with test scripts for Gmail and Yahoo email access. The main application architecture (ingestion pipeline, vector storage, UI) is planned but not yet implemented.

## Current Structure

```
.
├── test_gmail_auth.py    # Gmail OAuth2 test script
├── test_yahoo_auth.py    # Yahoo IMAP test script
├── pyproject.toml        # Project dependencies and metadata
├── .env                  # Environment variables (not in git)
├── credentials.json      # Gmail OAuth credentials (not in git)
└── token.json           # Gmail access token (not in git)
```

The `src/` directory structure described in "Planned Architecture" below doesn't exist yet.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment (assuming .venv exists)
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Install with local embeddings support (avoids OpenAI API dependency)
pip install -e ".[local-embeddings]"
```

### Code Quality
```bash
# Format code with Black
black .

# Lint with Ruff
ruff check .
ruff check --fix .  # Auto-fix issues

# Run tests (when tests/ directory exists)
pytest
pytest tests/test_specific.py  # Single test file
pytest -v  # Verbose output
```

### Testing Email Authentication
```bash
# Test Gmail OAuth flow (opens browser for auth)
python test_gmail_auth.py

# Test Yahoo IMAP connection
python test_yahoo_auth.py
```

## Authentication Setup

### Gmail OAuth2
1. Create a project in Google Cloud Console
2. Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app type)
4. Download credentials JSON and save as `credentials.json` in project root
5. Add yourself as a test user in OAuth consent screen
6. Set in `.env`:
   ```
   GMAIL_CREDENTIALS_PATH=credentials.json
   GMAIL_TOKEN_PATH=token.json
   ```
7. Run `python test_gmail_auth.py` - will open browser for OAuth flow
8. `token.json` will be created for future authenticated requests

### Yahoo IMAP
1. Enable 2-step verification on Yahoo account
2. Generate an App Password (Account Security > Generate app password)
3. Set in `.env`:
   ```
   YAHOO_EMAIL=your-email@yahoo.com
   YAHOO_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
   YAHOO_FOLDER=INBOX
   ```
4. Run `python test_yahoo_auth.py` to verify connection

## Planned Architecture

### Email Ingestion
- **Gmail**: OAuth2 via `google-api-python-client`
- **Yahoo**: IMAP via `imap-tools`
- Polling-based ingestion (weekly or on-demand)

### Processing Pipeline
1. Parse HTML/text from emails
2. Extract links and fetch article metadata
3. Classify content type (paper, tutorial, course, news, tool)
4. Chunk content (~500 tokens per chunk with `tiktoken`)
5. Generate embeddings (OpenAI API or local `sentence-transformers`)
6. Store in ChromaDB with metadata

### Storage
- **Vector Store**: ChromaDB (local, file-based)
- **Metadata**: SQLite via SQLAlchemy (emails, sources, tags, curation status)

### Frontend
- Streamlit UI for search, browsing, and curation
- Features: semantic search, category/date/source filters, read/starred status, weekly digest

### Planned Project Structure
```
src/
├── ingestion/           # Email clients and content extraction
│   ├── gmail_client.py  # Gmail API integration
│   └── yahoo_client.py  # Yahoo IMAP integration
├── processing/          # Chunking, embedding, classification
│   ├── embeddings.py    # Embedding generation
│   └── classifier.py    # Content type classification
├── storage/             # Vector DB and SQLite interfaces
│   └── vector_store.py  # ChromaDB interface
└── app/                 # Streamlit application
    └── streamlit_app.py # Main UI application
scripts/
└── run_ingestion.py     # Manual ingestion runner
tests/                   # Pytest test suite
```

### Planned Common Tasks

**Running ingestion manually** (once implemented):
```bash
python scripts/run_ingestion.py --source gmail --days 7
```

**Running the Streamlit app** (once implemented):
```bash
streamlit run src/app/streamlit_app.py
```

**Adding a new email source**:
1. Create client in `src/ingestion/`
2. Implement `fetch_emails()` returning `List[RawEmail]`
3. Register in `scripts/run_ingestion.py`

**Adding a new content classifier**:
1. Add classification logic in `src/processing/classifier.py`
2. Update `ContentType` enum if adding new category
3. May need to update UI filters in Streamlit app

## Code Conventions

### Style
- Python 3.11+ with type hints throughout
- Pydantic models for all data structures
- Google-style docstrings for public functions
- Black formatting (line length 88)
- Ruff linting (see `pyproject.toml` for rules)

### Naming
- `snake_case` for functions and variables
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Prefix private functions with underscore

### Error Handling
- Custom exceptions in `src/exceptions.py` (when created)
- Log errors with context (email ID, source, etc.)
- Fail gracefully in ingestion - one bad email shouldn't stop the batch

## Environment Variables

Create a `.env` file in the project root (never committed to git):

```bash
# Gmail OAuth
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json

# Yahoo IMAP
YAHOO_EMAIL=your-email@yahoo.com
YAHOO_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
YAHOO_FOLDER=INBOX

# OpenAI (if using OpenAI embeddings)
OPENAI_API_KEY=sk-...

# Database paths (defaults shown)
CHROMA_DB_PATH=./chroma_db
SQLITE_DB_PATH=./data/curator.db
```

## Dependencies Notes

- **ChromaDB**: Requires SQLite 3.35+ (may need system upgrade on older systems)
- **Gmail API**: Requires OAuth credentials JSON from Google Cloud Console
- **Local Embeddings**: Use `sentence-transformers` with `all-MiniLM-L6-v2` model to avoid OpenAI API dependency
- **Token Counting**: `tiktoken` for accurate token counts when chunking text for embeddings
