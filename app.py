import os
import sys
import html
from io import StringIO
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as stcomponents
from rich.console import Console

# Fix relative imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pipeline import run_pipeline, DEFAULT_MAX_ITERATIONS, DEFAULT_PASS_THRESHOLD
from src.models import Iteration, MatchReport
from src.job_search import search_jobs, build_posting, JobPosting
from src.database import (
    SessionLocal,
    get_db,
    Run,
    Iteration as DBIteration,
    MemoryItem,
    JobApplication,
    init_db,
)
from sqlalchemy.orm import joinedload
from src.exceptions import (
    ResumeTailorError,
    ConfigError,
    APIError,
    DatabaseError,
    ValidationError,
)
from src import config

# ──────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Resume Tailor", page_icon="🎯", layout="wide")

# ──────────────────────────────────────────────────────────────
# UI Theme (single injection, no duplicates)
# ──────────────────────────────────────────────────────────────
@st.cache_resource
def inject_theme():
    st.markdown(
        """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

      :root {
        --bg: #fafafa;
        --panel: #ffffff;
        --text: #0a0a0a;
        --muted: #6b7280;
        --border: rgba(0,0,0,0.08);
        --brand: #171717; /* Dark Vercel-style black */
        --brand-accent: #2563eb;
        --ok: #10b981;
        --warn: #f59e0b;
        --danger: #ef4444;
        --radius: 8px;
        --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);

        /* Spacing System */
        --space-1: 6px;
        --space-2: 12px;
        --space-3: 20px;
        --space-4: 32px;
      }

      html, body, [data-testid="stAppViewContainer"] {
        background: var(--bg);
        font-family: 'Inter', -apple-system, system-ui, sans-serif;
        color: var(--text);
      }

      h1, h2, h3, [data-testid="stHeader"] {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
        color: var(--text);
      }

      .main .block-container {
        max-width: 1100px;
        padding-top: var(--space-4);
        padding-bottom: var(--space-4);
      }

      /* Sidebar */
      [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid var(--border);
      }

      /* Minimalist Card */
      .rt-card {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow-sm);
        padding: var(--space-3);
        margin-bottom: var(--space-3);
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
      }
      .rt-card:hover {
        border-color: rgba(0,0,0,0.15);
        box-shadow: var(--shadow);
      }

      /* Selection Bar */
      .rt-selection-bar {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: var(--space-2) var(--space-3);
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: var(--space-3);
      }

      /* Badge */
      .rt-badge {
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.02em;
      }
      .rt-high { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
      .rt-mid { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
      .rt-low { background: #f9fafb; color: #374151; border: 1px solid #e5e7eb; }

      /* Buttons */
      .stButton > button {
        border-radius: 6px !important;
        border: 1px solid var(--border) !important;
        background: white !important;
        color: var(--text) !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        padding: 8px 16px !important;
      }
      .stButton > button:hover {
        border-color: rgba(0,0,0,0.2) !important;
        background: #f9fafb !important;
      }
      .stButton > button[kind="primary"] {
        background: var(--brand) !important;
        color: white !important;
        border: none !important;
      }
      .stButton > button[kind="primary"]:hover {
        background: #262626 !important;
        transform: translateY(-1px);
      }

      /* Stepper UI */
      .stepper-container {
        display: flex;
        justify-content: space-between;
        margin-bottom: var(--space-3);
        position: relative;
      }
      .step-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        flex: 1;
        position: relative;
        z-index: 1;
      }
      .step-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #e5e7eb;
        margin-bottom: 8px;
      }
      .step-dot.active { background: var(--brand-accent); box-shadow: 0 0 0 4px rgba(37,99,235,0.1); }
      .step-label { font-size: 0.7rem; font-weight: 600; color: var(--muted); text-transform: uppercase; }
      .step-label.active { color: var(--text); }

      /* Resume Paper */
      .resume-paper {
        background: #ffffff;
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 40px 60px !important;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
      }

      /* Clean loading banner */
      .rt-loading {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: var(--space-2) var(--space-3);
        box-shadow: var(--shadow-sm);
        margin-bottom: var(--space-3);
      }
      .rt-loading-title{
        font-weight: 600;
        font-size: .95rem;
      }
      .rt-loading-sub{
        color: var(--muted);
        font-size: .87rem;
        margin-top: 2px;
      }
      .rt-progress {
        height: 6px;
        border-radius: 999px;
        background: rgba(0,0,0,.06);
        overflow: hidden;
        margin-top: 10px;
      }
      .rt-progress > div{
        height: 100%;
        width: 20%;
        background: var(--brand);
        border-radius: 999px;
        transition: width .25s ease;
      }

      /* Hide Streamlit chrome */
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
    </style>
    """,
        unsafe_allow_html=True,
    )


inject_theme()

# Ensure database is initialized (once per app session)
@st.cache_resource
def cached_init_db():
    init_db()


cached_init_db()

# ──────────────────────────────────────────────────────────────
# Caching Layer
# ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_cached_llm_client():
    return config.get_llm_client()


@st.cache_data
def cached_search_jobs(api_key, query, location, num_pages):
    _console = Console(file=StringIO())
    return search_jobs(api_key, query, location, num_pages, _console)


# ──────────────────────────────────────────────────────────────
# UI helpers
# ──────────────────────────────────────────────────────────────
def hero():
    selected = st.session_state.get("selected_jd", "")
    has_jd = bool(selected.strip())

    if not has_jd:
        st.markdown(
            """
            <div style="margin-bottom: var(--space-4);">
                <h1 style="font-size: 2.25rem; font-weight: 700; margin-bottom: 8px;">Resume Tailor</h1>
                <p style="color: var(--muted); font-size: 1.1rem;">Precision resume optimization for your next role.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        preview = selected.strip().replace("\n", " ")
        preview = (preview[:80] + "...") if len(preview) > 80 else preview
        st.markdown(
            f"""
            <div class="rt-selection-bar">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 8px; height: 8px; border-radius: 50%; background: var(--ok);"></div>
                    <div>
                        <span style="font-weight: 600; font-size: 0.9rem;">Selected Job</span>
                        <span style="margin: 0 8px; color: var(--border);">|</span>
                        <span style="color: var(--muted); font-size: 0.85rem;">{html.escape(preview)}</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, _ = st.columns([1, 4])
        with col1:
            if st.button("Change Job", use_container_width=True):
                st.session_state.selected_jd = ""
                st.rerun()


def job_card(job: JobPosting, i: int):
    st.markdown('<div class="rt-card">', unsafe_allow_html=True)

    cols = st.columns([5, 2])
    with cols[0]:
        st.markdown(f"**{job.title}**")
        st.caption(f"{job.company}  ·  {job.location}")
    with cols[1]:
        if st.button("Select Job", key=f"tailor_{i}", type="primary", use_container_width=True):
            st.session_state.selected_jd = job.description or ""
            st.session_state.auto_run = True
            st.session_state.scroll_to_pipeline = True
            st.rerun()

    with st.expander("View job description"):
        if job.description:
            st.markdown(job.description)
        else:
            st.info("No description available for this job.")

    st.markdown("</div>", unsafe_allow_html=True)


def pipeline_runner_controls() -> bool:
    run_clicked = st.button(
        "Begin Tailoring",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.get("is_running", False),
    )
    return run_clicked


def render_stepper(current_step: int):
    steps = ["Extract", "Plan", "Rewrite", "Critique", "Finalize"]
    cols = st.columns(len(steps))
    for i, step in enumerate(steps):
        is_active = i <= current_step
        with cols[i]:
            st.markdown(
                f"""
                <div class="step-item">
                    <div class="step-dot {"active" if is_active else ""}"></div>
                    <div class="step-label {"active" if is_active else ""}">{step}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def set_loading(loading_box: st.delta_generator.DeltaGenerator, title: str, subtitle: str, pct: int):
    title = html.escape(title)
    subtitle = html.escape(subtitle)
    pct = max(0, min(100, int(pct)))
    loading_box.markdown(
        f"""
        <div class="rt-loading">
          <div class="rt-loading-title">{title}</div>
          <div class="rt-loading-sub">{subtitle}</div>
          <div class="rt-progress"><div style="width:{pct}%;"></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def chips(items: list, color: str) -> str:
    style = (
        f"display:inline-block;background:{color};color:#fff;"
        "border-radius:4px;padding:2px 8px;margin:3px 4px 0 0;"
        "font-size:0.75rem;font-weight:600;white-space:nowrap;"
    )
    return " ".join(f'<span style="{style}">{html.escape(str(item))}</span>' for item in items)


# ──────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────
hero()

# ──────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Configuration")

    with st.expander("Pipeline Settings", expanded=True):
        max_iterations = st.slider("Max Iterations", 1, 5, DEFAULT_MAX_ITERATIONS)
        pass_threshold = st.slider("Pass Threshold", 50.0, 100.0, float(DEFAULT_PASS_THRESHOLD))
        demo_mode = st.toggle("Demo Mode (Instant Replay)", value=False, help="Use cached results if available to bypass API limits.")

    st.markdown("---")
    st.markdown("### Master CV Data")
    uploaded_cv = st.file_uploader(
        "Upload JSON CV",
        type=["json"],
        help="Custom master_cv.json. Defaults to project data/master_cv.json.",
    )

    if st.button("Reset session", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

cv_path = "data/master_cv.json"
if uploaded_cv is not None:
    temp_dir = Path("output/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_cv_path = temp_dir / "uploaded_cv.json"
    with open(temp_cv_path, "wb") as f:
        f.write(uploaded_cv.getbuffer())
    cv_path = str(temp_cv_path)
    st.sidebar.success(f"Using uploaded CV: {uploaded_cv.name}")
else:
    st.sidebar.info("Using default CV data")

# ──────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────
jd_tab1, jd_tab2, jd_tab3, jd_tab4 = st.tabs(["Search Jobs", "Paste Description", "Run History", "Learned Memory"])

# ──────────────────────────────────────────────────────────────
# Tab 1: Search Jobs
# ──────────────────────────────────────────────────────────────
with jd_tab1:
    st.markdown("### Search Jobs")
    st.caption("Find active postings via SerpAPI.")
    search_col1, search_col2, search_col3 = st.columns([3, 2, 1])
    with search_col1:
        search_query = st.text_input("Keywords", placeholder="Software Engineer", label_visibility="collapsed")
    with search_col2:
        search_location = st.text_input("Location", value="Remote", label_visibility="collapsed")
    with search_col3:
        do_search = st.button("Search", type="primary", use_container_width=True)

    if do_search:
        if not search_query.strip():
            st.error("Please enter a search query.")
        elif not config.SERPAPI_KEY:
            st.error("SERPAPI_KEY is not configured. Please add it to your .env file.")
        else:
            try:
                with st.spinner("Searching jobs..."):
                    raw_jobs = cached_search_jobs(config.SERPAPI_KEY, search_query, search_location.strip(), 1)
                    st.session_state.search_results = [build_posting(raw, None, "no_fetch", None) for raw in raw_jobs]
            except Exception as e:
                st.error(f"Job search failed: {e}")

    if st.session_state.get("search_results"):
        st.subheader("Results")
        results: list[JobPosting] = st.session_state.search_results
        for i, job in enumerate(results):
            job_card(job, i)
    else:
        st.caption("Search to see job postings here.")

# ──────────────────────────────────────────────────────────────
# Tab 2: Paste JD
# ──────────────────────────────────────────────────────────────
with jd_tab2:
    st.markdown("### Paste Job Description")
    st.caption("Manually provide the requirements for tailoring.")
    manual_jd = st.text_area(
        "Job Description Text",
        height=300,
        placeholder="Paste full job description here...",
        label_visibility="collapsed",
    )
    use_jd = st.button("Save Description", type="primary", use_container_width=True)

    if use_jd:
        if manual_jd.strip():
            st.session_state.selected_jd = manual_jd
            st.session_state.auto_run = True
            st.session_state.scroll_to_pipeline = True
            st.rerun()
        else:
            st.error("Please paste a job description first.")

# ──────────────────────────────────────────────────────────────
# Tab 3: History
# ──────────────────────────────────────────────────────────────
with jd_tab3:
    st.markdown("### Search History")
    st.caption("Recent tailoring runs and their outcomes.")

    try:
        st.button("Refresh History")
        with get_db() as db:
            runs = db.query(Run).options(joinedload(Run.job_application)).order_by(Run.started_at.desc()).limit(20).all()
            if runs:
                for run in runs:
                    app = run.job_application
                    score = run.final_score or 0
                    cls = "rt-high" if score >= 85 else "rt-mid" if score >= 70 else "rt-low"

                    st.markdown('<div class="rt-card">', unsafe_allow_html=True)
                    cols = st.columns([4, 1])
                    with cols[0]:
                        st.markdown(f"**{app.title}**")
                        st.caption(f"{app.company}  ·  {run.started_at.strftime('%Y-%m-%d %H:%M')}")
                        st.markdown(
                            f'<span class="rt-badge {cls}">Score {int(score)}/100</span>'
                            f'&nbsp;&nbsp;<span style="color:var(--muted);font-weight:650;">Status: {html.escape(str(run.status))}</span>',
                            unsafe_allow_html=True,
                        )
                    with cols[1]:
                        if st.button("Reuse JD", key=f"reuse_run_{run.id}", use_container_width=True):
                            st.session_state.selected_jd = app.jd_text
                            st.session_state.auto_run = True
                            st.session_state.scroll_to_pipeline = True
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("No history yet.")
    except Exception as e:
        st.error(f"Failed to load history: {e}")

# ──────────────────────────────────────────────────────────────
# Tab 4: Memory
# ──────────────────────────────────────────────────────────────
with jd_tab4:
    st.markdown("### Shared Context")
    st.caption("Insights extracted from previous successful runs.")

    try:
        with get_db() as db:
            memories = db.query(MemoryItem).order_by(MemoryItem.created_at.desc()).all()
            if memories:
                for mem in memories:
                    st.markdown('<div class="rt-card">', unsafe_allow_html=True)
                    st.markdown(f"**{mem.role_tag.title()}**")
                    st.write(mem.critic_summary)
                    st.caption(f"Learned on {mem.created_at.strftime('%Y-%m-%d')}")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("No memory items yet.")
    except Exception as e:
        st.error(f"Failed to load memory: {e}")

# ──────────────────────────────────────────────────────────────
# Pipeline Section
# ──────────────────────────────────────────────────────────────
st.markdown('<div id="pipeline-section"></div>', unsafe_allow_html=True)

if st.session_state.get("scroll_to_pipeline"):
    st.session_state.pop("scroll_to_pipeline", None)
    stcomponents.html(
        """
        <script>
          window.parent.document.getElementById("pipeline-section")
            .scrollIntoView({behavior: "smooth"});
        </script>
        """,
        height=0,
    )

auto_run = st.session_state.get("auto_run", False)
if auto_run:
    st.session_state.pop("auto_run", None)

jd_text = st.session_state.get("selected_jd", "")

run_clicked = pipeline_runner_controls()

if run_clicked or auto_run:
    if not jd_text.strip():
        st.error("Please search for and select a job first (or paste a JD).")
        st.stop()

    stepper_placeholder = st.empty()
    status_text = st.empty()
    loading_box = st.empty()

    st.session_state["is_running"] = True

    def _cleanup():
        stepper_placeholder.empty()
        status_text.empty()
        loading_box.empty()
        st.session_state["is_running"] = False

    def on_iteration_callback(iteration: Iteration | None, status: str | None):
        step_idx = 0
        if status:
            if "Extracting" in status:
                step_idx = 0
            elif "Matching" in status:
                step_idx = 1
            elif "Generating" in status or "Refining" in status:
                step_idx = 2
            elif "Performing quality" in status:
                step_idx = 3
            elif "complete" in status.lower():
                step_idx = 4

            with stepper_placeholder:
                render_stepper(step_idx)

            pct_map = {0: 20, 1: 40, 2: 65, 3: 85, 4: 95}
            pct = pct_map.get(step_idx, 20)

            titles = ["Extracting", "Planning", "Rewriting", "Reviewing", "Finalizing"]
            title = f"{titles[step_idx]}…"
            set_loading(loading_box, "Tailoring in progress", status, pct)

            status_text.caption(status)

    # Initial loading state (no spinner)
    set_loading(loading_box, "Tailoring in progress", "Starting pipeline…", 5)

    try:
        result = run_pipeline(
            jd_text=jd_text,
            cv_path=Path(cv_path),
            max_iterations=max_iterations,
            pass_threshold=pass_threshold,
            on_iteration=on_iteration_callback,
            demo_mode=demo_mode,
        )
    except ConfigError as e:
        _cleanup()
        st.error(f"Configuration/Auth Error: {e}")
        st.info("Tip: Check your .env file for a valid GEMINI_API_KEY.")
        st.stop()
    except APIError as e:
        _cleanup()
        st.error(f"API Error ({e.status_code or 'Unknown'}): {e}")
        st.info("Tip: This might be a transient network issue. Please try again.")
        st.stop()
    except (ValidationError, DatabaseError) as e:
        _cleanup()
        st.error(f"Validation/Database Error: {e}")
        st.stop()
    except Exception as e:
        _cleanup()
        st.error(f"System failure: {e}")
        st.stop()

    _cleanup()
    st.session_state.pop("history_data", None)
    st.session_state.pop("memory_data", None)

    st.success(f"Tailoring complete after {result.total_iterations} iterations.")

    st.markdown("### Improvement Progress")
    history = []
    for it in result.iterations:
        history.append(
            {
                "Version": it.version,
                "Score": it.match_report.score,
                "Coverage": f"{it.match_report.keyword_coverage:.0%}",
                "Fixes": len(it.match_report.fixes),
                "Passed": "Yes" if it.passed else "No",
            }
        )

    if history:
        st.dataframe(
            history,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Version": st.column_config.NumberColumn(width="small"),
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                "Coverage": st.column_config.TextColumn(width="small"),
                "Fixes": st.column_config.NumberColumn(width="small"),
                "Passed": st.column_config.TextColumn(width="small"),
            },
        )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="rt-card">', unsafe_allow_html=True)
        st.markdown("### JD Profile")
        jdp = result.jd_profile
        st.markdown(f"**Target Title:** {jdp.target_title} &nbsp;|&nbsp; **Seniority:** {jdp.seniority}")

        st.markdown("**Must-Have Skills**")
        if jdp.must_have_skills:
            st.markdown(chips(jdp.must_have_skills, "#2563eb"), unsafe_allow_html=True)
        else:
            st.caption("None listed")

        st.markdown("**Nice-to-Have Skills**")
        if jdp.nice_to_have_skills:
            st.markdown(chips(jdp.nice_to_have_skills, "#64748b"), unsafe_allow_html=True)
        else:
            st.caption("None listed")

        with st.expander("Responsibilities"):
            for r in jdp.responsibilities:
                st.markdown(f"- {r}")

        with st.expander("Keywords"):
            if jdp.keywords:
                st.markdown(chips(jdp.keywords, "#10b981"), unsafe_allow_html=True)
            else:
                st.caption("None listed")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="rt-card">', unsafe_allow_html=True)
        st.markdown("### Selection Plan")
        sp = result.selection_plan
        reason = sp.reasoning

        a, b = st.columns(2)
        with a:
            st.metric("Matched Skills", len(reason.matched_skills))
        with b:
            st.metric("Missing Skills", len(reason.missing_skills))

        st.markdown("**Matched Skills**")
        if reason.matched_skills:
            st.markdown(chips(reason.matched_skills, "#10b981"), unsafe_allow_html=True)
        else:
            st.caption("None")

        st.markdown("**Missing Skills**")
        if reason.missing_skills:
            st.markdown(chips(reason.missing_skills, "#ef4444"), unsafe_allow_html=True)
        else:
            st.caption("None — great fit!")

        if sp.skills_ordered:
            st.markdown("**Skills to Emphasise (ordered)**")
            for idx, skill in enumerate(sp.skills_ordered, 1):
                st.markdown(f"{idx}. {skill}")

        with st.expander("Selected Experience & Projects"):
            if sp.selected_experience_ids:
                st.markdown("**Experience IDs**")
                for eid in sp.selected_experience_ids:
                    st.markdown(f"- `{eid}`")
            if sp.selected_project_ids:
                st.markdown("**Project IDs**")
                for pid in sp.selected_project_ids:
                    st.markdown(f"- `{pid}`")
        st.markdown("</div>", unsafe_allow_html=True)

        if result.final_report and result.total_iterations > 1:
            with st.expander("Final Auditor Report", expanded=False):
                st.json(result.final_report.model_dump())

    with col2:
        if result.final_resume:
            st.markdown(f"### Final Resume (v{result.total_iterations})")
            st.markdown(f'<div class="resume-paper">{result.final_resume}</div>', unsafe_allow_html=True)

            st.download_button(
                "Download Resume (Markdown)",
                data=result.final_resume,
                file_name="tailored_resume.md",
                mime="text/markdown",
                use_container_width=True,
            )
        elif result.resume_v1:
            st.subheader("Resume v1")
            st.markdown(f'<div class="resume-paper">{result.resume_v1}</div>', unsafe_allow_html=True)
        else:
            st.warning("No resume generated.")