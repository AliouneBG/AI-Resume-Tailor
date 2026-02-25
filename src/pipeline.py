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

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.agents.critic import critique_resume
from src.agents.jd_extractor import extract_jd_profile
from src.agents.resume_writer import generate_resume, improve_resume
from src.config import MODEL_NAME, MASTER_CV_PATH
from src.matcher import select_content
from src.models import Iteration, MasterCV, PipelineResult, JDProfile, SelectionPlan
from src.database import Iteration as DBIteration, JobApplication, Run, SessionLocal, compute_jd_hash, init_db
from src.memory import retrieve_examples, store_success
from src.exceptions import ResumeTailorError, APIError, DatabaseError, JDValidationError, CVValidationError
import threading

# Global lock removed due to Streamlit thread management issues

logger = logging.getLogger(__name__)

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
    on_iteration: Callable[[Iteration | None, str | None], None] | None = None,
    use_dynamic_iteration: bool = True,
    use_pruned_context: bool = True,
    use_rubric_optimization: bool = True,
    demo_mode: bool = False,
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
    # ── Input Validation ──────────────────────────────────────
    if not jd_text or not jd_text.strip():
        raise JDValidationError("Job description text cannot be empty.")
    
    # ── Initialize Database ───────────────────────────────────
    init_db()
    db = SessionLocal()
    run_id = None
    iterations: list[Iteration] = []
    jd_profile = None
    selection_plan = None

    jd_hash = compute_jd_hash(jd_text)
    cache_path = Path("data/demo_cache.json")

    # ── Demo Mode: Instant Replay ─────────────────────────────
    if demo_mode:
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text())
                if jd_hash in cache:
                    if on_iteration: on_iteration(None, "Demo Mode: Loading results from memory...")
                    return PipelineResult.model_validate_json(cache[jd_hash])
            except Exception as e:
                logger.warning(f"Demo cache load failed: {e}")

    lock_acquired = False
    try:
        # ── Load CV ───────────────────────────────────────────────
        try:
            if master_cv is None:
                master_cv = load_master_cv(cv_path)
        except Exception as e:
            raise CVValidationError(f"Failed to load Master CV from {cv_path}: {e}")

        # ── Global Request Gate (Removed) ───────────────────────────
        lock_acquired = True
        
        try:
            # ── Step 1: Extract JD Profile (with caching) ─────────────
            cache_dir = Path("data/cache/jd")
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / f"{jd_hash}.json"

            if cache_file.exists():
                if on_iteration: on_iteration(None, "Using cached JD profile...")
                jd_profile = JDProfile.model_validate_json(cache_file.read_text())
            else:
                if on_iteration: on_iteration(None, "Extracting structured JD profile...")
                jd_profile = extract_jd_profile(jd_text)
                cache_file.write_text(jd_profile.model_dump_json(indent=2))
        except Exception as e:
            raise e

        # ── Persistence: JobApplication & Run ─────────────────────
        job_app = db.query(JobApplication).filter(JobApplication.jd_hash == jd_hash).first()
        if not job_app:
            job_app = JobApplication(
                company="Unknown",  # To be updated if extracted
                title=jd_profile.target_title,
                jd_text=jd_text,
                jd_hash=jd_hash
            )
            db.add(job_app)
            db.flush()

        run = Run(
            job_application_id=job_app.id,
            target_score=int(pass_threshold),
            status="RUNNING",
            model_name=MODEL_NAME
        )
        db.add(run)
        db.commit()
        run_id = run.id

        # ── Step 2: Match & Select ────────────────────────────────
        if on_iteration: on_iteration(None, "Matching experiences and projects...")
        selection_plan = select_content(jd_profile, master_cv)

        # ── Step 2.5: Retrieve Memory Examples ────────────────────
        memory_examples = retrieve_examples(role_tag=jd_profile.target_title, jd_hash=jd_hash)

        # Write output files from Backbone (Step 1-2)
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        (out_dir / "jd_profile.json").write_text(jd_profile.model_dump_json(indent=2))
        (out_dir / "selection_plan.json").write_text(selection_plan.model_dump_json(indent=2))

        # ── Step 3: Self-Improvement Loop ─────────────────────────
        current_resume: str | None = None
        prev_score: float = 0.0

        for i in range(1, max_iterations + 1):
            # Generate or improve
            if i == 1:
                # First pass: generate from scratch + inject memory
                if on_iteration: on_iteration(None, f"Iteration {i}: Generating initial draft...")
                current_resume = generate_resume(
                    jd_profile, 
                    selection_plan, 
                    master_cv, 
                    memory_examples=memory_examples,
                    use_pruned_context=use_pruned_context,
                    use_rubric_optimization=use_rubric_optimization
                )
            else:
                # Subsequent passes: improve based on critic feedback
                if on_iteration: on_iteration(None, f"Iteration {i}: Refining based on critic feedback...")
                prev_report = iterations[-1].match_report
                current_resume = improve_resume(
                    jd_profile,
                    master_cv,
                    current_resume,  # type: ignore[arg-type]
                    prev_report.model_dump_json(indent=2),
                    use_rubric_optimization=use_rubric_optimization
                )

            # Critique the current version
            if on_iteration: on_iteration(None, f"Iteration {i}: Performing quality audit...")
            report = critique_resume(jd_profile, master_cv, current_resume, iteration=i)

            # Check if this version passes
            passed = report.score >= pass_threshold

            # Record iteration (Pydantic model)
            iteration = Iteration(
                version=i,
                resume_md=current_resume,
                match_report=report,
                passed=passed,
            )
            iterations.append(iteration)

            # Persistence: Save iteration (DB)
            db_iteration = DBIteration(
                run_id=run_id,
                iteration_number=i,
                score=int(report.score),
                critic_feedback=report.model_dump_json(indent=2),
                resume_markdown=current_resume
            )
            db.add(db_iteration)
            db.commit()

            # Fire callback if provided
            if on_iteration:
                try:
                    on_iteration(iteration, f"Iteration {i} complete (Score: {report.score})")
                except Exception as e:
                    logger.warning(f"on_iteration callback failed: {e}")

            # ── Exit conditions ───────────────────────────────────
            if passed:
                break

            # DYNAMIC ITERATION POLICY:
            # - Default max is 2 iterations.
            # - Auto-extend up to 'max_iterations' ONLY IF score improved significantly and still below threshold.
            if use_dynamic_iteration and i >= 2:
                improvement = report.score - prev_score
                # If we aren't improving enough, or if we hit an arbitrary max safety cap (e.g. 4)
                if improvement < min_improvement or i >= 4:
                    break
                # Otherwise, if we improved by at least 3 points and still below 80, we keep going up to max_iterations
                if i < max_iterations:
                     logger.info(f"Iteration {i} improved by {improvement:.1f} pts. Extending run.")
                else:
                    break

            prev_score = report.score

        # ── Finalize Run ──────────────────────────────────────────
        run = db.query(Run).filter(Run.id == run_id).first()
        run.final_score = int(iterations[-1].match_report.score)
        run.status = "SUCCESS"
        run.finished_at = datetime.utcnow()
        db.commit()

        # ── Store Memory if Successful ──────────────────────────
        if run.final_score >= pass_threshold:
            store_success(run_id, threshold=int(pass_threshold))

    except ResumeTailorError as e:
        logger.error(f"Pipeline domain error: {e}")
        if run_id:
            db_run = db.query(Run).filter(Run.id == run_id).first()
            if db_run:
                db_run.status = f"FAILED_{type(e).__name__.upper()}"
                db.commit()
        raise
    except Exception as e:
        logger.exception(f"Pipeline unexpected error: {e}")
        if run_id:
            db_run = db.query(Run).filter(Run.id == run_id).first()
            if db_run:
                db_run.status = "FAILED_UNKNOWN"
                db.commit()
        raise RuntimeError(f"Pipeline failed (Iterations completed: {len(iterations)}): {e}") from e
    finally:
        db.close()

    result = PipelineResult(
        jd_profile=jd_profile,
        selection_plan=selection_plan,
        iterations=iterations,
    )

    # ── Demo Mode: Save to Cache ──────────────────────────────
    if iterations and iterations[-1].match_report.score >= pass_threshold:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache = {}
            if cache_path.exists():
                cache = json.loads(cache_path.read_text())
            cache[jd_hash] = result.model_dump_json()
            cache_path.write_text(json.dumps(cache, indent=2))
        except Exception as e:
            logger.warning(f"Demo cache save failed: {e}")

    return result
