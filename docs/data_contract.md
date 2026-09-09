# Data Contract

## Source

Open-Meteo Historical Weather API.

## Grain

One row per city per hourly observation timestamp.

## Bronze Columns

| Column | Type | Rule |
| --- | --- | --- |
| city | string | Required |
| country | string | Required |
| latitude | double | Required |
| longitude | double | Required |
| observed_at | timestamp | Required |
| temperature_c | double | Between -80 and 60 |
| relative_humidity_pct | double | Between 0 and 100 |
| precipitation_mm | double | Greater than or equal to 0 |
| wind_speed_kmh | double | Greater than or equal to 0 |
| source | string | Must be `open_meteo` |
| ingested_at_utc | timestamp | Required |

## Quality Gates

- Silver hourly facts must contain rows.
- City and timestamp pairs must be unique.
- Temperature, humidity, and precipitation must remain within valid ranges.

