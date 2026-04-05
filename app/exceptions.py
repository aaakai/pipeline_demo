"""Application specific exceptions."""


class AppError(Exception):
    """Base class for user-facing application errors."""


class FetchError(AppError):
    """Raised when an HTTP request fails."""


class ExtractionError(AppError):
    """Raised when text extraction fails."""


class CleaningError(AppError):
    """Raised when text cleaning fails."""


class LLMError(AppError):
    """Raised when LLM adaptation fails."""
