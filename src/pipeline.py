"""Pipeline orchestrator — self-improving feedback loop.

Architecture:
  JD text → JD Extractor → JDProfile
                              ↓
  MasterCV + JDProfile → Matcher → SelectionPlan
                                      ↓
                          ┌─────────────────────────┐
                          │   SELF-IMPROVEMENT LOOP  │
                          │                         │
                          │  Writer → Resume vN     │
                          │     ↓                   │
                          │  Critic → MatchReport   │
                          │     ↓                   │
                          │  Score ≥ threshold? ────→ EXIT (pass)
                          │     ↓ no                │
                          │  Max iterations? ───────→ EXIT (best)
                          │     ↓ no                │
                          │  Writer (improve) ──┐   │
                          │     ↑               │   │
                          │     └───────────────┘   │
                          └─────────────────────────┘

The loop runs until:
  1. The critic's score meets the threshold (default: 80/100) → success
  2. Max iterations reached (default: 3) → returns best version
  3. Score stopped improving (convergence) → returns current version
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.agents.critic import critique_resume
from src.agents.jd_extractor import extract_jd_profile
from src.agents.resume_writer import generate_resume, improve_resume
from src.config import MASTER_CV_PATH
from src.matcher import select_content
from src.models import Iteration, MasterCV, PipelineResult


# ── Default thresholds ────────────────────────────────────────
DEFAULT_PASS_THRESHOLD = 80.0   # score out of 100 to consider "good enough"
DEFAULT_MAX_ITERATIONS = 3      # max Writer→Critic cycles
DEFAULT_MIN_IMPROVEMENT = 2.0   # stop if score improves less than this between iterations


def load_master_cv(path: Path | None = None) -> MasterCV:
    """Load the master CV from a JSON file."""
    cv_path = path or MASTER_CV_PATH
    with open(cv_path) as f:
        return MasterCV(**json.load(f))


def run_pipeline(
    jd_text: str,
    master_cv: MasterCV | None = None,
    cv_path: Path | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
    on_iteration: Callable[[Iteration], None] | None = None,
) -> PipelineResult:
    """Run the full tailor pipeline with self-improvement feedback loop.

    Args:
        jd_text: Raw job description text.
        master_cv: Pre-loaded MasterCV (takes priority over cv_path).
        cv_path: Path to master_cv.json (used if master_cv is None).
        max_iterations: Maximum Writer→Critic cycles (default: 3).
        pass_threshold: Score threshold to stop iterating (default: 80).
        min_improvement: Stop if score improves less than this (default: 2.0).
        on_iteration: Optional callback fired after each iteration (for live UI updates).

    Returns:
        PipelineResult with all iteration history.
    """
    # ── Load CV ───────────────────────────────────────────────
    if master_cv is None:
        master_cv = load_master_cv(cv_path)

    # ── Step 1: Extract JD Profile ────────────────────────────
    jd_profile = extract_jd_profile(jd_text)

    # ── Step 2: Match & Select ────────────────────────────────
    selection_plan = select_content(jd_profile, master_cv)

    # Write output files from Backbone (Step 1-2)
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "jd_profile.json").write_text(jd_profile.model_dump_json(indent=2))
    (out_dir / "selection_plan.json").write_text(selection_plan.model_dump_json(indent=2))

    # ── Step 3: Self-Improvement Loop ─────────────────────────
    iterations: list[Iteration] = []
    current_resume: str | None = None
    prev_score: float = 0.0

    try:
        for i in range(1, max_iterations + 1):
            # Generate or improve
            if i == 1:
                # First pass: generate from scratch
                current_resume = generate_resume(jd_profile, selection_plan, master_cv)
            else:
                # Subsequent passes: improve based on critic feedback
                prev_report = iterations[-1].match_report
                current_resume = improve_resume(
                    jd_profile,
                    master_cv,
                    current_resume,  # type: ignore[arg-type]
                    prev_report.model_dump_json(indent=2),
                )

            # Critique the current version
            report = critique_resume(jd_profile, master_cv, current_resume, iteration=i)

            # Check if this version passes
            passed = report.score >= pass_threshold

            # Record iteration
            iteration = Iteration(
                version=i,
                resume_md=current_resume,
                match_report=report,
                passed=passed,
            )
            iterations.append(iteration)

            # Fire callback if provided (for live CLI/UI updates)
            if on_iteration:
                on_iteration(iteration)

            # ── Exit conditions ───────────────────────────────────
            if passed:
                # Score meets threshold — we're done!
                break

            if i > 1:
                improvement = report.score - prev_score
                if improvement < min_improvement:
                    # Score converged — further iterations won't help much
                    break

            prev_score = report.score
    except Exception as e:
        raise RuntimeError(f"Pipeline failed on iteration {len(iterations) + 1}: {e}") from e

    return PipelineResult(
        jd_profile=jd_profile,
        selection_plan=selection_plan,
        iterations=iterations,
    )
