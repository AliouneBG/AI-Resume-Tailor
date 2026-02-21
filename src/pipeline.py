"""Pipeline orchestrator — wires all components into a single flow.

JD text → JD Extractor → JDProfile
                            ↓
MasterCV + JDProfile → Matcher → SelectionPlan
                                    ↓
JDProfile + SelectionPlan + MasterCV → Writer → Resume v1
                                                   ↓
JDProfile + MasterCV + Resume v1 → Critic → MatchReport v1
                                                ↓
MatchReport v1 + Resume v1 → Writer (improve) → Resume v2
                                                    ↓
JDProfile + MasterCV + Resume v2 → Critic → MatchReport v2
"""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.critic import critique_resume
from src.agents.jd_extractor import extract_jd_profile
from src.agents.resume_writer import generate_resume, improve_resume
from src.config import MASTER_CV_PATH
from src.matcher import select_content
from src.models import MasterCV, PipelineResult


def load_master_cv(path: Path | None = None) -> MasterCV:
    """Load the master CV from a JSON file."""
    cv_path = path or MASTER_CV_PATH
    with open(cv_path) as f:
        return MasterCV(**json.load(f))


def run_pipeline(
    jd_text: str,
    master_cv: MasterCV | None = None,
    cv_path: Path | None = None,
) -> PipelineResult:
    """Run the full tailor pipeline: Extract → Match → Write → Critique → Improve.

    Args:
        jd_text: Raw job description text.
        master_cv: Pre-loaded MasterCV (takes priority over cv_path).
        cv_path: Path to master_cv.json (used if master_cv is None).

    Returns:
        PipelineResult with all intermediate artifacts.
    """
    # ── Load CV ───────────────────────────────────────────────
    if master_cv is None:
        master_cv = load_master_cv(cv_path)

    # ── Step 1: Extract JD Profile ────────────────────────────
    jd_profile = extract_jd_profile(jd_text)

    # ── Step 2: Match & Select ────────────────────────────────
    selection_plan = select_content(jd_profile, master_cv)

    # ── Step 3: Generate Resume v1 ────────────────────────────
    resume_v1 = generate_resume(jd_profile, selection_plan, master_cv)

    # ── Step 4: Critique Resume v1 ────────────────────────────
    match_report_v1 = critique_resume(jd_profile, master_cv, resume_v1)

    # ── Step 5: Improve → Resume v2 ──────────────────────────
    resume_v2 = improve_resume(
        jd_profile,
        master_cv,
        resume_v1,
        match_report_v1.model_dump_json(indent=2),
    )

    # ── Step 6: Critique Resume v2 (optional verification) ───
    match_report_v2 = critique_resume(jd_profile, master_cv, resume_v2)

    return PipelineResult(
        jd_profile=jd_profile,
        selection_plan=selection_plan,
        resume_v1=resume_v1,
        match_report_v1=match_report_v1,
        resume_v2=resume_v2,
        match_report_v2=match_report_v2,
    )
