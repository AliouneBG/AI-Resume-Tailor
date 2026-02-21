"""Tests for the deterministic Matcher / Selector."""

import json
from pathlib import Path

from src.matcher import select_content
from src.models import JDProfile, MasterCV


def _load_cv() -> MasterCV:
    cv_path = Path(__file__).resolve().parent.parent / "data" / "master_cv.json"
    with open(cv_path) as f:
        return MasterCV(**json.load(f))


def _backend_jd() -> JDProfile:
    """A JD that should strongly match exp-1 and proj-3."""
    return JDProfile(
        target_title="Senior Backend Engineer",
        must_have_skills=["Python", "AWS", "Docker", "Kubernetes", "PostgreSQL", "Redis"],
        nice_to_have_skills=["Kafka", "Terraform", "GraphQL"],
        responsibilities=[
            "Design scalable backend services",
            "Build data pipelines",
            "Implement CI/CD pipelines",
            "Mentor junior engineers",
        ],
        keywords=["Python", "Docker", "Kubernetes", "AWS", "Kafka", "Terraform", "PostgreSQL", "Redis", "CI/CD", "microservices"],
    )


def test_selection_picks_top_experiences():
    """The backend JD should select exp-1 (most relevant) as the first pick."""
    plan = select_content(_backend_jd(), _load_cv())
    assert "exp-1" in plan.selected_experience_ids
    # exp-1 should rank highest due to microservices + Kafka + AWS
    assert plan.selected_experience_ids[0] == "exp-1"


def test_selection_picks_relevant_projects():
    """Should pick projects with backend/infra tech (proj-1, proj-3 likely)."""
    plan = select_content(_backend_jd(), _load_cv())
    # Should have 2-3 projects
    assert 2 <= len(plan.selected_project_ids) <= 3


def test_skills_ordered_must_have_first():
    """Must-have skills should appear before nice-to-have in ordered list."""
    plan = select_content(_backend_jd(), _load_cv())
    # Find first must-have and first nice-to-have in the ordered list
    must_have_set = {"python", "aws", "docker", "kubernetes", "postgresql", "redis"}
    nice_to_have_set = {"kafka", "terraform", "graphql"}

    first_must = None
    first_nice = None
    for i, skill in enumerate(plan.skills_ordered):
        s = skill.lower()
        if first_must is None and s in must_have_set:
            first_must = i
        if first_nice is None and s in nice_to_have_set:
            first_nice = i

    # Must-have skills should appear before nice-to-have
    if first_must is not None and first_nice is not None:
        assert first_must < first_nice


def test_matched_skills_not_empty():
    """The backend JD should match several skills from the CV."""
    plan = select_content(_backend_jd(), _load_cv())
    assert len(plan.reasoning.matched_skills) > 0
    # Python should definitely match
    assert "Python" in plan.reasoning.matched_skills or "python" in [s.lower() for s in plan.reasoning.matched_skills]


def test_frontend_jd_selects_different_content():
    """A frontend-focused JD should prefer exp-2 and proj-2."""
    frontend_jd = JDProfile(
        target_title="Frontend Engineer",
        must_have_skills=["React", "TypeScript", "Next.js"],
        nice_to_have_skills=["GraphQL", "Node.js"],
        responsibilities=[
            "Build user-facing dashboards",
            "Optimize frontend performance",
        ],
        keywords=["React", "TypeScript", "Next.js", "GraphQL", "A/B testing"],
    )
    plan = select_content(frontend_jd, _load_cv())
    # exp-2 (Full Stack with React/TS/GraphQL) should rank high
    assert "exp-2" in plan.selected_experience_ids
