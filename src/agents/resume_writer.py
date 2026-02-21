"""Resume Writer Agent — generates a tailored Markdown resume from selected CV content."""

from __future__ import annotations

import json

from src.config import MODEL_NAME, get_llm_client
from src.models import JDProfile, MasterCV, SelectionPlan

_SYSTEM_PROMPT = """\
You are an expert Resume Writer. You produce tailored, ATS-optimized resumes in Markdown.

You will receive:
1. A JD Profile (target job requirements)
2. A Selection Plan (which experiences/projects to include)
3. The candidate's Master CV (full inventory of their experience)

STRICT RULES:
- ONLY include technologies, skills, and tools that exist in the Master CV. NEVER invent new ones.
- ONLY include metrics/numbers that appear in the Master CV bullets. NEVER fabricate statistics.
- Rewrite bullets to match JD language and emphasize impact/ownership, but keep factual content intact.
- Use strong action verbs (Built, Led, Deployed, Shipped, Designed, Optimized, Reduced, Increased).
- Keep bullets concise: 1–2 lines each.
- Order skills section: must-have skills first, then nice-to-have, then remaining.
- Include ONLY the experiences and projects specified in the Selection Plan.

OUTPUT FORMAT — produce a clean Markdown resume with these sections:
# [Candidate Name]
[Contact info line]

## Summary
[2-3 sentence professional summary tailored to the target role]

## Skills
[Comma-separated, ordered by relevance to JD]

## Experience
### [Role] — [Company]
*[Start Date] – [End Date]*
- [Bullet 1]
- [Bullet 2]
...

## Projects
### [Project Name]
- [Bullet 1]
- [Bullet 2]
...

## Education
### [Degree] — [Institution]
*[Graduation Date]*

Return ONLY the Markdown resume, no extra commentary.
"""


def generate_resume(
    jd_profile: JDProfile,
    selection_plan: SelectionPlan,
    master_cv: MasterCV,
) -> str:
    """Generate a tailored resume in Markdown."""
    client = get_llm_client()

    user_msg = (
        "Generate a tailored resume using the following inputs.\n\n"
        f"## JD Profile\n```json\n{jd_profile.model_dump_json(indent=2)}\n```\n\n"
        f"## Selection Plan\n```json\n{selection_plan.model_dump_json(indent=2)}\n```\n\n"
        f"## Master CV\n```json\n{master_cv.model_dump_json(indent=2)}\n```"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content.strip()


_IMPROVE_SYSTEM_PROMPT = """\
You are an expert Resume Editor. You receive a resume (Markdown), a critic's Match Report,
and the original JD Profile and Master CV.

Your job: improve the resume by addressing the critic's feedback.

STRICT RULES:
- ONLY use technologies, skills, and metrics from the Master CV. NEVER invent new ones.
- Address each item in the "fixes" list.
- Incorporate missing keywords WHERE they authentically apply (don't force them).
- Improve bullet clarity, impact language, and ATS keyword density.
- Keep the same Markdown structure.

Return ONLY the improved Markdown resume, no extra commentary.
"""


def improve_resume(
    jd_profile: JDProfile,
    master_cv: MasterCV,
    resume_md: str,
    match_report_json: str,
) -> str:
    """Improve a resume based on the critic's feedback."""
    client = get_llm_client()

    user_msg = (
        "Improve this resume based on the critic's feedback.\n\n"
        f"## Current Resume\n{resume_md}\n\n"
        f"## Critic's Match Report\n```json\n{match_report_json}\n```\n\n"
        f"## JD Profile\n```json\n{jd_profile.model_dump_json(indent=2)}\n```\n\n"
        f"## Master CV\n```json\n{master_cv.model_dump_json(indent=2)}\n```"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": _IMPROVE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content.strip()
