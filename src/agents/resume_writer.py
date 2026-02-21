"""Resume Writer Agent — generates a tailored, STAR-method, ATS-optimized Markdown resume.

This is the core "writer" in the pipeline:
  JDProfile + SelectionPlan + MasterCV → tailored resume (Markdown)

Enhancement features:
  - STAR method bullet rewriting (Situation → Task → Action → Result)
  - ATS keyword mirroring from the JD
  - Anti-hallucination guardrails
  - Quantification preservation
  - Professional summary tailored per role
"""

from __future__ import annotations

import json

from src.config import MODEL_NAME, get_llm_client
from src.models import JDProfile, MasterCV, SelectionPlan


# ── STAR Method Generation Prompt ─────────────────────────────

_SYSTEM_PROMPT = """\
You are an elite Resume Writer who specializes in ATS-optimized, STAR-method resumes.
You have placed thousands of candidates at top companies by crafting resumes that pass
ATS filters AND impress human reviewers.

## YOUR INPUTS
1. **JD Profile** — structured job requirements (must-haves, nice-to-haves, keywords)
2. **Selection Plan** — which experiences/projects to include, pre-ranked by relevance
3. **Master CV** — the candidate's complete, factual career inventory (GROUND TRUTH)

## STAR METHOD FOR BULLETS
Rewrite EVERY bullet using the STAR framework compressed into 1–2 lines:
- **S/T** (Situation/Task): Brief context or challenge (optional if obvious)
- **A** (Action): What the candidate DID — use strong action verbs
- **R** (Result): Quantified outcome or impact

### STAR Examples:
❌ WEAK:  "Worked on microservices"
✅ STRONG: "Architected 3 microservices handling 50K+ RPM on AWS ECS, reducing API latency by 40%"

❌ WEAK:  "Helped with database optimization"
✅ STRONG: "Optimized PostgreSQL queries for reporting endpoints, reducing average query time from 800ms to 120ms (85% improvement)"

❌ WEAK:  "Built a dashboard"
✅ STRONG: "Developed customer-facing React dashboard serving 10K+ MAU with 99.9% uptime, enabling real-time analytics"

## ATS KEYWORD OPTIMIZATION
- Mirror the JD's EXACT terminology in your bullets wherever factually accurate.
  - If JD says "microservices architecture" and CV says "broke up monolith" → write "microservices architecture"
  - If JD says "CI/CD pipelines" and CV says "automated deployments" → write "CI/CD pipelines"
- Front-load the most important JD keywords in the Skills section.
- Weave must-have keywords naturally into the Summary and bullet points.
- Use the SAME casing as the JD (e.g., "Kubernetes" not "K8s" if JD says "Kubernetes").

## ANTI-HALLUCINATION RULES (CRITICAL)
1. ONLY include technologies, tools, and frameworks present in the Master CV. NEVER invent.
2. ONLY use metrics/numbers that exist in the Master CV bullets. NEVER fabricate.
3. If a metric exists (e.g., "50K+ RPM"), you may rephrase it but NEVER change the number.
4. You may COMBINE two related bullets into one stronger STAR bullet.
5. You may ADD context verbs (Architected, Spearheaded) but NOT context facts.

## QUANTIFICATION RULES
- Preserve ALL numbers from the Master CV (users, RPM, %, time savings, team sizes).
- Add percentage improvements where both numbers exist: "from 800ms to 120ms (85% improvement)"
- If the Master CV bullet has no number, DO NOT invent one. Use qualitative impact instead:
  "Streamlined deployment workflow, significantly reducing release cycle time"

## PROFESSIONAL SUMMARY
Write a 2–3 sentence summary that:
- Opens with years of experience + core identity matching the target title
- Highlights 2–3 most relevant strengths from the JD's must-have skills
- Ends with a value proposition tied to the JD's top responsibility
- Uses JD keywords naturally

## OUTPUT FORMAT — Markdown resume with these sections IN ORDER:

# [Full Name]
[Email] | [Phone] | [LinkedIn](URL) | [GitHub](URL)

## Summary
[2–3 sentence professional summary tailored to target role]

## Technical Skills
**Core:** [must-have skills from JD, comma-separated]
**Additional:** [nice-to-have + remaining skills, comma-separated]

## Professional Experience
### [Role Title] — [Company Name]
*[Start Date] – [End Date]*
- [STAR bullet 1 — highest impact, most JD-relevant]
- [STAR bullet 2]
- [STAR bullet 3]
- [STAR bullet 4 — if warranted]

### [Role Title 2] — [Company Name 2]
...

## Projects
### [Project Name] | [Technologies used]
- [STAR bullet 1]
- [STAR bullet 2]

## Education
### [Degree] — [Institution] | *[Graduation Date]*
[GPA if ≥ 3.5] | [Relevant coursework if matches JD]

## ADDITIONAL INSTRUCTIONS
- Include ONLY experiences/projects from the Selection Plan. Do NOT add others.
- Cap at 4–5 bullets per experience, 2–3 per project.
- Lead with the STRONGEST, most JD-relevant bullet for each section.
- Use varied action verbs — don't start 3 bullets with "Built."
- Skills section: group into "Core" (JD must-haves) and "Additional" (rest).
- Return ONLY the Markdown. No commentary, no explanations, no code fences.
"""


def generate_resume(
    jd_profile: JDProfile,
    selection_plan: SelectionPlan,
    master_cv: MasterCV,
) -> str:
    """Generate a tailored, STAR-method resume in Markdown.

    Args:
        jd_profile: Structured job requirements from JD Extractor.
        selection_plan: Ranked content selection from the Matcher.
        master_cv: Complete candidate CV (ground truth).

    Returns:
        ATS-optimized Markdown resume string.
    """
    client = get_llm_client()

    # Build a focused user message with clear section headers
    user_msg = _build_generation_prompt(jd_profile, selection_plan, master_cv)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.25,  # Low temp for consistency, slight creativity for phrasing
    )

    resume = response.choices[0].message.content.strip()

    # Strip any accidental code fences the LLM might wrap the output in
    resume = _strip_code_fences(resume)

    return resume


def _build_generation_prompt(
    jd_profile: JDProfile,
    selection_plan: SelectionPlan,
    master_cv: MasterCV,
) -> str:
    """Build a structured prompt for resume generation."""

    # Filter master CV to only selected items for cleaner context
    selected_exp = [
        exp for exp in master_cv.experience
        if exp.id in selection_plan.selected_experience_ids
    ]
    selected_proj = [
        proj for proj in master_cv.projects
        if proj.id in selection_plan.selected_project_ids
    ]

    # Build the prompt with clear structure
    parts = [
        "Generate a tailored STAR-method resume for this candidate.\n",

        "## Target Role",
        f"**Title:** {jd_profile.target_title}",
        f"**Seniority:** {jd_profile.seniority or 'Not specified'}\n",

        "## Must-Have Skills (prioritize these)",
        ", ".join(jd_profile.must_have_skills) + "\n",

        "## Nice-to-Have Skills",
        ", ".join(jd_profile.nice_to_have_skills) + "\n",

        "## Key Responsibilities to Address",
        "\n".join(f"- {r}" for r in jd_profile.responsibilities) + "\n",

        "## ATS Keywords to Weave In",
        ", ".join(jd_profile.keywords) + "\n",

        "## Skills (ordered by relevance)",
        ", ".join(selection_plan.skills_ordered) + "\n",

        "## Candidate Info",
        f"**Name:** {master_cv.name}",
        f"**Email:** {master_cv.email}",
        f"**Phone:** {master_cv.phone}" if master_cv.phone else "",
        f"**LinkedIn:** {master_cv.linkedin}" if master_cv.linkedin else "",
        f"**GitHub:** {master_cv.github}" if master_cv.github else "",
        f"**Website:** {master_cv.website}" if master_cv.website else "",
        "",

        "## Selected Experiences (use ONLY these, in this order)",
    ]

    for exp in selected_exp:
        parts.append(f"\n### {exp.role} — {exp.company}")
        parts.append(f"*{exp.start_date} – {exp.end_date}*")
        parts.append(f"Technologies: {', '.join(exp.technologies)}")
        parts.append("Original bullets (rewrite using STAR method):")
        for bullet in exp.bullets:
            parts.append(f"  - {bullet}")

    parts.append("\n## Selected Projects (use ONLY these)")

    for proj in selected_proj:
        parts.append(f"\n### {proj.name}")
        parts.append(f"Technologies: {', '.join(proj.technologies)}")
        if proj.url:
            parts.append(f"URL: {proj.url}")
        parts.append("Original bullets (rewrite using STAR method):")
        for bullet in proj.bullets:
            parts.append(f"  - {bullet}")

    parts.append("\n## Education")
    for edu in master_cv.education:
        parts.append(f"- {edu.degree} — {edu.institution} ({edu.graduation_date})")
        if edu.gpa:
            parts.append(f"  GPA: {edu.gpa}")
        if edu.relevant_courses:
            parts.append(f"  Courses: {', '.join(edu.relevant_courses)}")

    parts.append(f"\n## Matching Context")
    parts.append(f"Matched skills: {', '.join(selection_plan.reasoning.matched_skills)}")
    parts.append(f"Missing skills (do NOT invent these): {', '.join(selection_plan.reasoning.missing_skills)}")

    return "\n".join(parts)


# ── Self-Improvement Prompt ───────────────────────────────────

_IMPROVE_SYSTEM_PROMPT = """\
You are an elite Resume Editor specializing in ATS optimization and STAR-method bullets.

You receive:
1. A generated resume (Markdown) — the "v1"
2. A Critic's Match Report with specific issues and fixes
3. The original JD Profile and Master CV

## YOUR MISSION
Transform v1 into v2 by addressing EVERY item in the critic's feedback.

## IMPROVEMENT PRIORITIES (do these in order)
1. **Fix hallucinations** — Remove any tech/metrics not in Master CV. This is #1 priority.
2. **Fill keyword gaps** — Add missing JD keywords WHERE they authentically appear in the Master CV.
   - If the candidate has the skill but it wasn't mentioned, ADD it in the right context.
   - If the candidate does NOT have the skill, DO NOT add it. Just skip.
3. **Strengthen weak bullets** — Apply STAR method more aggressively:
   - Add Situation/Task context if missing
   - Make Action verbs stronger and more specific
   - Add Result quantification from Master CV if available
4. **Improve ATS density** — Mirror JD phrasing more precisely in bullets.
5. **Fix formatting** — Ensure consistent Markdown structure.

## ANTI-HALLUCINATION (same rules as v1)
- ONLY technologies, metrics, and facts from the Master CV.
- If the critic says "missing keyword: Go" but Go is NOT in the Master CV, DO NOT add it.
- NEVER inflate numbers. "50K+" stays "50K+", not "100K+".

## WHAT TO KEEP
- Same Markdown structure and section ordering
- Same experiences and projects (don't add/remove sections)
- Same factual content — only improve phrasing and keyword density

Return ONLY the improved Markdown resume. No commentary.
"""


def improve_resume(
    jd_profile: JDProfile,
    master_cv: MasterCV,
    resume_md: str,
    match_report_json: str,
) -> str:
    """Improve a resume based on the critic's feedback using STAR method.

    Args:
        jd_profile: Structured job requirements.
        master_cv: Complete candidate CV (ground truth for anti-hallucination).
        resume_md: The v1 resume Markdown to improve.
        match_report_json: JSON string of the critic's MatchReport.

    Returns:
        Improved v2 resume Markdown string.
    """
    client = get_llm_client()

    user_msg = (
        "Improve this resume based on the critic's feedback. "
        "Apply STAR method more aggressively and fix all identified issues.\n\n"
        f"## Current Resume (v1)\n{resume_md}\n\n"
        f"## Critic's Match Report\n```json\n{match_report_json}\n```\n\n"
        f"## JD Profile (for keyword reference)\n```json\n{jd_profile.model_dump_json(indent=2)}\n```\n\n"
        f"## Master CV (ground truth — do NOT add anything not here)\n```json\n{master_cv.model_dump_json(indent=2)}\n```"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": _IMPROVE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,  # Even lower temp for precise edits
    )

    resume = response.choices[0].message.content.strip()
    resume = _strip_code_fences(resume)

    return resume


# ── Utilities ─────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """Remove Markdown code fences if the LLM wraps its output in them."""
    lines = text.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)
