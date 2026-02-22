"""Base agent utilities including retry logic."""

import logging
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from src.exceptions import APIError, ConfigError

logger = logging.getLogger(__name__)

def retry_on_api_error(func):
    """Decorator to retry agent functions on transient API errors."""
    @wraps(func)
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(APIError),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying {func.__name__} after error: {retry_state.outcome.exception()}. "
            f"Attempt {retry_state.attempt_number}/5"
        ),
        reraise=True
    )
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # If it's already an APIError or ConfigError, re-raise to let tenacity decide
            if isinstance(e, (APIError, ConfigError)):
                raise e
            
            # Map other exceptions to APIError if they seem transient or API-related
            err_msg = str(e).lower()
            
            # These are RETRYABLE (APIError)
            if any(token in err_msg for token in ("rate limit", "429", "quota", "too many requests")):
                raise APIError(f"Rate limit exceeded: {e}", status_code=429)
            if any(token in err_msg for token in ("timeout", "408", "deadline exceeded")):
                raise APIError(f"Request timed out: {e}", status_code=408)
            if any(token in err_msg for token in ("500", "502", "503", "504", "server error", "unavailable")):
                raise APIError(f"Transient API error: {e}", status_code=500)
            
            # These are FATAL (Don't wrap in APIError to avoid retry)
            if any(token in err_msg for token in ("credential", "auth", "permission", "unauthorized", "invalid_argument", "401", "403")):
                raise ConfigError(f"Authentication/Permission failed: {e}")

            # For everything else, wrap in a generic Exception but don't retry by default
            # We raise the original exception wrapped in a clear message
            raise APIError(f"Unexpected fatal API error in {func.__name__}: {e}") from e
            
    return wrapper
