"""Resume Tailor — Google ADK Multi-Agent Pipeline.

Architecture:
  SequentialAgent (root_agent)
    ├── JD Extractor Agent (LlmAgent) → state["jd_profile"]
    ├── Matcher Agent (LlmAgent + tool) → state["selection_plan"]
    ├── Initial Writer Agent (LlmAgent) → state["current_resume"]
    └── Refinement Loop (LoopAgent, max_iterations=3)
          ├── Critic Agent (LlmAgent) → state["criticism"]
          └── Refiner Agent (LlmAgent + exit_loop tool) → state["current_resume"]
"""

import json
import re
from pathlib import Path

from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.adk.tools.tool_context import ToolContext

# ── Constants ──────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.0-flash"

# ── State keys ─────────────────────────────────────────────────
STATE_JD_TEXT = "jd_text"
STATE_JD_PROFILE = "jd_profile"
STATE_MASTER_CV = "master_cv"
STATE_SELECTION_PLAN = "selection_plan"
STATE_CURRENT_RESUME = "current_resume"
STATE_CRITICISM = "criticism"

# ── Completion signal ──────────────────────────────────────────
COMPLETION_PHRASE = "RESUME_APPROVED"

# ── Data loading ───────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ══════════════════════════════════════════════════════════════
#  TOOL FUNCTIONS
# ══════════════════════════════════════════════════════════════

def load_master_cv(tool_context: ToolContext) -> dict:
    """Load the master CV from data/master_cv.json and store it in session state.

    Call this tool before generating a resume. It reads the candidate's
    complete career data from disk.
    """
    cv_path = DATA_DIR / "master_cv.json"
    if not cv_path.exists():
        return {"status": "error", "message": f"File not found: {cv_path}"}

    with open(cv_path) as f:
        cv_data = json.load(f)

    tool_context.state[STATE_MASTER_CV] = json.dumps(cv_data, indent=2)
    return {"status": "success", "message": f"Loaded CV for {cv_data.get('name', 'unknown')}"}


def run_matcher(tool_context: ToolContext) -> dict:
    """Run the deterministic matcher to select the best CV content for the JD.

    This tool scores experiences and projects against the JD profile using
    a weighted system (must-have skills +3, nice-to-have +1, keyword match +1,
    metric bonus +1, ownership verb bonus +1). It returns the selection plan.
    """
    jd_raw = tool_context.state.get(STATE_JD_PROFILE, "{}")
    cv_raw = tool_context.state.get(STATE_MASTER_CV, "{}")
    try:
        jd = json.loads(jd_raw)
        cv = json.loads(cv_raw)
    except json.JSONDecodeError:
        return {"status": "error", "message": "Could not parse JD profile or CV from state"}

    must_have = [s.lower().strip() for s in jd.get("must_have_skills", [])]
    nice_have = [s.lower().strip() for s in jd.get("nice_to_have_skills", [])]
    keywords = [k.lower().strip() for k in jd.get("keywords", [])]
    responsibilities = jd.get("responsibilities", [])

    metric_re = re.compile(r"\d[\d,]*\.?\d*\s*[%xX]?")
    ownership_verbs = {
        "built", "led", "deployed", "shipped", "designed", "architected",
        "implemented", "optimized", "reduced", "increased", "launched",
        "engineered", "developed", "managed", "delivered", "scaled",
        "automated", "migrated", "refactored", "created", "established",
    }

    def score_item(bullets, technologies):
        blob = " ".join(bullets + technologies).lower()
        score = 0
        matched = []
        for s in must_have:
            if s in blob:
                score += 3
                matched.append(s)
        for s in nice_have:
            if s in blob:
                score += 1
                matched.append(s)
        for resp in responsibilities:
            for w in resp.lower().split():
                if len(w) > 3 and w in blob:
                    score += 1
                    break
        for kw in keywords:
            if kw in blob:
                score += 1
        for b in bullets:
            if metric_re.search(b):
                score += 1
            first = b.lower().split()[0] if b.split() else ""
            if first in ownership_verbs:
                score += 1
        return score, matched

    # Score experiences
    exp_scores = []
    for exp in cv.get("experience", []):
        s, m = score_item(exp.get("bullets", []), exp.get("technologies", []))
        exp_scores.append((s, m, exp))
    exp_scores.sort(key=lambda x: x[0], reverse=True)

    # Score projects
    proj_scores = []
    for proj in cv.get("projects", []):
        s, m = score_item(proj.get("bullets", []), proj.get("technologies", []))
        proj_scores.append((s, m, proj))
    proj_scores.sort(key=lambda x: x[0], reverse=True)

    top_exp = exp_scores[:2]
    top_proj = proj_scores[:3]

    all_matched = set()
    for _, m, _ in top_exp + top_proj:
        all_matched.update(m)

    all_required = set(must_have + nice_have)
    missing = all_required - all_matched

    # Order skills: must-have first
    must_set = set(must_have)
    nice_set = set(nice_have)
    all_skills = cv.get("skills", [])
    skills_must = [s for s in all_skills if s.lower().strip() in must_set]
    skills_nice = [s for s in all_skills if s.lower().strip() in nice_set]
    skills_rest = [s for s in all_skills if s.lower().strip() not in must_set and s.lower().strip() not in nice_set]

    plan = {
        "selected_experience_ids": [e["id"] for _, _, e in top_exp],
        "selected_project_ids": [p["id"] for _, _, p in top_proj],
        "skills_ordered": skills_must + skills_nice + skills_rest,
        "reasoning": {
            "matched_skills": sorted(all_matched),
            "missing_skills": sorted(missing),
        },
    }

    tool_context.state[STATE_SELECTION_PLAN] = json.dumps(plan, indent=2)
    return {"status": "success", "plan": plan}


def exit_loop(tool_context: ToolContext) -> dict:
    """Call this function ONLY when the resume critique indicates the resume
    has passed quality checks (score >= 80) and no major issues remain.
    This ends the self-improvement loop."""
    tool_context.actions.escalate = True
    return {"status": "loop_exited", "message": "Resume approved — exiting refinement loop."}


# ══════════════════════════════════════════════════════════════
#  AGENT DEFINITIONS
# ══════════════════════════════════════════════════════════════

# ── Step 1: JD Extractor Agent ─────────────────────────────────
jd_extractor_agent = Agent(
    name="JDExtractorAgent",
    model=GEMINI_MODEL,
    include_contents="none",
    instruction="""You are a Job Description Analyst. Extract structured information
from the raw job description text provided below.

**Job Description:**
{{jd_text}}

Return VALID JSON matching this schema exactly:
{
  "target_title": "string — the job title",
  "must_have_skills": ["string — hard requirements explicitly stated"],
  "nice_to_have_skills": ["string — preferred / nice-to-have items"],
  "responsibilities": ["string — key responsibilities"],
  "keywords": ["string — tools, technologies, methodologies, frameworks mentioned"],
  "seniority": "string — junior / mid / senior / staff / unknown"
}

Rules:
- Only include skills/keywords actually stated in the JD.
- Separate must-have vs nice-to-have based on language ("required" vs "preferred", "bonus").
- Keep each item short — 2-6 words max.
- De-duplicate keywords and skills.
- If seniority is unclear, put "unknown".
- Return ONLY the JSON, no extra text.""",
    description="Parses a raw job description into a structured JD profile.",
    output_key=STATE_JD_PROFILE,
)

# ── Step 2: Matcher Agent (uses tool) ──────────────────────────
matcher_agent = Agent(
    name="MatcherAgent",
    model=GEMINI_MODEL,
    include_contents="none",
    instruction="""You are a Content Selection Agent. Your job is to:
1. First, call the `load_master_cv` tool to load the candidate's CV into state.
2. Then, call the `run_matcher` tool to score and select the best CV content for the job.

Call the tools in order. After both tools complete, output a brief summary of the selection
(which experiences and projects were selected, what skills matched).
Do NOT generate a resume — just run the tools.""",
    description="Loads the master CV and runs deterministic matching to select content.",
    tools=[load_master_cv, run_matcher],
)

# ── Step 3: Initial Writer Agent ───────────────────────────────
initial_writer_agent = Agent(
    name="InitialWriterAgent",
    model=GEMINI_MODEL,
    include_contents="none",
    instruction="""You are an elite Resume Writer who specializes in ATS-optimized, STAR-method resumes.

## HUMAN TONE (CRITICAL — READ THIS FIRST)
The resume MUST sound like a real human wrote it, NOT an AI. Follow these rules:
- **Vary sentence structure.** Mix short punchy bullets with slightly longer ones.
- **BANNED WORDS** — Never use these AI-giveaway words/phrases:
  "Leveraged", "Utilized", "Spearheaded", "Orchestrated", "Synergized",
  "Cutting-edge", "State-of-the-art", "Robust", "Seamless", "Holistic",
  "Streamlined" (overused), "Facilitated", "Harnessed", "Pivotal",
  "Dynamic", "Innovative solution", "Best-in-class", "Comprehensive"
- **USE THESE INSTEAD** — Write like an engineer talking to another engineer:
  "Built", "Set up", "Wrote", "Fixed", "Shipped", "Ran", "Cut",
  "Dropped", "Moved", "Pulled", "Pushed", "Reworked", "Rewrote",
  "Sped up", "Rolled out", "Stood up", "Wired up", "Plugged in"
- Be specific, not grand. Say "Built a Kafka consumer that processes 2M events/day"
  NOT "Engineered a robust, scalable event processing solution"
- Mix bullet lengths. Some bullets should be short (6–10 words).
- No adjective stacking. "Built 3 microservices" not "Expertly architected robust microservices"
- Summary: conversational-professional, like a LinkedIn About. No "passionate" or "results-driven."

## YOUR INPUTS (from session state)
**JD Profile:**
{{jd_profile}}

**Selection Plan:**
{{selection_plan}}

**Master CV (GROUND TRUTH — ONLY use content from here):**
{{master_cv}}

## STAR METHOD FOR BULLETS
Rewrite EVERY bullet using Situation/Task → Action → Result, compressed into 1–2 lines.
Examples:
❌ "Worked on microservices"
✅ "Built 3 microservices handling 50K+ RPM on AWS ECS, cutting API latency by 40%"

## ATS KEYWORD OPTIMIZATION
- Mirror JD's EXACT terminology. If JD says "CI/CD pipelines" and CV says "automated deployments" → write "CI/CD pipelines"
- Front-load must-have skills in Skills section.
- Use the SAME casing as the JD.

## ANTI-HALLUCINATION RULES (CRITICAL)
1. ONLY include technologies, tools, and frameworks present in the Master CV. NEVER invent.
2. ONLY use metrics/numbers from Master CV bullets. NEVER fabricate.
3. You may rephrase but NEVER change numbers.
4. You may COMBINE two related bullets into one stronger STAR bullet.
5. You may ADD action verbs but NOT context facts.

## QUANTIFICATION
- Preserve ALL numbers from Master CV.
- Add % improvements where both numbers exist.
- No number in CV → use qualitative impact, don't invent.

## OUTPUT FORMAT — Markdown resume with sections IN ORDER:
# [Full Name]
[Email] | [Phone] | [LinkedIn](URL) | [GitHub](URL)

## Summary
[2–3 sentence summary tailored to target role]

## Technical Skills
**Core:** [must-have skills, comma-separated]
**Additional:** [nice-to-have + remaining, comma-separated]

## Professional Experience
### [Role] — [Company]
*[Start] – [End]*
- [STAR bullet 1 — highest impact]
- [STAR bullet 2]
- [STAR bullet 3]

## Projects
### [Name] | [Technologies]
- [STAR bullet]

## Education
### [Degree] — [Institution] | *[Date]*

Include ONLY experiences/projects from the Selection Plan.
Cap at 4–5 bullets per experience, 2–3 per project.
Return ONLY the Markdown. No commentary.""",
    description="Generates the initial tailored resume (v1) using STAR method and ATS optimization.",
    output_key=STATE_CURRENT_RESUME,
)

# ── Step 4a: Critic Agent (inside loop) ────────────────────────
critic_agent = Agent(
    name="CriticAgent",
    model=GEMINI_MODEL,
    include_contents="none",
    instruction=f"""You are a ruthless Resume Critic and quality gate in a self-improving pipeline.
Your feedback directly drives the next rewrite, so be SPECIFIC and ACTIONABLE.

**Resume to Audit:**
{{{{current_resume}}}}

**JD Profile:**
{{{{jd_profile}}}}

**Master CV (ground truth):**
{{{{master_cv}}}}

## 6-POINT AUDIT

### 1. KEYWORD COVERAGE
Count JD keywords + must_have_skills found in resume.
coverage = matched / total

### 2. HALLUCINATION DETECTION
Compare EVERY technology, metric in resume vs Master CV.
Flag: "HALLUCINATION: [item] — not in Master CV"

### 3. STAR METHOD CHECK
Each bullet needs ACTION + RESULT. Flag vague bullets.

### 4. AI VOICE DETECTION
Flag: "Leveraged", "Utilized", "Spearheaded", "Orchestrated", "Robust",
"Seamless", "Cutting-edge", "Holistic", "Comprehensive", etc.
Format: "AI_VOICE: '[word]' — replace with plain language"

### 5. MUST-HAVE GAP ANALYSIS
For each must_have_skill — is it in the resume?
If missing but in Master CV → suggest adding it.
If missing and NOT in Master CV → note but don't request adding.

### 6. EVIDENCE MAPPING
For each JD responsibility, find the matching resume bullet.

## SCORING (0–100)
- Keyword coverage (30 pts): coverage × 30
- Zero hallucinations (25 pts): 25 if clean, -5 each
- STAR compliance (15 pts): 15 × (good bullets / total)
- Human voice (10 pts): 10 if no buzzwords, -2 each
- Must-have coverage (20 pts): 20 × (present / total)

## OUTPUT FORMAT
If score >= 80 AND zero hallucinations:
Respond with EXACTLY: "{COMPLETION_PHRASE}"

Otherwise, output your full critique with:
- Score: [number]/100
- Hallucinations found: [list]
- Missing keywords: [list]
- AI voice issues: [list]
- Specific fixes needed: [numbered list]

Be brutally honest. Every fix must be actionable.""",
    description="Audits the resume with a 6-point checklist, provides score and actionable fixes.",
    output_key=STATE_CRITICISM,
)

# ── Step 4b: Refiner Agent (inside loop) ───────────────────────
refiner_agent = Agent(
    name="RefinerAgent",
    model=GEMINI_MODEL,
    include_contents="none",
    instruction=f"""You are an elite Resume Editor. You either improve the resume or exit the loop.

**Current Resume:**
{{{{current_resume}}}}

**Critic's Feedback:**
{{{{criticism}}}}

**JD Profile:**
{{{{jd_profile}}}}

**Master CV (ground truth):**
{{{{master_cv}}}}

## DECISION
IF the criticism is exactly "{COMPLETION_PHRASE}":
  → You MUST call the `exit_loop` tool. Do not output any text.

ELSE:
  → Apply ALL fixes from the criticism. Follow these priorities:
  1. Fix hallucinations — remove anything not in Master CV
  2. Fix AI voice — replace "Leveraged/Utilized/Spearheaded" with "Built/Set up/Wrote/Fixed"
  3. Fill keyword gaps — add missing JD keywords WHERE authentically in Master CV
  4. Strengthen bullets — apply STAR method: Action + Result
  5. Improve ATS density — mirror JD phrasing
  6. Fix formatting

## HUMAN TONE
- BANNED: "Leveraged", "Utilized", "Spearheaded", "Orchestrated", "Robust", "Seamless"
- USE: "Built", "Set up", "Wrote", "Fixed", "Shipped", "Cut", "Rolled out", "Sped up"
- Vary bullet lengths. Write like an engineer.

## ANTI-HALLUCINATION
- ONLY use tech/metrics from Master CV. Never invent.
- Never inflate numbers.

Output ONLY the improved Markdown resume, no explanations.
Either output the refined resume OR call exit_loop. Not both.""",
    description="Improves resume based on critic feedback, or exits loop if resume is approved.",
    tools=[exit_loop],
    output_key=STATE_CURRENT_RESUME,
)

# ── Step 4: Refinement Loop ───────────────────────────────────
refinement_loop = LoopAgent(
    name="RefinementLoop",
    sub_agents=[critic_agent, refiner_agent],
    max_iterations=3,
)

# ── Root Agent: Full Pipeline ─────────────────────────────────
root_agent = SequentialAgent(
    name="ResumeTailorPipeline",
    description="Self-improving resume tailor: extracts JD → matches content → writes resume → critique/refine loop.",
    sub_agents=[
        jd_extractor_agent,
        matcher_agent,
        initial_writer_agent,
        refinement_loop,
    ],
)
