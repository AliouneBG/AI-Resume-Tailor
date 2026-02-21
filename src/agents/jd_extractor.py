"""JD Extractor Agent — turns raw job description text into a structured JDProfile."""

from __future__ import annotations

import json
import logging

from google.genai import types

from src.config import MODEL_NAME, get_llm_client
from src.models import JDProfile

_SYSTEM_PROMPT = """\
You are a Job Description Analyst. Your ONLY job is to extract structured information
from a raw job description.

Return VALID JSON matching this schema exactly:
{
  "target_title": "string — the job title",
  "must_have_skills": ["string — hard requirements explicitly stated"],
  "nice_to_have_skills": ["string — preferred / nice-to-have items"],
  "responsibilities": ["string — key responsibilities"],
  "keywords": ["string — tools, technologies, methodologies, frameworks mentioned"],
  "seniority": "string — junior / mid / senior / staff / unknown"
}

Rules:
- Only include skills/keywords actually stated in the JD.
- Separate must-have vs nice-to-have based on language ("required" vs "preferred", "bonus", etc.).
- Keep each item short — 2-6 words max.
- De-duplicate keywords and skills.
- If seniority is unclear, put "unknown".
- Return ONLY the JSON, no extra text.
"""

_STRICT_PROMPT = """\
You are a Job Description Analyst. Your ONLY job is to extract structured information
from a raw job description. YOU MUST RETURN VALID JSON ONLY. NO MARKDOWN, NO EXPLANATION.

Return VALID JSON matching this schema exactly:
{
  "target_title": "string — the job title",
  "must_have_skills": ["string — hard requirements explicitly stated"],
  "nice_to_have_skills": ["string — preferred / nice-to-have items"],
  "responsibilities": ["string — key responsibilities"],
  "keywords": ["string — tools, technologies, methodologies, frameworks mentioned"],
  "seniority": "string — junior / mid / senior / staff / unknown"
}
"""

def _clean_item(item: str) -> str:
    """Trim item to 2-6 words max."""
    words = str(item).strip().split()
    if len(words) > 6:
        words = words[:6]
    return " ".join(words)

def _post_process(data: dict) -> dict:
    # Ensure target_title is a non-empty string
    title = str(data.get("target_title", "")).strip()
    data["target_title"] = title if title else "Unknown Title"

    for key in ["must_have_skills", "nice_to_have_skills", "responsibilities", "keywords"]:
        items = data.get(key, [])
        if not isinstance(items, list):
            items = []
            
        final_list = []
        seen_lower = set()
        
        for i in items:
            if not isinstance(i, str):
                continue
            cleaned = _clean_item(i)
            if not cleaned:
                continue
                
            # Normalize common variants only if term appears
            # "CI CD" -> "CI/CD", "Postgres" -> "PostgreSQL"
            if cleaned.lower() == "ci cd":
                cleaned = "CI/CD"
            elif cleaned.lower() == "postgres":
                cleaned = "PostgreSQL"
                
            lower_clean = cleaned.lower()
            if lower_clean not in seen_lower:
                seen_lower.add(lower_clean)
                final_list.append(cleaned)
        data[key] = final_list

    seniority = str(data.get("seniority", "")).strip().lower()
    if seniority not in {"junior", "mid", "senior", "staff", "unknown"}:
        seniority = "unknown"
    data["seniority"] = seniority
    
    return data

logger = logging.getLogger(__name__)


def _is_meaningful(profile: JDProfile) -> bool:
    """Return True if the profile has at least some useful content."""
    return bool(profile.responsibilities or profile.must_have_skills or profile.keywords)


def extract_jd_profile(jd_text: str) -> JDProfile:
    """Call the LLM to extract a structured JDProfile from raw JD text.

    Raises RuntimeError if both LLM attempts fail or return empty results.
    """
    client = get_llm_client()
    last_error: Exception | None = None

    def _call(system_prompt: str) -> JDProfile | None:
        nonlocal last_error
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=f"Extract the JD profile from this job description:\n\n{jd_text}",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text
            data = json.loads(raw)
            data = _post_process(data)
            return JDProfile(**data)
        except Exception as e:
            logger.warning("JD extraction attempt failed: %s", e)
            last_error = e
            return None

    for prompt in (_SYSTEM_PROMPT, _STRICT_PROMPT):
        profile = _call(prompt)
        if profile and _is_meaningful(profile):
            return profile

    if last_error is not None:
        raise RuntimeError(
            f"JD parsing failed after 2 attempts. Last error: {last_error}\n\n"
            "Check that your API key / credentials are valid and the model is reachable."
        ) from last_error

    raise RuntimeError(
        "JD parsing returned no usable data (responsibilities, skills, and keywords are all "
        "empty). The job description may be too short, paywalled, or in an unsupported format."
    )
