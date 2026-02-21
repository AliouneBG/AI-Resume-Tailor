"""JD Extractor Agent — turns raw job description text into a structured JDProfile."""

from __future__ import annotations

import json
import logging

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

def _fallback_extract(jd_text: str) -> JDProfile:
    """Simple regex/heuristic fallback when LLM fails."""
    lines = [L.strip() for L in jd_text.splitlines() if L.strip()]
    title = "Unknown Title"
    for line in lines:
        if line.lower().startswith("title:"):
            title = line[6:].strip()
            break
            
    if title == "Unknown Title" and lines:
        title = lines[0][:50]
        
    return JDProfile(
        target_title=title,
        must_have_skills=[],
        nice_to_have_skills=[],
        responsibilities=[],
        keywords=[],
        seniority="unknown"
    )

def extract_jd_profile(jd_text: str) -> JDProfile:
    """Call the LLM to extract a structured JDProfile from raw JD text."""
    client = get_llm_client()

    def _call(system_prompt: str) -> JDProfile | None:
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract the JD profile from this job description:\n\n{jd_text}"},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            data = _post_process(data)
            return JDProfile(**data)
        except Exception:
            return None

    # First attempt
    profile = _call(_SYSTEM_PROMPT)
    if profile:
        return profile
        
    # Second attempt (strict prompt)
    profile = _call(_STRICT_PROMPT)
    if profile:
        return profile
        
    # Ultimate fallback gracefully
    return _fallback_extract(jd_text)
