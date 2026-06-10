"""Application configuration loaded from environment variables / .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Gmail IMAP (App Password — no OAuth, no token expiry)
    gmail_email: str = ""
    gmail_app_password: str = ""

    # Yahoo IMAP
    yahoo_email: str = ""
    yahoo_app_password: str = ""
    yahoo_folder: str = "INBOX"

    # Telegram (for digest delivery)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Storage paths
    chroma_db_path: Path = Path("./chroma_db")
    sqlite_db_path: Path = Path("./data/curator.db")

    # Embedding settings
    embedding_model: str = "text-embedding-3-small"
    chunk_size_tokens: int = 500

    # Chat / RAG settings
    chat_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
