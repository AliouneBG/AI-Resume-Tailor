from __future__ import annotations

import os
import sys
from pathlib import Path

# Fix relative imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pipeline import run_pipeline
from src.database import SessionLocal, Run, Iteration, MemoryItem, init_db

def test_persistence_and_memory():
    init_db()
    db = SessionLocal()
    
    # Clear memory for a fresh test
    db.query(MemoryItem).delete()
    db.query(Iteration).delete()
    db.query(Run).delete()
    db.commit()

    jd_text = """
    Software Engineer at Netflix. 
    Required skills: Java, Spring Boot, Microservices, AWS.
    Responsibility: Build scalable backend systems.
    """
    
    print("Running initial pipeline run...")
    result1 = run_pipeline(jd_text, max_iterations=1, pass_threshold=10) # Low threshold to ensure success/storage
    
    print(f"Run 1 Score: {result1.final_report.score if result1.final_report else 'N/A'}")
    
    # Check if run was persisted
    run = db.query(Run).first()
    if run:
        print(f"Run persisted with ID: {run.id}, status: {run.status}")
    else:
        print("Run NOT persisted!")

    # Check if memory was stored
    memory = db.query(MemoryItem).first()
    if memory:
        print(f"Memory stored for role: {memory.role_tag}")
    else:
        print("Memory NOT stored!")

    print("\nRunning second pipeline run with similar JD...")
    jd_text_2 = """
    Senior Software Engineer at Amazon.
    Required skills: Java, AWS, Microservices.
    """
    # This should trigger memory retrieval in the logs
    result2 = run_pipeline(jd_text_2, max_iterations=1, pass_threshold=10)
    
    db.close()

if __name__ == "__main__":
    test_persistence_and_memory()
