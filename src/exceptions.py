"""Custom exception hierarchy for the AI Newsletter Curator."""


class CuratorError(Exception):
    """Base exception for all curator errors."""


class IngestionError(CuratorError):
    """Raised when email ingestion fails."""


class GmailError(IngestionError):
    """Raised when Gmail-specific operations fail."""


class YahooError(IngestionError):
    """Raised when Yahoo-specific operations fail."""


class ProcessingError(CuratorError):
    """Raised when content processing fails."""


class ParsingError(ProcessingError):
    """Raised when email parsing fails."""


class EmbeddingError(ProcessingError):
    """Raised when embedding generation fails."""


class StorageError(CuratorError):
    """Raised when storage operations fail."""
