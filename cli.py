"""CLI entry point — beautiful terminal UI for the Resume Tailor pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.json import JSON
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

# Ensure project root is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models import Iteration, MasterCV
from src.pipeline import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_PASS_THRESHOLD,
    load_master_cv,
    run_pipeline,
)
from src.job_search import run_search

app = typer.Typer(
    name="resume-tailor",
    help="🎯 Job Resume Tailor — Self-Improving Agent",
    add_completion=False,
)
console = Console()


def _on_iteration(iteration: Iteration) -> None:
    """Live callback — prints each iteration as it completes."""
    version = iteration.version
    score = iteration.match_report.score
    coverage = iteration.match_report.keyword_coverage
    passed = "✅ PASSED" if iteration.passed else "🔄 needs improvement"
    n_fixes = len(iteration.match_report.fixes)
    n_risks = len(iteration.match_report.risk_flags)

    console.print(f"  [dim]├─[/dim] v{version}: score={score}/100  coverage={coverage:.0%}  fixes={n_fixes}  risks={n_risks}  {passed}")


@app.command()
def tailor(
    jd: str = typer.Option(
        ...,
        help="Path to a JD text file, or raw JD text in quotes.",
    ),
    cv: str = typer.Option(
        "data/master_cv.json",
        help="Path to master_cv.json.",
    ),
    output: str = typer.Option(
        None,
        help="Optional path to save the final resume Markdown.",
    ),
    max_iter: int = typer.Option(
        DEFAULT_MAX_ITERATIONS,
        help="Maximum self-improvement iterations.",
    ),
    threshold: float = typer.Option(
        DEFAULT_PASS_THRESHOLD,
        help="Score threshold to stop iterating (0–100).",
    ),
) -> None:
    """Run the full tailor pipeline with self-improvement loop."""
    # ── Read JD ───────────────────────────────────────────────
    jd_path = Path(jd)
    if jd_path.exists():
        jd_text = jd_path.read_text()
    else:
        jd_text = jd

    # ── Header ────────────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]🎯 Resume Tailor — Self-Improving Agent[/bold cyan]")
    console.print(f"  [dim]Max iterations: {max_iter} | Pass threshold: {threshold}/100[/dim]")
    console.print()

    # ── Run pipeline ──────────────────────────────────────────
    console.print("[bold]⚡ Running pipeline...[/bold]")
    console.print(f"  [dim]├─[/dim] Extracting JD profile...")
    console.print(f"  [dim]├─[/dim] Matching & selecting content...")
    console.print(f"  [dim]├─[/dim] Starting self-improvement loop...")

    result = run_pipeline(
        jd_text,
        cv_path=Path(cv),
        max_iterations=max_iter,
        pass_threshold=threshold,
        on_iteration=_on_iteration,
    )

    console.print(f"  [dim]└─[/dim] [green]Done![/green] ({result.total_iterations} iterations)")
    console.print()

    # ── 1. JD Profile ─────────────────────────────────────────
    console.print(Panel(
        JSON(result.jd_profile.model_dump_json(indent=2)),
        title="[bold green]📋 JD Profile[/bold green]",
        border_style="green",
    ))
    console.print()

    # ── 2. Selection Plan ─────────────────────────────────────
    console.print(Panel(
        JSON(result.selection_plan.model_dump_json(indent=2)),
        title="[bold yellow]🎯 Selection Plan[/bold yellow]",
        border_style="yellow",
    ))
    console.print()

    # ── 3. Iteration History ──────────────────────────────────
    table = Table(title="📊 Self-Improvement Progress", border_style="cyan")
    table.add_column("Version", style="bold", justify="center")
    table.add_column("Score", justify="center")
    table.add_column("Coverage", justify="center")
    table.add_column("Fixes", justify="center")
    table.add_column("Risk Flags", justify="center")
    table.add_column("Status", justify="center")

    for it in result.iterations:
        delta = ""
        if it.version > 1:
            prev = result.iterations[it.version - 2].match_report.score
            diff = it.match_report.score - prev
            color = "green" if diff > 0 else ("red" if diff < 0 else "dim")
            delta = f" [{color}]({diff:+.1f})[/{color}]"

        table.add_row(
            f"v{it.version}",
            f"{it.match_report.score}/100{delta}",
            f"{it.match_report.keyword_coverage:.0%}",
            str(len(it.match_report.fixes)),
            str(len(it.match_report.risk_flags)),
            "[green]✅ PASS[/green]" if it.passed else "[yellow]🔄[/yellow]",
        )

    console.print(table)
    console.print()

    # ── 4. First Resume (v1) ──────────────────────────────────
    console.print(Panel(
        Markdown(result.resume_v1),
        title="[bold blue]📝 Resume v1 (Initial)[/bold blue]",
        border_style="blue",
    ))
    console.print()

    # ── 5. First Critic Report ────────────────────────────────
    if result.match_report_v1:
        console.print(Panel(
            JSON(result.match_report_v1.model_dump_json(indent=2)),
            title=f"[bold red]🔍 Critic Report v1 — Score: {result.match_report_v1.score}/100[/bold red]",
            border_style="red",
        ))
        console.print()

    # ── 6. Final Resume ───────────────────────────────────────
    if result.total_iterations > 1:
        console.print(Panel(
            Markdown(result.final_resume),
            title=f"[bold magenta]✨ Final Resume (v{result.total_iterations})[/bold magenta]",
            border_style="magenta",
        ))
        console.print()

    # ── 7. Final Critic Report ────────────────────────────────
    if result.final_report and result.total_iterations > 1:
        console.print(Panel(
            JSON(result.final_report.model_dump_json(indent=2)),
            title=f"[bold green]🔍 Final Critic Report — Score: {result.final_report.score}/100[/bold green]",
            border_style="green",
        ))
        console.print()

    # ── Summary ───────────────────────────────────────────────
    console.rule("[bold cyan]Summary[/bold cyan]")
    console.print(f"  [green]✓[/green] JD Profile: {len(result.jd_profile.must_have_skills)} must-have, {len(result.jd_profile.nice_to_have_skills)} nice-to-have skills")
    console.print(f"  [green]✓[/green] Selected: {len(result.selection_plan.selected_experience_ids)} experiences, {len(result.selection_plan.selected_project_ids)} projects")
    console.print(f"  [green]✓[/green] Self-improvement: {result.total_iterations} iteration(s)")

    if result.match_report_v1:
        console.print(f"  [green]✓[/green] v1 score: {result.match_report_v1.score}/100")
    if result.final_report and result.total_iterations > 1:
        console.print(f"  [green]✓[/green] Final score: {result.final_report.score}/100")
        imp = result.score_improvement
        color = "green" if imp > 0 else "red"
        console.print(f"  [{color}]{'✓' if imp > 0 else '✗'}[/{color}] Total improvement: {imp:+.1f} points")

    if result.iterations[-1].passed:
        console.print(f"\n  [bold green]🎉 Resume PASSED quality threshold ({threshold}/100)[/bold green]")
    else:
        console.print(f"\n  [bold yellow]⚠️  Best version returned (did not reach {threshold}/100 threshold)[/bold yellow]")

    console.print()

    # ── Save output ───────────────────────────────────────────
    if output:
        Path(output).write_text(result.final_resume)
        console.print(f"  [green]💾 Saved final resume to {output}[/green]")
        console.print()


@app.command()
def search(
    query: str = typer.Argument(
        ...,
        help='Natural language job search query, e.g. "solutions engineer NYC"',
    ),
    output_dir: str = typer.Option(
        "./jobs",
        "-o",
        "--output-dir",
        help="Output directory for YAML files.",
    ),
    max_pages: int = typer.Option(
        1,
        "--max-pages",
        help="SerpAPI pages to fetch, 10 results/page.",
    ),
    location: str = typer.Option(
        "",
        "--location",
        help='Location filter, e.g. "New York, NY".',
    ),
    no_fetch: bool = typer.Option(
        False,
        "--no-fetch",
        help="Skip page fetching, use SerpAPI snippets only.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite existing YAML files.",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Detailed progress output.",
    ),
) -> None:
    """Search for jobs via Google Jobs and output structured YAML files."""
    console.print()
    console.rule("[bold cyan]Job Search[/bold cyan]")
    console.print()

    run_search(
        query=query,
        output_dir=Path(output_dir),
        max_pages=max_pages,
        location=location,
        no_fetch=no_fetch,
        overwrite=overwrite,
        verbose=verbose,
        console=console,
    )


if __name__ == "__main__":
    app()
