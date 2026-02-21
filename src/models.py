"""Data contracts for the Resume Tailor pipeline.

Every component communicates through these Pydantic models,
ensuring type safety and easy JSON (de)serialization.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Master CV ─────────────────────────────────────────────────

class Experience(BaseModel):
    id: str
    role: str
    company: str
    start_date: str
    end_date: str
    bullets: list[str]
    technologies: list[str]


class Project(BaseModel):
    id: str
    name: str
    bullets: list[str]
    technologies: list[str]
    url: str = ""


class Education(BaseModel):
    degree: str
    institution: str
    graduation_date: str
    gpa: str = ""
    relevant_courses: list[str] = Field(default_factory=list)


class MasterCV(BaseModel):
    name: str
    email: str
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    summary: str = ""
    skills: list[str]
    experience: list[Experience]
    projects: list[Project]
    education: list[Education]


# ── JD Profile ────────────────────────────────────────────────

class JDProfile(BaseModel):
    target_title: str
    must_have_skills: list[str]
    nice_to_have_skills: list[str]
    responsibilities: list[str]
    keywords: list[str]
    seniority: str = ""


# ── Selection Plan ────────────────────────────────────────────

class SelectionReasoning(BaseModel):
    matched_skills: list[str]
    missing_skills: list[str]


class SelectionPlan(BaseModel):
    selected_experience_ids: list[str]
    selected_project_ids: list[str]
    skills_ordered: list[str]
    reasoning: SelectionReasoning


# ── Match Report ──────────────────────────────────────────────

class EvidenceItem(BaseModel):
    jd_item: str
    evidence: str


class MatchReport(BaseModel):
    keyword_coverage: float = Field(
        ge=0.0, le=1.0,
        description="Fraction of JD keywords found in the resume (0–1).",
    )
    matched_keywords: list[str]
    missing_keywords: list[str]
    evidence_map: list[EvidenceItem]
    risk_flags: list[str]
    score: float = Field(
        ge=0.0, le=100.0,
        description="Overall resume quality score (0–100).",
    )
    fixes: list[str] = Field(default_factory=list)


# ── Pipeline Result (everything together) ─────────────────────

class PipelineResult(BaseModel):
    jd_profile: JDProfile
    selection_plan: SelectionPlan
    resume_v1: str
    match_report_v1: MatchReport
    resume_v2: str
    match_report_v2: MatchReport | None = None
