from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

from contextlib import contextmanager

from src import config
from src.exceptions import DatabaseError

Base = declarative_base()

class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True)
    company = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    jd_text = Column(Text, nullable=False)
    jd_hash = Column(String(64), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("Run", back_populates="job_application")

class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True)
    job_application_id = Column(Integer, ForeignKey("job_applications.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    target_score = Column(Integer, default=80)
    final_score = Column(Integer)
    status = Column(String(50))  # RUNNING, SUCCESS, FAILED
    model_name = Column(String(255))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job_application = relationship("JobApplication", back_populates="runs")
    iterations = relationship("Iteration", back_populates="run")

class Iteration(Base):
    __tablename__ = "iterations"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    iteration_number = Column(Integer, nullable=False)
    score = Column(Integer)
    critic_feedback = Column(Text)
    resume_markdown = Column(Text)
    latency_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("Run", back_populates="iterations")

class MemoryItem(Base):
    __tablename__ = "memory_items"

    id = Column(Integer, primary_key=True)
    role_tag = Column(String(255), index=True)
    jd_hash = Column(String(64), index=True)
    best_resume_markdown = Column(Text)
    best_score = Column(Integer)
    critic_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# ── Database Setup ─────────────────────────────────────────────

# Default to SQLite if DATABASE_URL is not set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./resume_tailor.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

@contextmanager
def get_db():
    """Context manager for database sessions with automatic rollback and closing."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise DatabaseError(f"Database operation failed: {e}") from e
    finally:
        db.close()

def compute_jd_hash(text: str) -> str:
    """Compute SHA-256 hash of job description text."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
