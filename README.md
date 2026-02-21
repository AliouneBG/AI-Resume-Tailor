# 🎯 Resume Tailor — Self-Improving Agent

A hackathon project that takes a raw **Job Description** and your **Master CV**, then produces a **tailored resume** through a self-improving agent pipeline.

## Architecture

```
JD text ──→ JD Extractor ──→ JDProfile (structured)
                                │
Master CV + JDProfile ──→ Matcher ──→ SelectionPlan
                                        │
JDProfile + Selection + CV ──→ Writer ──→ Resume v1
                                            │
JDProfile + CV + Resume v1 ──→ Critic ──→ MatchReport
                                            │
MatchReport + Resume v1 ──→ Writer ──→ Resume v2 (improved)
```

| Component | Type | Description |
|-----------|------|-------------|
| **JD Extractor** | LLM Agent | Parses raw JD into structured requirements |
| **Matcher** | Deterministic | Scores & selects best CV content (no LLM) |
| **Resume Writer** | LLM Agent | Generates tailored Markdown resume |
| **Critic** | LLM Agent | Audits for hallucinations, keyword coverage |
| **Improver** | LLM Agent | Rewrites resume based on critic feedback |

## Quick Start

### 1. Install dependencies

```bash
cd resume-tailor-agent
pip3 install -r requirements.txt
```

### 2. Configure your LLM

```bash
cp .env.example .env
# Edit .env with your API key and model choice
```

**Supported providers:**
- **OpenAI**: Set `OPENAI_API_KEY` (default `gpt-4o-mini`)
- **Ollama**: Set `OPENAI_BASE_URL=http://localhost:11434/v1` and `MODEL_NAME=llama3`
- **Groq**: Set `OPENAI_BASE_URL=https://api.groq.com/openai/v1` and your Groq key

### 3. Edit your Master CV

Update `data/master_cv.json` with your real experience, projects, and skills.

### 4. Run the pipeline

```bash
# Use the sample JD
python3 cli.py tailor --jd data/sample_jd.txt

# Or paste JD inline
python3 cli.py tailor --jd "We are looking for a Python engineer..."

# Save the final resume
python3 cli.py tailor --jd data/sample_jd.txt --output resume_output.md
```

## Run Tests

```bash
pytest tests/ -v
```

## Project Structure

```
resume-tailor-agent/
├── cli.py                    # Typer CLI entry point
├── requirements.txt
├── .env.example
├── data/
│   ├── master_cv.json        # Your master CV
│   └── sample_jd.txt         # Sample JD for testing
├── src/
│   ├── config.py             # Env vars, LLM client
│   ├── models.py             # Pydantic data contracts
│   ├── matcher.py            # Deterministic scorer
│   ├── pipeline.py           # Orchestrator
│   ├── agents/
│   │   ├── jd_extractor.py   # JD → JDProfile
│   │   ├── resume_writer.py  # Generate + improve resume
│   │   └── critic.py         # Audit + score
│   └── templates/
│       └── resume.md.j2      # Markdown template
└── tests/
    ├── test_models.py
    └── test_matcher.py
```

## Data Contracts

All components communicate via typed Pydantic models defined in `src/models.py`:

- **`JDProfile`** — structured job requirements
- **`SelectionPlan`** — which CV content to use and why
- **`MatchReport`** — coverage score, missing keywords, hallucination flags
- **`PipelineResult`** — all intermediate artifacts bundled together
