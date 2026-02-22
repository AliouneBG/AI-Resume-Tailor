# AI Resume Tailor

### *A persistent, self-improving AI agent that tailors resumes to job descriptions using an iterative critique loop and SQL-backed memory.*

AI Resume Tailor is a stateful orchestration system that transforms raw job descriptions and a structured Master CV into tailored resumes through deterministic matching, iterative LLM refinement, and persistent memory retrieval. It enforces strict zero-hallucination guardrails and maintains long-term alignment through pattern extraction.

---

## Why This Project Is Non-Trivial

- **Separation of Concerns**: Decouples deterministic relevance matching (Matcher) from generative LLM tasks (Writer) to maintain factual accuracy.
- **Iterative Refinement**: Implements an autonomous feedback loop that persists until the output meets a specific score threshold or reaches the iteration limit.
- **Auditability and Reproducibility**: Persists structured intermediate artifacts (JDProfile, SelectionPlan, MatchReport, Iterations) in SQL for full reproducibility and post-run inspection.
- **Stateful Memory**: Successful runs (≥ threshold score) are distilled into critic summaries and stored as MemoryItems, which are retrieved and injected into subsequent prompts to accelerate convergence and improve alignment.
- **Zero-Hallucination Constraints**: Enforces rigorous validation to ensure the LLM never invents experience outside the provided Master CV data.

---

## Key Features

- **Integrated Job Search**: Search and ingest live job postings via SerpAPI integration.
- **Multi-Agent Pipeline**: Dedicated agents for Job Description (JD) extraction, Resume writing, and Peer Review (Critic).
- **Management Dashboard**: Streamlit-based interface for run history, memory inspection, and real-time pipeline monitoring.
- **Persistent Record**: Full SQLite integration for tracking runs, scores, and historical performance.
- **Smart Iteration**: Automatically triggers re-writes based on specific Critic feedback regarding keyword density and tone.

---

## System Design & Resilience

The project is built with a focus on durability and architectural clarity:

- **Persistence Model**: SQLAlchemy-backed storage supporting full relational integrity for Runs, Iterations, and MemoryItems.
- **Run/Iteration Abstraction**: Tracks every execution at a granular level, including status, target/final scores, latency, and specific model metadata.
- **Resilience Layer**:
    - **Structured Domain Exceptions**: Custom hierarchy (APIError, DatabaseError, ValidationError) for precise error handling.
    - **Backoff Strategy**: Exponential retry logic for transient API failures using the tenacity library.
    - **Transaction Safety**: Context-managed database sessions ensuring atomicity and clean rollbacks.
- **Memory Retrieval Flow**: Cross-session pattern recognition that weights prior successful critic summaries to guide the current writing task.

---

## Testing & Verification

- **Unit Tests**: Full coverage for deterministic matching and scoring logic.
- **Failure Scenario Tests**: Tests covering API rate limits, validation errors, and database disconnects.
- **Explicit Verification Scripts**: Confirm persistence, state transitions, and memory retrieval behavior.

---

## Architecture

The system operates on an iterative feedback loop:

1.  **JD Extractor**: Parses raw job text into structured technical requirements and soft skills.
2.  **Matcher**: A deterministic component that filters Master CV content for relevance without LLM overhead.
3.  **Resume Writer**: Compiles a professional Markdown resume based on the structured selection.
4.  **Critic (Auditor)**: Evaluates the resume against the JD, flagging keyword gaps and potential inaccuracies.
5.  **Improver**: Refines the resume based on the Critic's specific feedback (up to 5 iterations).

---

## Installation & Setup

### 1. Requirements
- Python 3.9+
- [Google AI Studio API Key](https://aistudio.google.com/) (for Gemini)
- [SerpAPI Key](https://serpapi.com/) (optional, for job search)

### 2. Setup
```bash
# Clone and enter the repo
git clone https://github.com/AliouneBG/AI-Resume-Tailor.git
cd AI-Resume-Tailor

# Install core dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Update .env with your API keys
```

### 3. Source of Truth
Populate `data/master_cv.json` with your verified work history. This file is the absolute boundary for the AI's content generation.

---

## Operations

### Dashboard (Recommended)
```bash
streamlit run app.py
```

### CLI Entrypoint
```bash
python cli.py tailor --jd data/sample_jd.txt --output tailored_resume.md
```

---

## License
Distributed under the MIT License. See LICENSE for more information.

---
 
