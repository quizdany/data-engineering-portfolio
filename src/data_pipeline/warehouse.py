from __future__ import annotations

from pathlib import Path

import duckdb

from data_pipeline.config import PipelineConfig


def _read_sql(project_root: Path, name: str) -> str:
    return (project_root / "sql" / name).read_text(encoding="utf-8")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_warehouse(config: PipelineConfig) -> None:
    config.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(config.warehouse_path))
    try:
        bronze_glob = str(config.bronze_dir / "**" / "*.parquet").replace("\\", "/")
        con.execute("create schema if not exists silver")
        con.execute("create schema if not exists gold")
        con.execute("create schema if not exists ops")
        con.execute(
            """
            create table if not exists ops.dq_results (
                run_id varchar,
                check_name varchar,
                passed boolean,
                observed_value double,
                expectation varchar,
                checked_at_utc timestamp
            )
            """
        )
        con.execute(
            f"""
            create or replace view silver.bronze_hourly_weather as
            select * from read_parquet({_sql_literal(bronze_glob)})
            """
        )
        for sql_file in [
            "01_dim_location.sql",
            "02_fact_hourly_weather.sql",
            "03_mart_daily_weather.sql",
            "04_mart_city_anomalies.sql",
        ]:
            con.execute(_read_sql(config.project_root, sql_file))
        export_marts(con, config.export_dir)
    finally:
        con.close()


def export_marts(con: duckdb.DuckDBPyConnection, export_dir: Path) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)
    con.execute(
        "copy gold.mart_daily_weather to ? (header, delimiter ',')",
        [str(export_dir / "mart_daily_weather.csv")],
    )
    con.execute(
        "copy gold.mart_city_anomalies to ? (header, delimiter ',')",
        [str(export_dir / "mart_city_anomalies.csv")],
    )
