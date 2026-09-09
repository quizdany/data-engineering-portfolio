from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, Field


class Location(BaseModel):
    city: str
    country: str
    latitude: float
    longitude: float
    timezone: str = "auto"

    @property
    def key(self) -> str:
        return f"{self.city.lower().replace(' ', '_')}_{self.country.lower().replace(' ', '_')}"


class PipelineConfig(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    api_url: str = "https://archive-api.open-meteo.com/v1/archive"
    locations: list[Location] = Field(default_factory=list)
    hourly_variables: tuple[str, ...] = (
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "wind_speed_10m",
    )

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw" / "open_meteo"

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze" / "open_meteo_hourly"

    @property
    def warehouse_path(self) -> Path:
        return self.data_dir / "warehouse" / "weather.duckdb"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"


def default_locations() -> list[Location]:
    return [
        Location(city="Kigali", country="Rwanda", latitude=-1.9441, longitude=30.0619),
        Location(city="Nairobi", country="Kenya", latitude=-1.2921, longitude=36.8219),
        Location(city="Lagos", country="Nigeria", latitude=6.5244, longitude=3.3792),
        Location(city="Cape Town", country="South Africa", latitude=-33.9249, longitude=18.4241),
        Location(city="Accra", country="Ghana", latitude=5.6037, longitude=-0.1870),
    ]


def build_config(project_root: Path | None = None) -> PipelineConfig:
    return PipelineConfig(
        project_root=project_root or Path.cwd(),
        locations=default_locations(),
    )


def date_window(days: int) -> tuple[date, date]:
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=days - 1)
    return start, end

