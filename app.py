import os
import streamlit as st
import streamlit.components.v1 as stcomponents
from pathlib import Path
from io import StringIO

# Fix relative imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pipeline import run_pipeline, DEFAULT_MAX_ITERATIONS, DEFAULT_PASS_THRESHOLD
from src.models import Iteration, MatchReport
from src.job_search import search_jobs, build_posting, JobPosting
from src.database import SessionLocal, get_db, Run, Iteration as DBIteration, MemoryItem, JobApplication
from src.exceptions import ResumeTailorError, ConfigError, APIError, DatabaseError, ValidationError
from src import config

from rich.console import Console

st.set_page_config(page_title="Resume Tailor", page_icon="🎯", layout="wide")

# ── Custom CSS Overhaul ──────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #1e293b;
    }

    h1, h2, h3, [data-testid="stHeader"] {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        color: #0f172a !important;
        letter-spacing: -0.02em;
    }

    .main .block-container {
        padding-top: 3rem;
        padding-bottom: 5rem;
        max-width: 1200px;
    }

    [data-testid="stVerticalBlock"] > div > div > div[data-testid="element-container"] .stContainer,
    .stQuote, .stChatMessage, .stExpander, div[data-testid="stForm"], div.stContainer {
        border: 1px solid rgba(226, 232, 240, 0.8) !important;
        border-radius: 12px !important;
        background-color: #ffffff !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05) !important;
        padding: 1.5rem !important;
        margin-bottom: 1rem !important;
    }

    [data-testid="stSidebar"] {
        background-color: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }

    .resume-paper {
        background-color: #ffffff;
        color: #1e293b;
        padding: 40px 60px !important;
        border-radius: 4px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
        border: 1px solid #e2e8f0;
        line-height: 1.6;
        font-size: 0.95rem;
        max-width: 800px;
        margin: 2rem auto;
    }
    
    .resume-paper h1, .resume-paper h2, .resume-paper h3 {
        color: #0f172a !important;
        margin-top: 1.5rem;
        border-bottom: 1px solid #f1f5f9;
        padding-bottom: 0.5rem;
    }

    .match-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        color: white;
    }
    .badge-high { background-color: #10b981; }
    .badge-mid { background-color: #f59e0b; }
    .badge-low { background-color: #64748b; }

    .stButton > button {
        border-radius: 8px !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        border: none !important;
    }

    [data-testid="stMetricValue"] {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
        color: #2563eb;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎯 Job Resume Tailor")
st.markdown("Customizing your resume to match each job can dramatically increases your odds of success! Customize your resume and land your dream job today!")

st.sidebar.header("Configuration")
max_iterations = st.sidebar.slider("Max Iterations", 1, 5, DEFAULT_MAX_ITERATIONS)
pass_threshold = st.sidebar.slider("Pass Threshold", 50.0, 100.0, float(DEFAULT_PASS_THRESHOLD))

# Handle CV Upload vs Default
st.sidebar.subheader("Master CV Data")
uploaded_cv = st.sidebar.file_uploader("Upload Master CV (JSON)", type=["json"], help="Upload your personal master_cv.json file. If None is provided, the sample data/master_cv.json will be used.")

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
    st.sidebar.info(f"Using default CV: `{cv_path}`")

# ── JD Input Section ─────────────────────────────────────────────

jd_tab1, jd_tab2, jd_tab3, jd_tab4 = st.tabs(["🔍 Search Jobs", "📝 Paste JD", "📜 History", "🧠 Memory"])

with jd_tab1:
    st.header("Search")
    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        search_query = st.text_input("Job title / keywords", placeholder="Dream Job", label_visibility="collapsed")
    with search_col2:
        search_location = st.text_input("Location", value="New York, NY", label_visibility="collapsed")

    if st.button("Search"):
        if not search_query.strip():
            st.error("Please enter a search query.")
        elif not config.SERPAPI_KEY:
            st.error("SERPAPI_KEY is not configured. Please add it to your .env file.")
        else:
            try:
                with st.spinner("Searching jobs..."):
                    _console = Console(file=StringIO())
                    raw_jobs = search_jobs(config.SERPAPI_KEY, search_query, search_location.strip(), 1, _console)
                    st.session_state.search_results = [build_posting(raw, None, "no_fetch", None) for raw in raw_jobs]
                    st.session_state.expanded_job_idx = None
            except Exception as e:
                st.error(f"Job search failed: {e}")

# ── Custom CSS Overhaul ──────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #1e293b;
    }

    h1, h2, h3, [data-testid="stHeader"] {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        color: #0f172a !important;
        letter-spacing: -0.02em;
    }

    .main .block-container {
        padding-top: 3rem;
        padding-bottom: 5rem;
        max-width: 1200px;
    }

    [data-testid="stVerticalBlock"] > div > div > div[data-testid="element-container"] .stContainer,
    .stQuote, .stChatMessage, .stExpander, div[data-testid="stForm"], div.stContainer {
        border: 1px solid rgba(226, 232, 240, 0.8) !important;
        border-radius: 12px !important;
        background-color: #ffffff !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05) !important;
        padding: 1.5rem !important;
        margin-bottom: 1rem !important;
    }

    [data-testid="stSidebar"] {
        background-color: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }

    .resume-paper {
        background-color: #ffffff;
        color: #1e293b;
        padding: 40px 60px !important;
        border-radius: 4px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
        border: 1px solid #e2e8f0;
        line-height: 1.6;
        font-size: 0.95rem;
        max-width: 800px;
        margin: 2rem auto;
    }
    
    .resume-paper h1, .resume-paper h2, .resume-paper h3 {
        color: #0f172a !important;
        margin-top: 1.5rem;
        border-bottom: 1px solid #f1f5f9;
        padding-bottom: 0.5rem;
    }

    .match-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        color: white;
    }
    .badge-high { background-color: #10b981; }
    .badge-mid { background-color: #f59e0b; }
    .badge-low { background-color: #64748b; }

    .stButton > button {
        border-radius: 8px !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        border: none !important;
    }

    [data-testid="stMetricValue"] {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
        color: #2563eb;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ── Search Results ─────────────────────────────────────────────
if st.session_state.get("search_results"):
    st.subheader("Search Results")
    results: list[JobPosting] = st.session_state.search_results
    expanded_idx = st.session_state.get("expanded_job_idx")

    for i, job in enumerate(results):
        is_expanded = expanded_idx == i

        with st.container():
            st.markdown(f'<div id="job-{i}"></div>', unsafe_allow_html=True)
            col_title, col_button = st.columns([4, 1])
            with col_title:
                st.markdown(f"#### {job.title}")
                st.caption(f"🏢 {job.company} | 📍 {job.location}")
            with col_button:
                action_label = "Close" if is_expanded else "Details"
                if st.button(action_label, key=f"job_toggle_{i}", use_container_width=True):
                    st.session_state.expanded_job_idx = None if is_expanded else i
                    if not is_expanded:
                        st.session_state.scroll_to_job = i
                    st.rerun()

            if is_expanded:
                st.divider()
                if st.button("✨ Tailor My Resume", key=f"tailor_top_{i}", type="primary", use_container_width=True):
                    st.session_state.selected_jd = job.description
                    st.session_state.auto_run = True
                    st.rerun()

                if job.description:
                    st.markdown(job.description)
                else:
                    st.info("No description available for this job.")

    if st.session_state.get("scroll_to_job") is not None:
        scroll_idx = st.session_state.scroll_to_job
        del st.session_state["scroll_to_job"]
        stcomponents.html(
            f'<script>window.parent.document.getElementById("job-{scroll_idx}")'
            f'.scrollIntoView({{behavior: "smooth"}});</script>',
            height=0,
        )

with jd_tab2:
    st.header("Paste JD")
    manual_jd = st.text_area("Job Description", height=300, placeholder="Paste the job description text here...")
    if st.button("Use This JD", type="primary"):
        if manual_jd.strip():
            st.session_state.selected_jd = manual_jd
            st.session_state.auto_run = True
            st.rerun()
        else:
            st.error("Please paste a job description first.")

with jd_tab3:
    st.header("Job Search History")
    try:
        with get_db() as db:
            runs = db.query(Run).order_by(Run.started_at.desc()).limit(20).all()
            if not runs:
                st.info("No history yet. Start tailoring to see results!")
            else:
                for run in runs:
                    app = run.job_application
                    score = run.final_score or 0
                    badge_class = "badge-high" if score >= 85 else "badge-mid" if score >= 70 else "badge-low"
                    
                    with st.container():
                        col_info, col_action = st.columns([3, 1])
                        with col_info:
                            st.markdown(f"**{app.title}**")
                            st.caption(f"🏢 {app.company} | 📅 {run.started_at.strftime('%Y-%m-%d %H:%M')}")
                            st.markdown(f'<span class="match-badge {badge_class}">Score: {score}/100</span> &nbsp; Status: `{run.status}`', unsafe_allow_html=True)
                        with col_action:
                            if st.button("Reuse JD", key=f"reuse_run_{run.id}", use_container_width=True):
                                st.session_state.selected_jd = app.jd_text
                                st.session_state.auto_run = True
                                st.rerun()
    except Exception as e:
        st.error(f"Failed to load history: {e}")

with jd_tab4:
    st.header("Learned Memory")
    st.markdown("These patterns are automatically extracted from your high-scoring resumes.")
    try:
        with get_db() as db:
            memories = db.query(MemoryItem).order_by(MemoryItem.created_at.desc()).all()
            if not memories:
                st.info("The agent hasn't 'learned' anything yet.")
            else:
                for mem in memories:
                    with st.container():
                        st.markdown(f"### {mem.role_tag.title()}")
                        st.write(mem.critic_summary)
                        st.caption(f"Learned on {mem.created_at.strftime('%Y-%m-%d')}")
    except Exception as e:
        st.error(f"Failed to load memory: {e}")

# ── Pipeline Section ───────────────────────────────────────────

st.markdown('<div id="pipeline-section"></div>', unsafe_allow_html=True)

auto_run = st.session_state.get("auto_run", False)
if auto_run:
    del st.session_state["auto_run"]
    stcomponents.html(
        '<script>window.parent.document.getElementById("pipeline-section")'
        '.scrollIntoView({behavior: "smooth"});</script>',
        height=0,
    )

jd_text = st.session_state.get("selected_jd", "")

if st.button("Tailor Resume", type="primary") or auto_run:
    if not jd_text.strip():
        st.error("Please search for and select a job first.")
        st.stop()

    _running_banner = st.empty()
    _running_banner.info("Pipeline is running... This may take a moment.")

    # Progress placeholders
    progress_bar = st.progress(0)
    status_text = st.empty()

    def _cleanup():
        progress_bar.empty()
        status_text.empty()
        _running_banner.empty()

    def on_iteration_callback(iteration: Iteration):
        status_text.text(f"Iteration {iteration.version} completed: Score {iteration.match_report.score}/100")
        progress_bar.progress(iteration.version / max_iterations)

    with st.spinner("Executing Pipeline..."):
        try:
            result = run_pipeline(
                jd_text=jd_text,
                cv_path=Path(cv_path),
                max_iterations=max_iterations,
                pass_threshold=pass_threshold,
                on_iteration=on_iteration_callback
            )
        except ConfigError as e:
            _cleanup()
            st.error(f"🔑 **Configuration/Auth Error:** {e}")
            st.info("💡 **Tip:** Check your `.env` file for a valid `GEMINI_API_KEY`.")
            st.stop()
        except APIError as e:
            _cleanup()
            st.error(f"🌐 **API Error ({e.status_code or 'Unknown'}):** {e}")
            st.info("💡 **Tip:** This might be a transient network issue or rate limit. Try again in a moment.")
            st.stop()
        except (ValidationError, DatabaseError) as e:
            _cleanup()
            st.error(f"❌ **Validation/Database Error:** {e}")
            st.stop()
        except Exception as e:
            _cleanup()
            st.error(f"Unexpected Pipeline failure: {e}")
            st.stop()

    _cleanup()

    st.success(f"Pipeline finished after {result.total_iterations} iteration(s)!")

    st.subheader("📊 Self-Improvement Progress")
    history = []
    for it in result.iterations:
        history.append({
            "Version": it.version,
            "Score": it.match_report.score,
            "Coverage": f"{it.match_report.keyword_coverage:.0%}",
            "Fixes": len(it.match_report.fixes),
            "Passed": "✅ Yes" if it.passed else "🔄 No"
        })
    if history:
        st.table(history)

    # Display results
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📋 JD Profile")
        jdp = result.jd_profile
        st.markdown(
            f"**Target Title:** {jdp.target_title} &nbsp;|&nbsp; **Seniority:** {jdp.seniority}",
            unsafe_allow_html=True,
        )

        def _chips(items: list, color: str = "#0e6efd") -> str:
            style = (
                f"display:inline-block;background:{color};color:#fff;"
                "border-radius:12px;padding:2px 10px;margin:2px 3px;"
                "font-size:0.8rem;white-space:nowrap;"
            )
            return " ".join(f'<span style="{style}">{item}</span>' for item in items)

        st.markdown("**Must-Have Skills**")
        if jdp.must_have_skills:
            st.markdown(_chips(jdp.must_have_skills, "#0e6efd"), unsafe_allow_html=True)
        else:
            st.caption("None listed")

        st.markdown("**Nice-to-Have Skills**")
        if jdp.nice_to_have_skills:
            st.markdown(_chips(jdp.nice_to_have_skills, "#6c757d"), unsafe_allow_html=True)
        else:
            st.caption("None listed")

        with st.expander("Responsibilities"):
            for r in jdp.responsibilities:
                st.markdown(f"- {r}")

        with st.expander("Keywords"):
            if jdp.keywords:
                st.markdown(_chips(jdp.keywords, "#198754"), unsafe_allow_html=True)
            else:
                st.caption("None listed")

        st.subheader("🎯 Selection Plan")
        sp = result.selection_plan
        reason = sp.reasoning

        col_match, col_miss = st.columns(2)
        with col_match:
            st.metric("Matched Skills", len(reason.matched_skills))
        with col_miss:
            st.metric("Missing Skills", len(reason.missing_skills))

        st.markdown("**Matched Skills**")
        if reason.matched_skills:
            st.markdown(_chips(reason.matched_skills, "#198754"), unsafe_allow_html=True)
        else:
            st.caption("None")

        st.markdown("**Missing Skills**")
        if reason.missing_skills:
            st.markdown(_chips(reason.missing_skills, "#dc3545"), unsafe_allow_html=True)
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

        if result.final_report and result.total_iterations > 1:
            st.subheader("🔍 Final Critic Report")
            st.json(result.final_report.model_dump())

    with col2:
        if result.final_resume:
            st.subheader(f"✨ Final Resume (v{result.total_iterations})")
            st.markdown(f'<div class="resume-paper">{result.final_resume}</div>', unsafe_allow_html=True)

            st.download_button(
                "Download Resume (Markdown)",
                data=result.final_resume,
                file_name="tailored_resume.md",
                mime="text/markdown",
                use_container_width=True
            )
        elif result.resume_v1:
             st.subheader("📝 Resume v1")
             st.markdown(f'<div class="resume-paper">{result.resume_v1}</div>', unsafe_allow_html=True)
        else:
             st.warning("No resume generated.")
