"""JD Extractor Agent — turns raw job description text into a structured JDProfile."""

from __future__ import annotations

import json

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


def extract_jd_profile(jd_text: str) -> JDProfile:
    """Call the LLM to extract a structured JDProfile from raw JD text."""
    client = get_llm_client()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract the JD profile from this job description:\n\n{jd_text}"},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)  # type: ignore[arg-type]
    return JDProfile(**data)
