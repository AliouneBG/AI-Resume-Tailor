"""CLI entry point — beautiful terminal UI for the Resume Tailor pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.json import JSON
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Ensure project root is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models import MasterCV
from src.pipeline import load_master_cv, run_pipeline

app = typer.Typer(
    name="resume-tailor",
    help="🎯 Job Resume Tailor — Self-Improving Agent",
    add_completion=False,
)
console = Console()


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
) -> None:
    """Run the full tailor pipeline: Extract → Match → Write → Critique → Improve."""
    # ── Read JD ───────────────────────────────────────────────
    jd_path = Path(jd)
    if jd_path.exists():
        jd_text = jd_path.read_text()
    else:
        jd_text = jd

    # ── Run pipeline with progress ────────────────────────────
    console.print()
    console.rule("[bold cyan]🎯 Resume Tailor — Self-Improving Agent[/bold cyan]")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running pipeline...", total=None)

        progress.update(task, description="[cyan]Step 1/6:[/] Extracting JD profile...")
        # We run the full pipeline and display results after
        result = run_pipeline(jd_text, cv_path=Path(cv))

    # ── Display results ───────────────────────────────────────
    console.print()

    # 1. JD Profile
    console.print(Panel(
        JSON(result.jd_profile.model_dump_json(indent=2)),
        title="[bold green]📋 JD Profile[/bold green]",
        border_style="green",
    ))
    console.print()

    # 2. Selection Plan
    console.print(Panel(
        JSON(result.selection_plan.model_dump_json(indent=2)),
        title="[bold yellow]🎯 Selection Plan[/bold yellow]",
        border_style="yellow",
    ))
    console.print()

    # 3. Resume v1
    console.print(Panel(
        Markdown(result.resume_v1),
        title="[bold blue]📝 Resume v1 (Initial)[/bold blue]",
        border_style="blue",
    ))
    console.print()

    # 4. Match Report v1
    score_v1 = result.match_report_v1.score
    coverage_v1 = result.match_report_v1.keyword_coverage
    console.print(Panel(
        JSON(result.match_report_v1.model_dump_json(indent=2)),
        title=f"[bold red]🔍 Critic Report v1 — Score: {score_v1}/100 | Coverage: {coverage_v1:.0%}[/bold red]",
        border_style="red",
    ))
    console.print()

    # 5. Resume v2 (improved)
    console.print(Panel(
        Markdown(result.resume_v2),
        title="[bold magenta]✨ Resume v2 (Self-Improved)[/bold magenta]",
        border_style="magenta",
    ))
    console.print()

    # 6. Match Report v2 (if available)
    if result.match_report_v2:
        score_v2 = result.match_report_v2.score
        coverage_v2 = result.match_report_v2.keyword_coverage
        improvement = score_v2 - score_v1
        color = "green" if improvement > 0 else "red"
        console.print(Panel(
            JSON(result.match_report_v2.model_dump_json(indent=2)),
            title=(
                f"[bold green]🔍 Critic Report v2 — Score: {score_v2}/100 | Coverage: {coverage_v2:.0%} "
                f"| Δ [{color}]{improvement:+.1f}[/{color}][/bold green]"
            ),
            border_style="green",
        ))
        console.print()

    # ── Summary ───────────────────────────────────────────────
    console.rule("[bold cyan]Summary[/bold cyan]")
    console.print(f"  [green]✓[/green] JD Profile extracted ({len(result.jd_profile.must_have_skills)} must-have, {len(result.jd_profile.nice_to_have_skills)} nice-to-have)")
    console.print(f"  [green]✓[/green] Selected {len(result.selection_plan.selected_experience_ids)} experiences, {len(result.selection_plan.selected_project_ids)} projects")
    console.print(f"  [green]✓[/green] Resume v1 score: {score_v1}/100 ({coverage_v1:.0%} keyword coverage)")
    if result.match_report_v2:
        console.print(f"  [green]✓[/green] Resume v2 score: {score_v2}/100 ({coverage_v2:.0%} keyword coverage)")
        console.print(f"  [{'green' if improvement > 0 else 'red'}]{'✓' if improvement > 0 else '✗'}[/] Improvement: {improvement:+.1f} points")
    console.print()

    # ── Save output ───────────────────────────────────────────
    if output:
        Path(output).write_text(result.resume_v2)
        console.print(f"  [green]💾 Saved final resume to {output}[/green]")
        console.print()


if __name__ == "__main__":
    app()
