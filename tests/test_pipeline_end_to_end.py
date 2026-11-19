"""End-to-end tests on synthetic data: no network needed.

Builds bronze Parquet from fake Open-Meteo payloads, runs the warehouse build,
quality checks, catalog governance check and lineage, and (when a PostgreSQL
DSN is available) the publish step.
"""

from __future__ import annotations

import os
import shutil
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from data_pipeline.catalog import build_catalog, compare, lineage_from_sql_dir, load_catalog
from data_pipeline.config import PipelineConfig, default_locations
from data_pipeline.extract import payload_to_bronze_frame, write_bronze
from data_pipeline.quality import record_results, run_quality_checks
from data_pipeline.warehouse import build_warehouse

REPO_ROOT = Path(__file__).resolve().parents[1]
START, END = date(2026, 1, 1), date(2026, 1, 2)


def fake_payload(hours: int = 48, offset: float = 0.0) -> dict:
    times = [f"2026-01-{1 + h // 24:02d}T{h % 24:02d}:00" for h in range(hours)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [20 + offset + (h % 24) / 4 for h in range(hours)],
            "relative_humidity_2m": [60 + (h % 10) for h in range(hours)],
            "precipitation": [0.0 if h % 6 else 1.5 for h in range(hours)],
            "wind_speed_10m": [8.0 + (h % 5) for h in range(hours)],
        }
    }


@pytest.fixture()
def built(tmp_path: Path) -> PipelineConfig:
    shutil.copytree(REPO_ROOT / "sql", tmp_path / "sql")
    shutil.copytree(REPO_ROOT / "catalog", tmp_path / "catalog")
    config = PipelineConfig(project_root=tmp_path, locations=default_locations()[:3])
    frames = [
        payload_to_bronze_frame(loc, fake_payload(offset=i))
        for i, loc in enumerate(config.locations)
    ]
    write_bronze(config.bronze_dir, pd.concat(frames), START, END)
    build_warehouse(config)
    return config


def test_warehouse_builds_expected_marts(built: PipelineConfig) -> None:
    con = duckdb.connect(str(built.warehouse_path), read_only=True)
    try:
        assert con.execute("select count(*) from silver.dim_location").fetchone()[0] == 3
        assert (
            con.execute("select count(*) from silver.fact_hourly_weather").fetchone()[0] == 3 * 48
        )
        daily = con.execute(
            "select count(*), min(hourly_observations) from gold.mart_daily_weather"
        ).fetchone()
        assert daily == (6, 24)  # 3 cities x 2 complete days
    finally:
        con.close()


def test_quality_checks_pass_and_are_recorded(built: PipelineConfig) -> None:
    results = run_quality_checks(built)
    assert results and all(r.passed for r in results)
    run_id = record_results(built, results)
    con = duckdb.connect(str(built.warehouse_path), read_only=True)
    try:
        stored = con.execute(
            "select count(*), bool_and(passed) from ops.dq_results where run_id = ?", [run_id]
        ).fetchone()
    finally:
        con.close()
    assert stored == (len(results), True)


def test_quality_check_catches_bad_data(tmp_path: Path) -> None:
    shutil.copytree(REPO_ROOT / "sql", tmp_path / "sql")
    config = PipelineConfig(project_root=tmp_path, locations=default_locations()[:1])
    payload = fake_payload()
    payload["hourly"]["relative_humidity_2m"][0] = 140  # impossible value
    write_bronze(
        config.bronze_dir, payload_to_bronze_frame(config.locations[0], payload), START, END
    )
    build_warehouse(config)
    failed = {r.check_name for r in run_quality_checks(config) if not r.passed}
    assert failed == {"humidity_reasonable_range"}


def test_catalog_documents_every_column(built: PipelineConfig) -> None:
    gaps = build_catalog(built)
    assert gaps.ok, gaps.lines()
    doc = (built.project_root / "docs" / "data_catalog.md").read_text(encoding="utf-8")
    assert "```mermaid" in doc and "## Business glossary" in doc
    assert "| `temperature_anomaly_c` | DOUBLE |" in doc


def test_catalog_check_flags_undocumented_and_stale_columns() -> None:
    catalog = {"tables": {"gold.t": {"description": "x", "columns": {"a": {"description": "A"}}}}}
    gaps = compare(catalog, {"gold.t": {"b": "INTEGER"}, "gold.u": {"c": "INTEGER"}})
    assert gaps.undocumented_columns == ["gold.t.b"]
    assert gaps.stale_columns == ["gold.t.a"]
    assert gaps.undocumented_tables == ["gold.u"]
    assert not gaps.ok


def test_lineage_is_derived_from_sql() -> None:
    edges = set(lineage_from_sql_dir(REPO_ROOT / "sql"))
    assert ("silver.bronze_hourly_weather", "silver.fact_hourly_weather") in edges
    assert ("silver.dim_location", "silver.fact_hourly_weather") in edges
    assert ("gold.mart_daily_weather", "gold.mart_city_anomalies") in edges
    assert not any(target == "daily" or source == "daily" for source, target in edges)  # CTEs


def test_repository_catalog_has_glossary_and_owners() -> None:
    catalog = load_catalog(REPO_ROOT / "catalog" / "catalog.yml")
    assert catalog["owner"] and len(catalog["glossary"]) >= 5


@pytest.mark.skipif(not os.environ.get("TEST_PG_DSN"), reason="set TEST_PG_DSN to run")
def test_publish_to_postgres(built: PipelineConfig) -> None:
    import psycopg

    from data_pipeline.publish import publish

    dsn = os.environ["TEST_PG_DSN"]
    results = {r.table: r.rows for r in publish(built, dsn)}
    assert results == {
        "analytics.dim_location": 3,
        "analytics.mart_daily_weather": 6,
        "analytics.mart_city_anomalies": 6,
    }
    publish(built, dsn)  # idempotent: re-publishing replaces, never duplicates
    with psycopg.connect(dsn) as pg:
        assert pg.execute("select count(*) from analytics.mart_daily_weather").fetchone()[0] == 6
        comment = pg.execute(
            "select obj_description('analytics.mart_daily_weather'::regclass)"
        ).fetchone()[0]
        assert "Daily weather summary" in comment
        with pytest.raises(psycopg.errors.UniqueViolation):  # primary key enforces the grain
            pg.execute(
                "insert into analytics.mart_daily_weather "
                "select * from analytics.mart_daily_weather limit 1"
            )
