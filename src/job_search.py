"""Job search pipeline — SerpAPI search, page fetch, Gemini parsing, YAML output.

Ported from v1's job_search package into a single module.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
import serpapi
import yaml
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from rich.console import Console
from rich.progress import track

from . import config

# ── Models ────────────────────────────────────────────────────


class GeminiParsedJob(BaseModel):
    """Schema for Gemini structured extraction from a job posting page."""

    description: str = Field(
        description="Full plain-text job description including all requirements, responsibilities, and qualifications"
    )
    apply_url: Optional[str] = Field(
        None, description="Direct URL to apply for this job (the Apply button link)"
    )
    salary_range: Optional[str] = Field(
        None,
        description="Salary or compensation range if explicitly stated, e.g. '$120k-$160k per year'",
    )


class JobPosting(BaseModel):
    """Final output model, serialized to YAML."""

    schema_version: str = "1"
    fetched_at: str  # ISO 8601

    title: str
    company: str
    location: str
    remote: bool = False

    description: str
    description_source: str  # "gemini" | "serpapi"
    serpapi_description: str = ""  # always stored as fallback

    source_url: str
    apply_url: Optional[str] = None

    via: str
    posted_at: Optional[str] = None
    schedule_type: Optional[str] = None
    salary_range: Optional[str] = None

    qualifications: list[str] = []
    responsibilities: list[str] = []
    benefits: list[str] = []

    serpapi_job_id: str
    full_description_fetched: bool
    fetch_error: Optional[str] = None
    gemini_parsed: bool = False


# ── Gemini parser ─────────────────────────────────────────────

STRIP_TAGS = ["script", "style", "nav", "header", "footer", "iframe", "noscript"]
MAX_TEXT_CHARS = 80_000  # ~20k tokens


class GeminiParser:
    def __init__(self, project: str, location: str, model: str = "gemini-2.0-flash"):
        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.model = model
        self._schema = GeminiParsedJob.model_json_schema()

    def _clean_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(STRIP_TAGS):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line for line in text.splitlines() if line.strip()]
        return "\n".join(lines)[:MAX_TEXT_CHARS]

    def parse(self, html: str, job_title: str, company: str) -> Optional[GeminiParsedJob]:
        cleaned = self._clean_html(html)
        prompt = f"""You are extracting structured data from a job posting page.

Job: {job_title} at {company}

Page content:
---
{cleaned}
---

Extract:
1. The COMPLETE job description text (all requirements, responsibilities, qualifications, benefits — include everything)
2. The direct URL to apply for this job (the "Apply" button link, not a generic careers page)
3. The salary/compensation range if explicitly stated

Return JSON matching the schema exactly."""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=self._schema,
                    temperature=0.1,
                ),
            )
            return GeminiParsedJob.model_validate_json(response.text)
        except Exception:
            return None


# ── Constants ─────────────────────────────────────────────────

GATED_DOMAINS = {"linkedin.com", "www.linkedin.com"}
BOT_DETECTION_SIGNALS = [
    "sign in",
    "log in to",
    "please verify",
    "are you a robot",
    "captcha",
    "access denied",
]
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CACHE_DIR = Path(__file__).resolve().parent.parent / ".serpapi_cache"


# ── Helpers ───────────────────────────────────────────────────


def slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40].strip("-")


def _cache_key(params: dict) -> str:
    """Hash query params + today's date to get a cache key."""
    key_data = {**params, "_date": date.today().isoformat()}
    raw = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fetch_page(url: str) -> tuple[str | None, str | None]:
    """Fetch a job posting page. Returns (html, error_message)."""
    domain = urlparse(url).netloc.lower()
    if any(gated in domain for gated in GATED_DOMAINS):
        return None, f"gated:{domain}"

    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        preview = resp.text[:2000].lower()
        for signal in BOT_DETECTION_SIGNALS:
            if signal in preview:
                return None, "bot_detection"
        return resp.text, None
    except requests.Timeout:
        return None, "timeout"
    except requests.HTTPError as e:
        return None, f"http_{e.response.status_code}"
    except requests.RequestException as e:
        return None, str(e)


def search_jobs(api_key: str, query: str, location: str, max_pages: int, console: Console) -> list[dict]:
    """Search Google Jobs via SerpAPI with disk caching."""
    client = serpapi.Client(api_key=api_key)
    params = {"engine": "google_jobs", "q": query}
    if location:
        params["location"] = location

    all_jobs: list[dict] = []
    for page in range(max_pages):
        page_params = {**params}
        cache_file = CACHE_DIR / f"{_cache_key(page_params)}.json"

        if cache_file.exists():
            console.print(f"  [dim]Using cached results (page {page + 1})[/]")
            results = json.loads(cache_file.read_text())
        else:
            results = client.search(page_params)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(dict(results), default=str))

        jobs = results.get("jobs_results", [])
        all_jobs.extend(jobs)
        next_token = results.get("serpapi_pagination", {}).get("next_page_token")
        if not next_token or not jobs:
            break
        params["next_page_token"] = next_token

    return all_jobs


def build_posting(
    raw: dict,
    html: str | None,
    fetch_error: str | None,
    parsed: GeminiParsedJob | None,
) -> JobPosting:
    """Merge raw SerpAPI result + parsed page into a JobPosting."""
    detected = raw.get("detected_extensions", {})
    highlights = {h["title"]: h.get("items", []) for h in raw.get("job_highlights", [])}
    apply_options = raw.get("apply_options", [])
    source_url = apply_options[0]["link"] if apply_options else ""

    serpapi_description = raw.get("description", "")
    apply_url = source_url
    salary = detected.get("salary")
    gemini_parsed = False

    # Always prefer SerpAPI description; use Gemini only for apply_url/salary
    description = serpapi_description
    description_source = "serpapi"

    if parsed:
        gemini_parsed = True
        if parsed.apply_url:
            apply_url = parsed.apply_url
        if parsed.salary_range:
            salary = parsed.salary_range

    return JobPosting(
        fetched_at=datetime.now(timezone.utc).isoformat(),
        title=raw["title"],
        company=raw["company_name"],
        location=raw.get("location", ""),
        remote=detected.get("work_from_home", False),
        description=description,
        description_source=description_source,
        serpapi_description=serpapi_description,
        source_url=source_url,
        apply_url=apply_url,
        via=raw.get("via", ""),
        posted_at=detected.get("posted_at"),
        schedule_type=detected.get("schedule_type"),
        salary_range=salary,
        qualifications=highlights.get("Qualifications", []),
        responsibilities=highlights.get("Responsibilities", []),
        benefits=highlights.get("Benefits", []),
        serpapi_job_id=raw.get("job_id", ""),
        full_description_fetched=html is not None,
        fetch_error=fetch_error,
        gemini_parsed=gemini_parsed,
    )


def write_job(job: JobPosting, output_dir: Path, overwrite: bool) -> Path:
    """Write a JobPosting to a YAML file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    job_id_short = slug(job.serpapi_job_id)[:8]
    filename = f"{slug(job.company)}-{slug(job.title)}-{job_id_short}.yaml"
    filepath = output_dir / filename

    if filepath.exists() and not overwrite:
        return filepath

    data = job.model_dump(exclude_none=False)
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return filepath


# ── Orchestrator ──────────────────────────────────────────────


def run_search(
    query: str,
    output_dir: Path,
    max_pages: int = 1,
    location: str = "",
    no_fetch: bool = False,
    overwrite: bool = False,
    verbose: bool = False,
    console: Console | None = None,
) -> None:
    """Top-level search pipeline: search -> fetch -> parse -> write YAML."""
    if console is None:
        console = Console()

    serpapi_key = config.SERPAPI_KEY
    gcp_project = config.GOOGLE_CLOUD_PROJECT
    gcp_location = config.GOOGLE_CLOUD_LOCATION
    gemini_model = config.GEMINI_MODEL

    missing = []
    if not serpapi_key:
        missing.append("SERPAPI_KEY")
    if not gcp_project and not no_fetch:
        missing.append("GOOGLE_CLOUD_PROJECT")
    if missing:
        console.print(f"[red]Missing required environment variables: {', '.join(missing)}[/]")
        console.print("Set them in your .env file or shell environment.")
        sys.exit(1)

    gemini = None if no_fetch else GeminiParser(gcp_project, gcp_location, gemini_model)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        console.print(f"[red]Cannot create output directory {output_dir}: {e}[/]")
        sys.exit(1)

    console.print(f"[bold]Searching:[/] {query}")
    raw_jobs = search_jobs(serpapi_key, query, location, max_pages, console)
    console.print(f"Found [bold]{len(raw_jobs)}[/] job listings\n")

    written = 0
    skipped = 0

    for raw in track(raw_jobs, description="Processing jobs..."):
        title = raw.get("title", "Unknown")
        company = raw.get("company_name", "Unknown")

        html = None
        fetch_error = None
        parsed = None

        if not no_fetch:
            apply_options = raw.get("apply_options", [])
            if apply_options:
                url = apply_options[0]["link"]
                html, fetch_error = fetch_page(url)
                if html and gemini:
                    parsed = gemini.parse(html, title, company)
                time.sleep(1.0)
            else:
                fetch_error = "no_apply_url"

        job = build_posting(raw, html, fetch_error, parsed)
        path = write_job(job, output_dir, overwrite)

        if path.exists() and not overwrite and written == 0 and skipped == 0:
            skipped += 1
        else:
            written += 1

        if verbose:
            status_parts = []
            if job.full_description_fetched:
                status_parts.append("[green]fetched[/]")
            else:
                status_parts.append(f"[yellow]snippet[/] ({job.fetch_error})")
            if job.gemini_parsed:
                status_parts.append("[green]parsed[/]")
            status = " ".join(status_parts)
            console.print(f"  {status} [bold]{title}[/] @ {company} -> {path.name}")

    console.print(f"\n[bold green]Done.[/] {written} jobs written to [bold]{output_dir}[/]")
