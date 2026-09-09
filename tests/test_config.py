from datetime import date

from data_pipeline.config import Location, date_window


def test_location_key_is_stable() -> None:
    location = Location(city="Cape Town", country="South Africa", latitude=-33.9, longitude=18.4)
    assert location.key == "cape_town_south_africa"


def test_date_window_returns_requested_number_of_days() -> None:
    start, end = date_window(7)
    assert isinstance(start, date)
    assert isinstance(end, date)
    assert (end - start).days == 6

