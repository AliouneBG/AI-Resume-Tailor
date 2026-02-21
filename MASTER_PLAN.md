# 🎯 Master Plan — Job Resume Tailor (Self-Improving Agent)

## The Big Idea

**Problem:** Tailoring a resume for every job application is tedious, error-prone, and time-consuming.

**Solution:** An AI agent pipeline that reads a raw Job Description, selects the most relevant content from your Master CV, generates a tailored resume, then *critiques and improves itself* — producing a better v2 automatically.

**The "self-improving" hook:** `Writer v1 → Critic → Writer v2`. This is our core differentiator.

---

## How It Works (5-Step Pipeline)

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   1. JD EXTRACTOR (LLM)                                            │
│      Raw job description → structured requirements (JDProfile)      │
│                                                                     │
│   2. MATCHER / SELECTOR (deterministic — NO LLM)                   │
│      JDProfile + Master CV → score & rank content → SelectionPlan   │
│      • +3 pts per must-have skill matched                          │
│      • +1 pt per nice-to-have, keyword, metric, ownership verb     │
│                                                                     │
│   3. RESUME WRITER (LLM)                                           │
│      JDProfile + SelectionPlan + Master CV → tailored resume v1     │
│      • Cannot invent tech or metrics not in Master CV              │
│                                                                     │
│   4. CRITIC (LLM)                                                  │
│      Resume v1 + JDProfile + Master CV → MatchReport               │
│      • Keyword coverage %, hallucination flags, missing skills     │
│                                                                     │
│   5. IMPROVER (LLM)                                                │
│      Resume v1 + Critic feedback → Resume v2 (improved)            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Contracts (shared language across all modules)

| Contract | What it holds |
|----------|--------------|
| `MasterCV` | Your full career inventory — skills, experiences, projects, education |
| `JDProfile` | Parsed JD — must-have skills, nice-to-haves, responsibilities, keywords |
| `SelectionPlan` | Which experiences/projects to use, skills ordering, reasoning |
| `MatchReport` | Coverage score, matched/missing keywords, hallucination flags, fixes |

All defined in `src/models.py` using Pydantic (typed, validated, JSON-serializable).

---

## Repo Structure

```
Hack/
├── cli.py                    ← Entry point — run the whole pipeline
├── src/
│   ├── config.py             ← API keys, model settings (.env)
│   ├── models.py             ← Data contracts (Pydantic)
│   ├── matcher.py            ← Deterministic scorer (no LLM)
│   ├── pipeline.py           ← Orchestrator (wires everything)
│   └── agents/
│       ├── jd_extractor.py   ← Step 1: JD → JDProfile
│       ├── resume_writer.py  ← Steps 3 & 5: generate + improve
│       └── critic.py         ← Step 4: audit + score
├── data/
│   ├── master_cv.json        ← YOUR CV (edit this!)
│   └── sample_jd.txt         ← Test JD
└── tests/                    ← Unit tests for matcher + models
```

---

## Branching Guide

| Branch | Owner | What to work on |
|--------|-------|-----------------|
| `main` | — | Stable, working pipeline |
| `feature/jd-extractor` | — | Improve JD parsing prompts, handle edge cases |
| `feature/matcher` | — | Tune scoring weights, add signals |
| `feature/writer` | — | Better resume prompts, formatting, templates |
| `feature/critic` | — | Stricter hallucination checks, better fixes |
| `feature/frontend` | — | Web UI (Streamlit / Flask) if time allows |

> **Fill in owner names above.** Each person owns one vertical slice.

---

## Setup (for everyone)

```bash
git clone <repo-url> && cd Hack
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ← add your API key here
```

## Run It

```bash
source .venv/bin/activate
python3 cli.py tailor --jd data/sample_jd.txt
```

## Run Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

---

## Demo Flow (what we show the judges)

1. **Paste a live JD** from LinkedIn / job board
2. **JDProfile JSON appears** — show structured extraction
3. **Selection reasoning** — "picked these 2 experiences because..."
4. **Resume v1** — first draft tailored to the JD
5. **Critic report** — coverage %, missing keywords, issues found
6. **Resume v2** — self-improved version with score bump
7. **Before/after score comparison** — the "self-improving" moment ✨

---

## Key Design Decisions

- **Google Gemini** (`google-genai` SDK) — uses `GEMINI_API_KEY` with `gemini-2.5-flash` by default
- **Deterministic Matcher** — no LLM, transparent scoring. Judges love explainability.
- **Anti-hallucination** — Writer + Critic both enforce "only use what's in Master CV"
- **Pydantic contracts** — every module speaks the same typed language, no ambiguity
