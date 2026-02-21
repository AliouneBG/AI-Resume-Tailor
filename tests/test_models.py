"""Tests for Pydantic data contracts."""

import json
from pathlib import Path

import pytest

from src.models import (
    EvidenceItem,
    JDProfile,
    MasterCV,
    MatchReport,
    SelectionPlan,
    SelectionReasoning,
)


# ── MasterCV ──────────────────────────────────────────────────

def test_master_cv_loads_from_json():
    """The sample master_cv.json should parse into a valid MasterCV."""
    cv_path = Path(__file__).resolve().parent.parent / "data" / "master_cv.json"
    with open(cv_path) as f:
        data = json.load(f)
    cv = MasterCV(**data)
    assert cv.name
    assert len(cv.skills) > 0
    assert len(cv.experience) > 0
    assert len(cv.projects) > 0
    assert len(cv.education) > 0


def test_master_cv_roundtrip():
    """MasterCV should serialize and deserialize identically."""
    cv_path = Path(__file__).resolve().parent.parent / "data" / "master_cv.json"
    with open(cv_path) as f:
        data = json.load(f)
    cv = MasterCV(**data)
    roundtrip = MasterCV(**json.loads(cv.model_dump_json()))
    assert cv == roundtrip


# ── JDProfile ─────────────────────────────────────────────────

def test_jd_profile_creation():
    profile = JDProfile(
        target_title="Software Engineer",
        must_have_skills=["Python", "AWS"],
        nice_to_have_skills=["Kafka"],
        responsibilities=["Build microservices"],
        keywords=["Docker", "Kubernetes"],
    )
    assert profile.target_title == "Software Engineer"
    assert len(profile.must_have_skills) == 2


# ── SelectionPlan ─────────────────────────────────────────────

def test_selection_plan_creation():
    plan = SelectionPlan(
        selected_experience_ids=["exp-1"],
        selected_project_ids=["proj-1", "proj-2"],
        skills_ordered=["Python", "AWS", "Docker"],
        reasoning=SelectionReasoning(
            matched_skills=["Python", "AWS"],
            missing_skills=["Go"],
        ),
    )
    assert len(plan.selected_experience_ids) == 1
    assert "Go" in plan.reasoning.missing_skills


# ── MatchReport ───────────────────────────────────────────────

def test_match_report_creation():
    report = MatchReport(
        keyword_coverage=0.85,
        matched_keywords=["Python", "AWS"],
        missing_keywords=["Go"],
        evidence_map=[
            EvidenceItem(jd_item="Python experience", evidence="Built services with Python"),
        ],
        risk_flags=[],
        score=78.0,
        fixes=["Add more cloud keywords"],
    )
    assert report.keyword_coverage == 0.85
    assert report.score == 78.0


def test_match_report_validates_bounds():
    """keyword_coverage must be 0–1, score must be 0–100."""
    with pytest.raises(Exception):
        MatchReport(
            keyword_coverage=1.5,  # out of bounds
            matched_keywords=[],
            missing_keywords=[],
            evidence_map=[],
            risk_flags=[],
            score=50.0,
        )

    with pytest.raises(Exception):
        MatchReport(
            keyword_coverage=0.5,
            matched_keywords=[],
            missing_keywords=[],
            evidence_map=[],
            risk_flags=[],
            score=150.0,  # out of bounds
        )
