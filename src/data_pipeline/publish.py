"""Load gold marts from DuckDB into PostgreSQL (one transaction, row counts checked)."""

from __future__ import annotations

import os
from dataclasses import dataclass

import duckdb
import psycopg
from psycopg import sql

from data_pipeline.catalog import load_catalog
from data_pipeline.config import PipelineConfig

DEFAULT_DSN = "postgresql://pipeline:pipeline@localhost:5432/metadata"  # docker-compose
TARGET_SCHEMA = "analytics"

# duckdb table -> (postgres table, primary key)
PUBLISHED_TABLES: dict[str, tuple[str, list[str]]] = {
    "silver.dim_location": ("dim_location", ["location_id"]),
    "gold.mart_daily_weather": ("mart_daily_weather", ["location_id", "observation_date"]),
    "gold.mart_city_anomalies": ("mart_city_anomalies", ["city", "country", "observation_date"]),
}

_TYPE_MAP = {
    "BIGINT": "bigint",
    "INTEGER": "integer",
    "DOUBLE": "double precision",
    "VARCHAR": "text",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
    "BOOLEAN": "boolean",
}


def postgres_type(duckdb_type: str) -> str:
    if duckdb_type.startswith("DECIMAL"):
        return duckdb_type.replace("DECIMAL", "numeric")
    return _TYPE_MAP.get(duckdb_type, "text")


@dataclass(frozen=True)
class PublishResult:
    table: str
    rows: int


def publish(config: PipelineConfig, dsn: str | None = None) -> list[PublishResult]:
    dsn = dsn or os.environ.get("PIPELINE_PG_DSN", DEFAULT_DSN)
    catalog = load_catalog(config.project_root / "catalog" / "catalog.yml")["tables"]
    duck = duckdb.connect(str(config.warehouse_path), read_only=True)
    results: list[PublishResult] = []
    try:
        with psycopg.connect(dsn) as pg, pg.transaction():
            pg.execute(
                sql.SQL("create schema if not exists {}").format(sql.Identifier(TARGET_SCHEMA))
            )
            for source, (target, primary_key) in PUBLISHED_TABLES.items():
                columns = duck.execute(f"describe {source}").fetchall()  # name, type, ...
                rows = duck.execute(f"select * from {source}").fetchall()
                table = sql.Identifier(TARGET_SCHEMA, target)

                pg.execute(sql.SQL("drop table if exists {}").format(table))
                column_defs = [
                    sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(postgres_type(dtype)))
                    for name, dtype, *_ in columns
                ]
                column_defs.append(
                    sql.SQL("primary key ({})").format(
                        sql.SQL(", ").join(map(sql.Identifier, primary_key))
                    )
                )
                pg.execute(
                    sql.SQL("create table {} ({})").format(table, sql.SQL(", ").join(column_defs))
                )

                names = [name for name, *_ in columns]
                copy = sql.SQL("copy {} ({}) from stdin").format(
                    table, sql.SQL(", ").join(map(sql.Identifier, names))
                )
                with pg.cursor().copy(copy) as cp:
                    for row in rows:
                        cp.write_row(row)

                _apply_comments(pg, target, catalog.get(source, {}))

                published = pg.execute(sql.SQL("select count(*) from {}").format(table)).fetchone()[
                    0
                ]
                if published != len(rows):  # rolls back everything
                    raise RuntimeError(
                        f"{target}: DuckDB has {len(rows)} rows, PostgreSQL has {published}"
                    )
                results.append(PublishResult(f"{TARGET_SCHEMA}.{target}", published))
    finally:
        duck.close()
    return results


def _apply_comments(pg: psycopg.Connection, target: str, meta: dict) -> None:
    table = sql.Identifier(TARGET_SCHEMA, target)
    if meta.get("description"):
        pg.execute(
            sql.SQL("comment on table {} is {}").format(table, sql.Literal(meta["description"]))
        )
    for column, col_meta in (meta.get("columns") or {}).items():
        description = (col_meta or {}).get("description")
        if description:
            pg.execute(
                sql.SQL("comment on column {} is {}").format(
                    sql.Identifier(TARGET_SCHEMA, target, column), sql.Literal(description)
                )
            )
