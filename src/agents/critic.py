"""Critic Agent — verifies truth + ATS alignment, returns a MatchReport."""

from __future__ import annotations

import json

from src.config import MODEL_NAME, get_llm_client
from src.models import JDProfile, MasterCV, MatchReport

_SYSTEM_PROMPT = """\
You are a Resume Critic and ATS Alignment Auditor. You receive:
1. A JD Profile (what the job requires)
2. The candidate's Master CV (ground truth)
3. A generated resume (Markdown)

Your job: verify the resume and return a structured quality report.

CHECKS TO PERFORM:
1. **Keyword Coverage** — What % of JD keywords appear in the resume?
2. **Hallucination Detection** — Does the resume mention ANY technology, tool, metric, or claim
   that does NOT exist in the Master CV? Flag each one.
3. **Bullet Quality** — Are bullets concise (1–2 lines), impact-oriented, and using strong verbs?
4. **Missing Must-Haves** — Are any must-have skills from the JD completely absent from the resume?
5. **Evidence Mapping** — For each JD responsibility/requirement, what resume bullet addresses it?

Return VALID JSON matching this schema:
{
  "keyword_coverage": 0.0,
  "matched_keywords": [],
  "missing_keywords": [],
  "evidence_map": [
    {"jd_item": "JD requirement text", "evidence": "resume bullet or 'NOT FOUND'"}
  ],
  "risk_flags": ["any hallucinated tech/metrics or other issues"],
  "score": 0.0,
  "fixes": ["specific actionable improvement instructions"]
}

Rules:
- keyword_coverage is a float 0.0–1.0 (fraction of JD keywords found in resume).
- score is 0–100 overall quality score.
- Be specific in fixes — say exactly what to change and why.
- risk_flags should list any content in the resume not backed by the Master CV.
- Return ONLY the JSON, no extra text.
"""


def critique_resume(
    jd_profile: JDProfile,
    master_cv: MasterCV,
    resume_md: str,
) -> MatchReport:
    """Critique a resume and return a structured MatchReport."""
    client = get_llm_client()

    user_msg = (
        "Critique this resume against the JD and Master CV.\n\n"
        f"## JD Profile\n```json\n{jd_profile.model_dump_json(indent=2)}\n```\n\n"
        f"## Master CV (ground truth)\n```json\n{master_cv.model_dump_json(indent=2)}\n```\n\n"
        f"## Generated Resume\n{resume_md}"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)  # type: ignore[arg-type]
    return MatchReport(**data)
