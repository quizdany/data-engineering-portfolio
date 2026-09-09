from __future__ import annotations

import shutil
from pathlib import Path

import typer

from data_pipeline.config import build_config, date_window
from data_pipeline.extract import extract_to_bronze
from data_pipeline.quality import run_quality_checks
from data_pipeline.warehouse import build_warehouse

app = typer.Typer(help="Open-Meteo weather lakehouse pipeline.")


@app.command()
def run(days: int = typer.Option(14, min=1, max=365, help="Historical days to ingest.")) -> None:
    config = build_config(Path.cwd())
    start_date, end_date = date_window(days)
    bronze_path = extract_to_bronze(config, start_date, end_date)
    build_warehouse(config)
    typer.echo(f"Bronze parquet: {bronze_path}")
    typer.echo(f"DuckDB warehouse: {config.warehouse_path}")
    typer.echo(f"Exports: {config.export_dir}")


@app.command()
def quality() -> None:
    config = build_config(Path.cwd())
    results = run_quality_checks(config)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        message = (
            f"{status} {result.check_name}: observed {result.observed_value}, "
            f"expected {result.expectation}"
        )
        typer.echo(message)
    if not all(result.passed for result in results):
        raise typer.Exit(code=1)


@app.command()
def clean() -> None:
    config = build_config(Path.cwd())
    if config.data_dir.exists():
        shutil.rmtree(config.data_dir)
    typer.echo(f"Removed {config.data_dir}")


if __name__ == "__main__":
    app()
