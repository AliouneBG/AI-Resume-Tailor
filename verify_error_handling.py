"""Verification script for robust error handling."""

import os
import sys
from unittest.mock import patch, MagicMock
from src.pipeline import run_pipeline
from src.exceptions import ConfigError, APIError, JDValidationError, CVValidationError
from src import config

def test_config_error():
    print("\n--- Testing ConfigError (Invalid API Key) ---")
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=True):
        # Reset cache
        config._CLIENT_CACHE = None
        try:
            run_pipeline("test jd", pass_threshold=80)
        except ConfigError as e:
            print(f"Successfully caught ConfigError: {e}")
        except Exception as e:
            print(f"FAILED: Caught unexpected exception: {type(e).__name__}: {e}")

def test_jd_validation_error():
    print("\n--- Testing JDValidationError (Empty JD) ---")
    try:
        run_pipeline("", pass_threshold=80)
    except JDValidationError as e:
        print(f"Successfully caught JDValidationError: {e}")
    except Exception as e:
        print(f"FAILED: Caught unexpected exception: {type(e).__name__}: {e}")

def test_api_retry_and_failure():
    print("\n--- Testing API Retry and Failure ---")
    with patch("src.agents.jd_extractor.get_llm_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # Simulate rate limit error (429)
        mock_client.models.generate_content.side_effect = Exception("429 Rate Limit Exceeded")
        
        try:
            # This should trigger retries and eventually fail with APIError
            run_pipeline("Software Engineer JD details here...", pass_threshold=80)
        except APIError as e:
            print(f"Successfully caught APIError after retries: {e}")
        except Exception as e:
            print(f"FAILED: Caught unexpected exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    # Ensure database is initialized
    from src.database import init_db
    init_db()
    
    test_config_error()
    test_jd_validation_error()
    test_api_retry_and_failure()
