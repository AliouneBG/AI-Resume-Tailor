"""Configuration — loads .env and exposes settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from src.exceptions import ConfigError

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# ── LLM settings ──────────────────────────────────────────────
# We will read GEMINI_API_KEY dynamically inside get_llm_client
# to allow runtime overrides (like from Streamlit).
# You can use gemini-2.0-flash for best balance of speed and quality
_FALLBACK_MODEL = "gemini-flash-latest"

def get_model_name(is_fallback: bool = False) -> str:
    """Return the current model name, supporting a fallback choice."""
    if is_fallback:
        return _FALLBACK_MODEL
    _primary = os.getenv("MODEL_NAME", "gemini-2.0-flash")
    return _primary if _primary.startswith("gemini") else "gemini-2.0-flash"

# Use a property or a dynamic helper for MODEL_NAME
class _Config:
    @property
    def MODEL_NAME(self) -> str:
        return get_model_name()

# We'll stick to a function for now and update agents to use it if needed,
# or just make get_model_name the source of truth.
MODEL_NAME: str = get_model_name() # Initial value

# ── Job search settings ──────────────────────────────────────
SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")
GOOGLE_CLOUD_PROJECT: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ── Paths ─────────────────────────────────────────────────────
DATA_DIR = _PROJECT_ROOT / "data"
MASTER_CV_PATH = DATA_DIR / "master_cv.json"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


# ── LLM Client Singleton ───────────────────────────────────────
_CLIENT_CACHE: genai.Client | None = None

def get_llm_client() -> genai.Client:
    """Return a configured Gemini client (cached)."""
    global _CLIENT_CACHE
    if _CLIENT_CACHE:
        return _CLIENT_CACHE

    api_key = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        _CLIENT_CACHE = genai.Client(api_key=api_key)
        return _CLIENT_CACHE

    # Fall back to GCP Application Default Credentials
    if GOOGLE_CLOUD_PROJECT:
        try:
            _CLIENT_CACHE = genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT, location=GOOGLE_CLOUD_LOCATION)
            return _CLIENT_CACHE
        except Exception as e:
            raise ConfigError(f"Vertex AI initialization failed: {e}")

    try:
        import google.auth
        import google.auth.transport.requests
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/generative-language"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        _CLIENT_CACHE = genai.Client(api_key=credentials.token)
        return _CLIENT_CACHE
    except Exception as e:
        raise ConfigError(
            "No Gemini authentication found. Tried in order:\n"
            "  1. GEMINI_API_KEY environment variable — not set\n"
            f"  2. Vertex AI via GOOGLE_CLOUD_PROJECT — not set\n"
            f"  3. GCP Application Default Credentials — failed: {e}\n"
            "Set GEMINI_API_KEY, or configure GOOGLE_CLOUD_PROJECT and run "
            "'gcloud auth application-default login'."
        ) from e
