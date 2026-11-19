# Architecture Notes

## System Design

This repository models a small lakehouse-style analytics platform:

1. **Source system**: Open-Meteo historical weather API.
2. **Raw zone**: Full JSON payloads are stored for audit and replay.
3. **Bronze zone**: Source-shaped Parquet preserves ingestion metadata.
4. **Silver zone**: DuckDB tables enforce types, deduplicate records, and attach dimensions.
5. **Gold zone**: Daily marts and anomaly metrics support analytics.
6. **Quality gate**: Checks fail fast when data contracts are violated.

## Why DuckDB and Parquet

DuckDB provides local analytical SQL execution without needing a server. Parquet
keeps the lake storage columnar, compressed, and portable. Together they mimic
patterns used in larger stacks such as Spark, Trino, Iceberg, and warehouse ELT,
but remain easy for reviewers to run on a laptop.

## Operational Concerns Demonstrated

- **Idempotency**: Each run writes deterministic partitions for the selected date range.
- **Replayability**: Raw payloads can be reprocessed if transformation logic changes.
- **Contracts**: Quality checks cover row counts, uniqueness, and valid physical ranges.
- **Separation of concerns**: Extraction, modeling, and validation are isolated modules.
- **Portability**: Docker services show how object storage and metadata stores fit in.

## Governance and Serving

- `catalog/catalog.yml` – table/column descriptions, owner, grain, glossary
- lineage is parsed from `sql/` and written to `docs/data_catalog.md`
- `catalog --check` fails on undocumented or stale columns
- quality results are appended to `ops.dq_results`
- `publish` loads gold marts into PostgreSQL (one transaction, primary keys, row-count check)

## Future Production Extensions

- Add Airflow, Dagster, or Prefect scheduling.
- Store Parquet in S3 or MinIO using partitioned paths.
- Add Great Expectations or Soda for richer data contracts.
- Add OpenTelemetry metrics and structured logs.

