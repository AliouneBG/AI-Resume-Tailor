import os
import streamlit as st
import json
from pathlib import Path

# Fix relative imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.pipeline import run_pipeline, DEFAULT_MAX_ITERATIONS, DEFAULT_PASS_THRESHOLD
from src.models import Iteration

st.set_page_config(page_title="Resume Tailor", page_icon="🎯", layout="wide")

st.title("🎯 Job Resume Tailor")
st.markdown("A self-improving agent that tailors your resume to a specific job description.")

st.sidebar.header("Configuration")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Required to run the LLM. You can provide this later.")
if api_key:
    # Set the environment variable so the pipeline picks it up
    os.environ["GEMINI_API_KEY"] = api_key

max_iterations = st.sidebar.slider("Max Iterations", 1, 5, DEFAULT_MAX_ITERATIONS)
pass_threshold = st.sidebar.slider("Pass Threshold", 50.0, 100.0, float(DEFAULT_PASS_THRESHOLD))

# Handle CV Upload vs Default
st.sidebar.subheader("Master CV Data")
uploaded_cv = st.sidebar.file_uploader("Upload Master CV (JSON)", type=["json"], help="Upload your personal master_cv.json file. If None is provided, the sample data/master_cv.json will be used.")

cv_path = "data/master_cv.json"
if uploaded_cv is not None:
    # Save uploaded file temporarily for the pipeline
    temp_dir = Path("output/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_cv_path = temp_dir / "uploaded_cv.json"
    with open(temp_cv_path, "wb") as f:
        f.write(uploaded_cv.getbuffer())
    cv_path = str(temp_cv_path)
    st.sidebar.success(f"Using uploaded CV: {uploaded_cv.name}")
else:
    st.sidebar.info(f"Using default CV: `{cv_path}`")

jd_text = st.text_area("Job Description", height=200, placeholder="Paste the job description here...")

if st.button("Tailor Resume", type="primary"):
    if not jd_text.strip():
        st.error("Please enter a job description.")
        st.stop()
    if not os.getenv("GEMINI_API_KEY") and not api_key:
        st.warning("No API Key provided. The LLM extraction will likely fail or fall back to dummy data.")
        
    st.info("Pipeline is running... This may take a moment.")
    
    # Progress placeholders
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def on_iteration_callback(iteration: Iteration):
        status_text.text(f"Iteration {iteration.version} completed: Score {iteration.match_report.score}/100")
        progress_bar.progress(iteration.version / max_iterations)

    with st.spinner("Executing Pipeline..."):
        result = run_pipeline(
            jd_text=jd_text,
            cv_path=Path(cv_path),
            max_iterations=max_iterations,
            pass_threshold=pass_threshold,
            on_iteration=on_iteration_callback
        )
        
    progress_bar.empty()
    status_text.empty()
    
    st.success(f"Pipeline finished after {result.total_iterations} iteration(s)!")
    
    # Display results
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 JD Profile")
        st.json(result.jd_profile.model_dump())
        
        st.subheader("🎯 Selection Plan")
        st.json(result.selection_plan.model_dump())
        
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
            
        if result.final_report and result.total_iterations > 1:
            st.subheader("🔍 Final Critic Report")
            st.json(result.final_report.model_dump())
            
    with col2:
        if result.final_resume:
            st.subheader(f"✨ Final Resume (v{result.total_iterations})")
            st.markdown(result.final_resume)
            
            st.download_button(
                "Download Resume (Markdown)",
                data=result.final_resume,
                file_name="tailored_resume.md",
                mime="text/markdown"
            )
        elif result.resume_v1:
             # In case it failed later or only had 1 iteration
             st.subheader("📝 Resume v1")
             st.markdown(result.resume_v1)
        else:
             st.warning("No resume generated.")
