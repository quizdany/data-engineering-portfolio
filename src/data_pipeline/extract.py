from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from data_pipeline.config import Location, PipelineConfig


class OpenMeteoClient:
    def __init__(self, config: PipelineConfig, timeout_seconds: int = 30) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def fetch_hourly(self, location: Location, start_date: date, end_date: date) -> dict[str, Any]:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(self.config.hourly_variables),
            "timezone": location.timezone,
        }
        for attempt in range(3):
            response = requests.get(
                self.config.api_url,
                params=params,
                timeout=self.timeout_seconds,
            )
            if response.ok:
                payload = response.json()
                if "hourly" not in payload:
                    raise ValueError(f"Open-Meteo response missing hourly data: {payload}")
                return payload
            if attempt == 2:
                response.raise_for_status()
            time.sleep(2**attempt)
        raise RuntimeError("unreachable retry state")


def write_raw_payload(
    raw_dir: Path,
    location: Location,
    start_date: date,
    end_date: date,
    payload: dict[str, Any],
) -> Path:
    partition = (
        raw_dir
        / f"start_date={start_date.isoformat()}"
        / f"end_date={end_date.isoformat()}"
    )
    partition.mkdir(parents=True, exist_ok=True)
    output_path = partition / f"{location.key}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def payload_to_bronze_frame(location: Location, payload: dict[str, Any]) -> pd.DataFrame:
    hourly = payload["hourly"]
    frame = pd.DataFrame(hourly)
    frame = frame.rename(
        columns={
            "time": "observed_at",
            "temperature_2m": "temperature_c",
            "relative_humidity_2m": "relative_humidity_pct",
            "precipitation": "precipitation_mm",
            "wind_speed_10m": "wind_speed_kmh",
        }
    )
    frame["observed_at"] = pd.to_datetime(frame["observed_at"])
    frame.insert(0, "city", location.city)
    frame.insert(1, "country", location.country)
    frame.insert(2, "latitude", location.latitude)
    frame.insert(3, "longitude", location.longitude)
    frame["source"] = "open_meteo"
    frame["ingested_at_utc"] = pd.Timestamp.now(tz="UTC")
    return frame


def write_bronze(bronze_dir: Path, frame: pd.DataFrame, start_date: date, end_date: date) -> Path:
    output_dir = (
        bronze_dir
        / f"start_date={start_date.isoformat()}"
        / f"end_date={end_date.isoformat()}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "hourly_weather.parquet"
    frame.to_parquet(output_path, index=False)
    return output_path


def extract_to_bronze(config: PipelineConfig, start_date: date, end_date: date) -> Path:
    client = OpenMeteoClient(config)
    frames: list[pd.DataFrame] = []
    for location in config.locations:
        payload = client.fetch_hourly(location, start_date, end_date)
        write_raw_payload(config.raw_dir, location, start_date, end_date, payload)
        frames.append(payload_to_bronze_frame(location, payload))

    bronze = pd.concat(frames, ignore_index=True)
    return write_bronze(config.bronze_dir, bronze, start_date, end_date)
