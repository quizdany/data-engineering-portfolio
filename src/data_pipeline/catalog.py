"""Data catalog, business glossary and lineage for the warehouse.

The catalog lives in catalog/catalog.yml. This module:
- derives table-level lineage from the SQL transformation files,
- compares the catalog with the live warehouse schema (governance check), and
- renders docs/data_catalog.md, including a Mermaid lineage diagram.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import yaml

from data_pipeline.config import PipelineConfig

TABLE_REF = r"([a-z_]+\.[a-z_][a-z0-9_]*)"
_TARGET = re.compile(rf"create\s+or\s+replace\s+(?:table|view)\s+{TABLE_REF}", re.IGNORECASE)
_SOURCE = re.compile(rf"\b(?:from|join)\s+{TABLE_REF}", re.IGNORECASE)
_COMMENT = re.compile(r"--[^\n]*")

# The bronze view is created in Python (warehouse.py), not in a SQL file.
BRONZE_EDGE = ("bronze.open_meteo_hourly (Parquet)", "silver.bronze_hourly_weather")


def parse_lineage(sql: str) -> list[tuple[str, str]]:
    """Return (source, target) edges for every CREATE TABLE/VIEW statement in a SQL script."""
    edges: list[tuple[str, str]] = []
    for statement in _COMMENT.sub("", sql).split(";"):
        target = _TARGET.search(statement)
        if not target:
            continue
        for source in dict.fromkeys(_SOURCE.findall(statement)):  # keep order, drop repeats
            if source != target.group(1):
                edges.append((source.lower(), target.group(1).lower()))
    return edges


def lineage_from_sql_dir(sql_dir: Path) -> list[tuple[str, str]]:
    edges = [BRONZE_EDGE]
    for path in sorted(sql_dir.glob("*.sql")):
        edges.extend(parse_lineage(path.read_text(encoding="utf-8")))
    return edges


def load_catalog(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def warehouse_schema(warehouse_path: Path) -> dict[str, dict[str, str]]:
    """Return {schema.table: {column: data_type}} for every documented layer in the warehouse."""
    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        rows = con.execute(
            """
            select table_schema || '.' || table_name, column_name, data_type
            from information_schema.columns
            where table_schema in ('silver', 'gold', 'ops')
            order by table_schema, table_name, ordinal_position
            """
        ).fetchall()
    finally:
        con.close()
    schema: dict[str, dict[str, str]] = {}
    for table, column, data_type in rows:
        schema.setdefault(table, {})[column] = data_type
    return schema


@dataclass
class CatalogGaps:
    undocumented_tables: list[str] = field(default_factory=list)
    undocumented_columns: list[str] = field(default_factory=list)
    stale_tables: list[str] = field(default_factory=list)
    stale_columns: list[str] = field(default_factory=list)
    missing_descriptions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(vars(self).values())

    def lines(self) -> list[str]:
        labels = {
            "undocumented_tables": "Table in warehouse but not in catalog",
            "undocumented_columns": "Column in warehouse but not in catalog",
            "stale_tables": "Table in catalog but not in warehouse",
            "stale_columns": "Column in catalog but not in warehouse",
            "missing_descriptions": "Missing description",
        }
        return [f"{labels[name]}: {item}" for name, items in vars(self).items() for item in items]


def compare(catalog: dict, schema: dict[str, dict[str, str]]) -> CatalogGaps:
    gaps = CatalogGaps()
    documented = catalog.get("tables", {})
    for table, columns in schema.items():
        if table not in documented:
            gaps.undocumented_tables.append(table)
            continue
        doc_columns = documented[table].get("columns", {})
        gaps.undocumented_columns += [f"{table}.{c}" for c in columns if c not in doc_columns]
        gaps.stale_columns += [f"{table}.{c}" for c in doc_columns if c not in columns]
    gaps.stale_tables += [t for t in documented if t not in schema]
    for table, meta in documented.items():
        if not meta.get("description"):
            gaps.missing_descriptions.append(table)
        for column, col_meta in (meta.get("columns") or {}).items():
            if not (col_meta or {}).get("description"):
                gaps.missing_descriptions.append(f"{table}.{column}")
    return gaps


def _node(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def render_mermaid(edges: list[tuple[str, str]]) -> str:
    lines = ["flowchart LR"]
    nodes = dict.fromkeys(n for edge in edges for n in edge)
    for name in nodes:
        lines.append(f'    {_node(name)}["{name}"]')
    for source, target in edges:
        lines.append(f"    {_node(source)} --> {_node(target)}")
    return "\n".join(lines)


def render_markdown(
    catalog: dict,
    schema: dict[str, dict[str, str]],
    edges: list[tuple[str, str]],
) -> str:
    out = [
        "# Data catalog",
        "",
        "Generated by `weather-pipeline catalog` from `catalog/catalog.yml`, the SQL in `sql/`",
        "and the live warehouse schema. Do not edit by hand.",
        "",
        f"- **Owner:** {catalog.get('owner', '')}",
        f"- **Source system:** {catalog.get('source_system', '')}",
        f"- **Refresh:** {catalog.get('refresh', '')}",
        "",
        "## Lineage",
        "",
        "```mermaid",
        render_mermaid(edges),
        "```",
        "",
        "## Tables",
    ]
    upstream: dict[str, list[str]] = {}
    for source, target in edges:
        upstream.setdefault(target, []).append(source)

    for table, meta in catalog.get("tables", {}).items():
        out += ["", f"### `{table}`", "", meta.get("description", ""), ""]
        out.append(f"- **Layer:** {meta.get('layer', '')}")
        out.append(f"- **Grain:** {meta.get('grain', '')}")
        if table in upstream:
            out.append("- **Built from:** " + ", ".join(f"`{s}`" for s in upstream[table]))
        if meta.get("quality_checks"):
            out.append(
                "- **Quality checks:** " + ", ".join(f"`{c}`" for c in meta["quality_checks"])
            )
        out += ["", "| Column | Type | Description |", "| --- | --- | --- |"]
        types = schema.get(table, {})
        for column, col_meta in (meta.get("columns") or {}).items():
            description = (col_meta or {}).get("description", "")
            out.append(f"| `{column}` | {types.get(column, '')} | {description} |")

    out += ["", "## Business glossary", "", "| Term | Definition |", "| --- | --- |"]
    for term, meta in sorted(catalog.get("glossary", {}).items()):
        out.append(f"| {term} | {meta.get('definition', '')} |")
    return "\n".join(out) + "\n"


def build_catalog(config: PipelineConfig, check_only: bool = False) -> CatalogGaps:
    catalog = load_catalog(config.project_root / "catalog" / "catalog.yml")
    schema = warehouse_schema(config.warehouse_path)
    gaps = compare(catalog, schema)
    if not check_only:
        edges = lineage_from_sql_dir(config.project_root / "sql")
        doc_path = config.project_root / "docs" / "data_catalog.md"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(render_markdown(catalog, schema, edges), encoding="utf-8")
    return gaps
