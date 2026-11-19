from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb

from data_pipeline.config import PipelineConfig


@dataclass(frozen=True)
class QualityResult:
    check_name: str
    passed: bool
    observed_value: int | float
    expectation: str


QUALITY_CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "hourly_fact_has_rows",
        "select count(*) from silver.fact_hourly_weather",
        "> 0",
    ),
    (
        "hourly_fact_unique_city_timestamp",
        """
        select count(*) - count(distinct city || '|' || cast(observed_at as varchar))
        from silver.fact_hourly_weather
        """,
        "= 0",
    ),
    (
        "temperature_reasonable_range",
        """
        select count(*) from silver.fact_hourly_weather
        where temperature_c < -80 or temperature_c > 60
        """,
        "= 0",
    ),
    (
        "humidity_reasonable_range",
        """
        select count(*) from silver.fact_hourly_weather
        where relative_humidity_pct < 0 or relative_humidity_pct > 100
        """,
        "= 0",
    ),
    (
        "precipitation_non_negative",
        """
        select count(*) from silver.fact_hourly_weather
        where precipitation_mm < 0
        """,
        "= 0",
    ),
)


def _evaluate(value: int | float, expectation: str) -> bool:
    operator, threshold = expectation.split()
    threshold_value = float(threshold)
    if operator == ">":
        return value > threshold_value
    if operator == "=":
        return value == threshold_value
    raise ValueError(f"Unsupported expectation: {expectation}")


def run_quality_checks(config: PipelineConfig) -> list[QualityResult]:
    con = duckdb.connect(str(config.warehouse_path), read_only=True)
    try:
        results: list[QualityResult] = []
        for check_name, sql, expectation in QUALITY_CHECKS:
            observed = con.execute(sql).fetchone()[0]
            results.append(
                QualityResult(
                    check_name=check_name,
                    passed=_evaluate(observed, expectation),
                    observed_value=observed,
                    expectation=expectation,
                )
            )
        return results
    finally:
        con.close()



def record_results(config: PipelineConfig, results: list[QualityResult]) -> str:
    """Append results to ops.dq_results so quality can be monitored across runs."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    con = duckdb.connect(str(config.warehouse_path))
    try:
        con.executemany(
            "insert into ops.dq_results values (?, ?, ?, ?, ?, now())",
            [
                (run_id, r.check_name, r.passed, float(r.observed_value), r.expectation)
                for r in results
            ],
        )
    finally:
        con.close()
    return run_id
