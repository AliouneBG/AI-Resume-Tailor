"""Custom exceptions for the Resume Tailor application."""

class ResumeTailorError(Exception):
    """Base exception for all Resume Tailor errors."""
    pass

class APIError(ResumeTailorError):
    """Raised when an external API (Gemini, SerpApi) fails."""
    def __init__(self, message: str, status_code: int = None, details: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}

class DatabaseError(ResumeTailorError):
    """Raised when a database operation fails."""
    pass

class ConfigError(ResumeTailorError):
    """Raised when there is a configuration issue (e.g., missing API keys)."""
    pass

class ValidationError(ResumeTailorError):
    """Raised when input validation fails (e.g., empty JD, invalid CV format)."""
    pass

class JDValidationError(ValidationError):
    """Specific error for Job Description validation."""
    pass

class CVValidationError(ValidationError):
    """Specific error for Master CV validation."""
    pass

class ResponseParseError(ResumeTailorError):
    """Raised when the LLM response cannot be parsed correctly."""
    pass
