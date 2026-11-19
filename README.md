# Weather Lakehouse: a governed ETL pipeline

[![ci](https://github.com/quizdany/data-engineering-portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/quizdany/data-engineering-portfolio/actions/workflows/ci.yml)

An end-to-end data pipeline that ingests public weather data for five African cities, models it in a layered warehouse, enforces data quality rules, documents every table and column in a data catalog with lineage, and publishes analytics-ready tables to PostgreSQL.

It is built to show the parts of data engineering that make data trustworthy, not just available:

| Need | How this project handles it |
| --- | --- |
| Reliable ingestion | Open-Meteo API client with retries; raw responses kept for audit and replay; idempotent runs |
| Layered modeling | `raw` → `bronze` (Parquet) → `silver` (typed, deduplicated) → `gold` (marts) in DuckDB |
| Data quality | Contract and quality gates (row counts, uniqueness, valid ranges); results stored in `ops.dq_results` for monitoring |
| Data governance | Data catalog and business glossary in `catalog/catalog.yml`; a check that fails if any column is undocumented |
| Lineage | Derived automatically from the SQL and rendered as a diagram in [docs/data_catalog.md](docs/data_catalog.md) |
| Serving | `publish` loads gold marts into PostgreSQL in one transaction, with primary keys on each table's grain, catalog descriptions as column comments, and row-count reconciliation |
| Engineering practice | Typed config, tests on synthetic data (no network needed), PostgreSQL in CI, linting, Docker |

## Architecture

```mermaid
flowchart LR
    A["Open-Meteo API"] --> B["Raw JSON<br/>(audit, replay)"]
    A --> C["Bronze Parquet"]
    C --> D["Silver tables<br/>typed, deduplicated"]
    D --> E["Gold marts"]
    E --> F{"Quality gate"}
    F --> G[("PostgreSQL<br/>analytics schema")]
    H["catalog.yml<br/>+ SQL lineage"] -.-> I["Data catalog docs<br/>+ governance check"]
    D -.-> I
    E -.-> I
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

weather-pipeline run --days 14        # ingest and build the warehouse
weather-pipeline quality              # run quality gates; results saved to ops.dq_results
weather-pipeline catalog              # regenerate docs/data_catalog.md (lineage + glossary)
weather-pipeline catalog --check      # fail if catalog and warehouse disagree

docker compose up -d postgres         # local PostgreSQL
weather-pipeline publish              # load gold marts into PostgreSQL (schema: analytics)
```

`publish` reads `PIPELINE_PG_DSN` (default: the docker-compose database).

## Data quality and governance

**Quality gates** (`src/data_pipeline/quality.py`) check that hourly facts exist, that each city and hour appears once, and that temperature, humidity and precipitation are physically possible. A failed check exits non-zero, so a scheduler stops before bad data reaches users. Every run is appended to `ops.dq_results`.

**The data catalog** (`catalog/catalog.yml`) records the owner, source, refresh pattern, each table's grain and description, every column's meaning, and a business glossary (baseline, anomaly, grain and so on). `catalog --check` compares it with the live warehouse schema. When I added the check, it immediately caught two partition columns (`start_date`, `end_date`) that were in the warehouse but undocumented.

**Lineage** is parsed from the transformation SQL, so it can't drift from the code:

```mermaid
flowchart LR
    A["bronze Parquet"] --> B["silver.bronze_hourly_weather"]
    B --> C["silver.dim_location"]
    B --> D["silver.fact_hourly_weather"]
    C --> D
    D --> E["gold.mart_daily_weather"]
    E --> F["gold.mart_city_anomalies"]
```

## Tests

```bash
pytest                                                   # offline, on synthetic data
TEST_PG_DSN=postgresql://pipeline:pipeline@localhost:5432/metadata pytest   # + PostgreSQL publish
```

The suite builds the warehouse from synthetic API payloads, so it needs no network. It checks the marts, confirms that quality checks pass on good data and catch impossible values, verifies that the catalog documents every column, validates the derived lineage, and tests that publishing to PostgreSQL is idempotent, enforces primary keys and carries catalog comments. CI runs everything against a PostgreSQL service container.

## Repository layout

```text
src/data_pipeline/   extract, warehouse, quality, catalog, publish, CLI
sql/                 transformation SQL (silver and gold)
catalog/catalog.yml  data catalog and business glossary
docs/                architecture notes, data contract, generated data catalog
tests/               unit and end-to-end tests
```

## Data source

[Open-Meteo](https://open-meteo.com/) historical weather API: free, no API key, hourly data from 1940 onward. The pipeline loads hourly temperature, humidity, precipitation and wind speed for Kigali, Nairobi, Lagos, Cape Town and Accra.
