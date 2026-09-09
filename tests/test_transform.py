from data_pipeline.config import Location
from data_pipeline.extract import payload_to_bronze_frame


def test_payload_to_bronze_frame_normalizes_open_meteo_payload() -> None:
    payload = {
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [20.1, 21.2],
            "relative_humidity_2m": [70, 72],
            "precipitation": [0.0, 0.2],
            "wind_speed_10m": [10.5, 11.0],
        }
    }
    location = Location(city="Kigali", country="Rwanda", latitude=-1.9441, longitude=30.0619)

    frame = payload_to_bronze_frame(location, payload)

    assert list(frame["city"].unique()) == ["Kigali"]
    assert "temperature_c" in frame.columns
    assert "relative_humidity_pct" in frame.columns
    assert len(frame) == 2

