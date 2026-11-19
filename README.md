# Weather Lakehouse – ETL pipeline

[![ci](https://github.com/quizdany/data-engineering-portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/quizdany/data-engineering-portfolio/actions/workflows/ci.yml)

Pulls hourly weather data for five African cities (Kigali, Nairobi, Lagos, Cape Town, Accra) from the Open-Meteo API, builds a layered warehouse in DuckDB, checks data quality, and publishes the final tables to PostgreSQL.

## What's in it

- **Ingestion** – API client with retries; raw JSON kept for replay; reruns are idempotent
- **Layers** – raw → bronze (Parquet) → silver (typed, deduplicated) → gold (marts)
- **Quality checks** – row counts, unique city/hour, valid ranges. A failure stops the run. Results are saved to `ops.dq_results`
- **Data catalog** – `catalog/catalog.yml` has the owner, grain, column descriptions and a glossary. `catalog --check` fails if a column isn't documented
- **Lineage** – parsed from the SQL, shown in [docs/data_catalog.md](docs/data_catalog.md)
- **PostgreSQL** – `publish` loads the marts in one transaction, with primary keys, column comments from the catalog, and a row-count check
- **Tests** – run on fake API data, no network needed; CI also tests the PostgreSQL step

```mermaid
flowchart LR
    A["Open-Meteo API"] --> B["raw JSON"]
    A --> C["bronze"]
    C --> D["silver"] --> E["gold"] --> F{"quality checks"} --> G[("PostgreSQL")]
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

weather-pipeline run --days 14
weather-pipeline quality
weather-pipeline catalog            # regenerate docs/data_catalog.md
weather-pipeline catalog --check

docker compose up -d postgres
weather-pipeline publish            # uses PIPELINE_PG_DSN
```

## Lineage

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
pytest
TEST_PG_DSN=postgresql://pipeline:pipeline@localhost:5432/metadata pytest   # includes the Postgres test
```

## Layout

```text
src/data_pipeline/   extract, warehouse, quality, catalog, publish, cli
sql/                 silver and gold SQL
catalog/             catalog.yml
docs/                architecture, data contract, generated catalog
tests/
```

Data: [Open-Meteo](https://open-meteo.com/) historical weather API (free, no key).
