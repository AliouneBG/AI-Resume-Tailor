from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.database import Iteration, MemoryItem, Run, SessionLocal

logger = logging.getLogger(__name__)

def store_success(run_id: int, threshold: int = 80):
    """
    Extracts the best iteration from a successful run and stores it as a MemoryItem.
    """
    db = SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run or (run.final_score is not None and run.final_score < threshold):
            return

        # Find the iteration with the highest score
        best_iteration = db.query(Iteration).filter(Iteration.run_id == run_id).order_by(Iteration.score.desc()).first()
        if not best_iteration or best_iteration.score < threshold:
            return

        # Check if we already have a memory item for this JD to avoid duplicates
        existing = db.query(MemoryItem).filter(MemoryItem.jd_hash == run.job_application.jd_hash).first()
        if existing:
            if best_iteration.score > existing.best_score:
                existing.best_score = best_iteration.score
                existing.best_resume_markdown = best_iteration.resume_markdown
                existing.critic_summary = best_iteration.critic_feedback # Simplified for now
                db.commit()
            return

        # Create new memory item
        memory_item = MemoryItem(
            role_tag=run.job_application.title,
            jd_hash=run.job_application.jd_hash,
            best_resume_markdown=best_iteration.resume_markdown,
            best_score=best_iteration.score,
            critic_summary=best_iteration.critic_feedback
        )
        db.add(memory_item)
        db.commit()
        logger.info(f"Stored success patterns for Run ID {run_id} as MemoryItem.")
    except Exception as e:
        logger.error(f"Failed to store success for Run ID {run_id}: {e}")
        db.rollback()
    finally:
        db.close()

def retrieve_examples(role_tag: Optional[str] = None, jd_hash: Optional[str] = None, k: int = 3) -> list[str]:
    """
    Retrieves up to k summarized patterns from past successful runs.
    """
    db = SessionLocal()
    try:
        query = db.query(MemoryItem)
        
        # 1. Try exact jd_hash match first (same job description)
        if jd_hash:
            exact_matches = query.filter(MemoryItem.jd_hash == jd_hash).all()
            if exact_matches:
                return [m.critic_summary for m in exact_matches[:k]]

        # 2. Try role_tag matches
        if role_tag:
            role_matches = query.filter(MemoryItem.role_tag.ilike(f"%{role_tag}%")).order_by(MemoryItem.best_score.desc()).limit(k).all()
            if role_matches:
                return [m.critic_summary for m in role_matches]

        # 3. Fallback to recent top-scoring items
        fallbacks = query.order_by(MemoryItem.best_score.desc()).limit(k).all()
        return [m.critic_summary for m in fallbacks]

    except Exception as e:
        logger.error(f"Failed to retrieve memory examples: {e}")
        return []
    finally:
        db.close()
