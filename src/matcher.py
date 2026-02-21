"""Matcher / Selector — deterministic scoring to choose the best CV content for a JD.

No LLM needed here. Pure Python + regex matching.
"""

from __future__ import annotations

import re

from src.models import (
    Experience,
    JDProfile,
    MasterCV,
    Project,
    SelectionPlan,
    SelectionReasoning,
)

# ── Ownership / impact verbs ──────────────────────────────────
_OWNERSHIP_VERBS = {
    "built", "led", "deployed", "shipped", "designed", "architected",
    "implemented", "optimized", "reduced", "increased", "launched",
    "engineered", "developed", "managed", "delivered", "scaled",
    "automated", "migrated", "refactored", "created", "established",
}

_METRIC_RE = re.compile(r"\d+[\d,]*\.?\d*\s*[%xX]?")


def _normalize(text: str) -> str:
    """Lowercase + strip for fuzzy matching."""
    return text.lower().strip()


def _text_blob(bullets: list[str], technologies: list[str]) -> str:
    """Combine bullets + tech into a single searchable text blob."""
    return _normalize(" ".join(bullets + technologies))


def _score_item(
    blob: str,
    bullets: list[str],
    jd: JDProfile,
) -> tuple[int, list[str]]:
    """Score an experience or project against the JD. Returns (score, matched_skills)."""
    score = 0
    matched: list[str] = []

    # Must-have skills: +3 each
    for skill in jd.must_have_skills:
        if _normalize(skill) in blob:
            score += 3
            matched.append(skill)

    # Nice-to-have skills: +1 each
    for skill in jd.nice_to_have_skills:
        if _normalize(skill) in blob:
            score += 1
            matched.append(skill)

    # Responsibility keywords: +1 each
    for resp in jd.responsibilities:
        for word in _normalize(resp).split():
            if len(word) > 3 and word in blob:
                score += 1
                break  # only count once per responsibility

    # Keywords: +1 each
    for kw in jd.keywords:
        if _normalize(kw) in blob:
            score += 1

    # Per-bullet bonuses
    for bullet in bullets:
        lower = _normalize(bullet)
        # Metric bonus
        if _METRIC_RE.search(bullet):
            score += 1
        # Ownership verb bonus
        first_word = lower.split()[0] if lower.split() else ""
        if first_word in _OWNERSHIP_VERBS:
            score += 1

    return score, matched


def select_content(jd_profile: JDProfile, master_cv: MasterCV) -> SelectionPlan:
    """Score all experiences & projects and return the best selection."""

    # ── Score experiences ─────────────────────────────────────
    exp_scores: list[tuple[int, list[str], Experience]] = []
    for exp in master_cv.experience:
        blob = _text_blob(exp.bullets, exp.technologies)
        score, matched = _score_item(blob, exp.bullets, jd_profile)
        exp_scores.append((score, matched, exp))
    exp_scores.sort(key=lambda x: x[0], reverse=True)

    # ── Score projects ────────────────────────────────────────
    proj_scores: list[tuple[int, list[str], Project]] = []
    for proj in master_cv.projects:
        blob = _text_blob(proj.bullets, proj.technologies)
        score, matched = _score_item(blob, proj.bullets, jd_profile)
        proj_scores.append((score, matched, proj))
    proj_scores.sort(key=lambda x: x[0], reverse=True)

    # ── Pick top items ────────────────────────────────────────
    top_exp = exp_scores[:2]  # top 1–2 experiences
    top_proj = proj_scores[:3]  # top 2–3 projects

    # ── Collect matched / missing skills ──────────────────────
    all_matched: set[str] = set()
    for _, matched, _ in top_exp + top_proj:
        all_matched.update(matched)

    all_required = set(jd_profile.must_have_skills + jd_profile.nice_to_have_skills)
    missing = all_required - all_matched

    # ── Re-order skills: must-have first ──────────────────────
    must_set = {_normalize(s) for s in jd_profile.must_have_skills}
    nice_set = {_normalize(s) for s in jd_profile.nice_to_have_skills}

    skills_must = [s for s in master_cv.skills if _normalize(s) in must_set]
    skills_nice = [s for s in master_cv.skills if _normalize(s) in nice_set]
    skills_rest = [
        s for s in master_cv.skills
        if _normalize(s) not in must_set and _normalize(s) not in nice_set
    ]
    skills_ordered = skills_must + skills_nice + skills_rest

    return SelectionPlan(
        selected_experience_ids=[exp.id for _, _, exp in top_exp],
        selected_project_ids=[proj.id for _, _, proj in top_proj],
        skills_ordered=skills_ordered,
        reasoning=SelectionReasoning(
            matched_skills=sorted(all_matched),
            missing_skills=sorted(missing),
        ),
    )
