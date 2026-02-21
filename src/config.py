"""Configuration — loads .env and exposes settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# ── LLM settings ──────────────────────────────────────────────
# We will read GEMINI_API_KEY dynamically inside get_llm_client 
# to allow runtime overrides (like from Streamlit).
# Gemini provides an OpenAI-compatible endpoint
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
# You can use gemini-2.5-flash or gemini-2.0-flash, standard testing model
MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-2.5-flash")

# ── Job search settings ──────────────────────────────────────
SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")
GOOGLE_CLOUD_PROJECT: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# ── Paths ─────────────────────────────────────────────────────
DATA_DIR = _PROJECT_ROOT / "data"
MASTER_CV_PATH = DATA_DIR / "master_cv.json"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def get_llm_client() -> OpenAI:
    """Return a configured OpenAI client (works with Gemini OpenAI compatibility layer)."""
    # Allow dynamic override from os.environ (e.g. set by Streamlit UI)
    api_key = os.environ.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = "missing-key"
    return OpenAI(
        api_key=api_key,
        base_url=OPENAI_BASE_URL,
    )
