"""Configuration — loads .env and exposes settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ── LLM settings ──────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o-mini")

# ── Paths ─────────────────────────────────────────────────────
DATA_DIR = _PROJECT_ROOT / "data"
MASTER_CV_PATH = DATA_DIR / "master_cv.json"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def get_llm_client() -> OpenAI:
    """Return a configured OpenAI client (works with Ollama/Groq too)."""
    return OpenAI(
        api_key=OPENAI_API_KEY or "ollama",
        base_url=OPENAI_BASE_URL,
    )
