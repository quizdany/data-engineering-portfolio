from __future__ import annotations

import shutil
from pathlib import Path

import typer

from data_pipeline.catalog import build_catalog
from data_pipeline.config import build_config, date_window
from data_pipeline.extract import extract_to_bronze
from data_pipeline.publish import publish as publish_to_postgres
from data_pipeline.quality import record_results, run_quality_checks
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
    run_id = record_results(config, results)
    typer.echo(f"Recorded run {run_id} in ops.dq_results")
    if not all(result.passed for result in results):
        raise typer.Exit(code=1)


@app.command()
def catalog(
    check: bool = typer.Option(False, "--check", help="Only verify the catalog; write nothing."),
) -> None:
    """Regenerate docs/data_catalog.md, or fail if the catalog and warehouse disagree."""
    config = build_config(Path.cwd())
    gaps = build_catalog(config, check_only=check)
    for line in gaps.lines():
        typer.echo(f"GAP {line}")
    if not gaps.ok:
        raise typer.Exit(code=1)
    typer.echo("Catalog matches the warehouse." + ("" if check else " Wrote docs/data_catalog.md"))


@app.command()
def publish(
    dsn: str = typer.Option(None, envvar="PIPELINE_PG_DSN", help="PostgreSQL connection string."),
) -> None:
    """Publish gold marts and the location dimension to PostgreSQL (schema: analytics)."""
    config = build_config(Path.cwd())
    for result in publish_to_postgres(config, dsn):
        typer.echo(f"Published {result.table}: {result.rows} rows")


@app.command()
def clean() -> None:
    config = build_config(Path.cwd())
    if config.data_dir.exists():
        shutil.rmtree(config.data_dir)
    typer.echo(f"Removed {config.data_dir}")


if __name__ == "__main__":
    app()
