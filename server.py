"""FastAPI server — wraps the ADK Resume Tailor pipeline with a REST API.

Endpoints:
  POST /api/tailor  — accepts JD text, runs the pipeline, returns results
  GET  /            — serves the static frontend
"""

from __future__ import annotations

import asyncio
import json
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from resume_tailor_agent.agent import root_agent

# ── App setup ──────────────────────────────────────────────────
app = FastAPI(title="Resume Tailor", version="1.0.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── ADK Runner ─────────────────────────────────────────────────
APP_NAME = "resume_tailor"
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)


# ── Routes ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main HTML page."""
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text())


@app.post("/api/tailor")
async def tailor_resume(request: Request):
    """Run the full ADK pipeline on a job description.

    Request body:
        { "jd_text": "..." }

    Returns:
        JSON with pipeline results (jd_profile, selection_plan, resume, etc.)
    """
    body = await request.json()
    jd_text = body.get("jd_text", "").strip()

    if not jd_text:
        return JSONResponse(
            status_code=400,
            content={"error": "jd_text is required"},
        )

    # Create a unique session for this run
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    session_id = f"session_{uuid.uuid4().hex[:8]}"

    # Create session with JD text pre-loaded into state
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={"jd_text": jd_text},
    )

    try:
        # Run the agent pipeline
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=f"Tailor a resume for this job description:\n\n{jd_text}")],
        )

        final_response_text = ""
        all_events = []

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_message,
        ):
            all_events.append({
                "author": event.author,
                "is_final": event.is_final_response(),
            })

            # Collect text from the final response
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        if event.is_final_response():
                            final_response_text += part.text

        # Pull results from session state
        updated_session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        state = updated_session.state if updated_session else {}

        # Extract structured outputs from state
        result = {
            "status": "success",
            "jd_profile": _safe_json_parse(state.get("jd_profile", "{}")),
            "selection_plan": _safe_json_parse(state.get("selection_plan", "{}")),
            "current_resume": state.get("current_resume", final_response_text),
            "criticism": state.get("criticism", ""),
            "events_count": len(all_events),
        }

        return JSONResponse(content=result)

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "traceback": traceback.format_exc()},
        )


def _safe_json_parse(value):
    """Try to parse a JSON string, return as-is if already a dict or fails."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


# ── Run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
