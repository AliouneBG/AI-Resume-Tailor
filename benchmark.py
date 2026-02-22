import time
import json
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from src.pipeline import run_pipeline, load_master_cv
from src.models import MasterCV

console = Console()

def run_benchmark():
    jd_text = """Snowflake is about empowering enterprises to achieve their full potential. Our Solution Engineering organization is seeking an AI/ML specialist... Apply your multi-cloud data architecture expertise while presenting Snowflake technology and vision. 5+ years of data engineering experience, 3+ years experience working with AI/ML technologies. Hands on Development experience with SQL, Python, Pandas, Spark."""
    cv_path = Path("data/master_cv.json")
    
    scenarios = [
        {
            "name": "Baseline (Full Context)",
            "model": "gemini-flash-latest",
            "dynamic": False,
            "pruned": False,
            "rubric": False
        },
        {
            "name": "Optimized (Dynamic/Pruned)",
            "model": "gemini-flash-latest",
            "dynamic": True,
            "pruned": True,
            "rubric": True
        }
    ]

    results = []
    
    for s in scenarios:
        console.print(f"\n[bold cyan]Running {s['name']}...[/bold cyan]")
        os.environ["MODEL_NAME"] = s['model']
        
        start_time = time.time()
        try:
            result = run_pipeline(
                jd_text,
                cv_path=cv_path,
                max_iterations=3,
                use_dynamic_iteration=s['dynamic'],
                use_pruned_context=s['pruned'],
                use_rubric_optimization=s['rubric']
            )
            duration = time.time() - start_time
            
            results.append({
                "Scenario": s['name'],
                "Duration (s)": f"{duration:.1f}",
                "Iterations": result.total_iterations,
                "Score": f"{result.final_report.score:.1f}",
                "Status": "✅"
            })
        except Exception as e:
            console.print(f"[red]Error in {s['name']}: {e}[/red]")
            results.append({
                "Scenario": s['name'],
                "Duration (s)": "N/A",
                "Iterations": "N/A",
                "Score": "N/A",
                "Status": "❌"
            })

    # Display results
    table = Table(title="🚀 Resume Tailor Performance Benchmark")
    table.add_column("Scenario", style="cyan")
    table.add_column("Duration (s)", justify="right")
    table.add_column("Iterations", justify="right")
    table.add_column("Final Score", justify="right")
    table.add_column("Status", justify="center")

    for r in results:
        table.add_row(r["Scenario"], r["Duration (s)"], str(r["Iterations"]), r["Score"], r["Status"])

    console.print(table)

if __name__ == "__main__":
    run_benchmark()
