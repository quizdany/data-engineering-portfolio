create or replace table silver.fact_hourly_weather as
select
    l.location_id,
    b.city,
    b.country,
    cast(b.observed_at as timestamp) as observed_at,
    cast(b.temperature_c as double) as temperature_c,
    cast(b.relative_humidity_pct as double) as relative_humidity_pct,
    cast(b.precipitation_mm as double) as precipitation_mm,
    cast(b.wind_speed_kmh as double) as wind_speed_kmh,
    b.source,
    cast(b.ingested_at_utc as timestamp) as ingested_at_utc
from silver.bronze_hourly_weather b
join silver.dim_location l
    on b.city = l.city
    and b.country = l.country
qualify row_number() over (
    partition by b.city, b.country, cast(b.observed_at as timestamp)
    order by cast(b.ingested_at_utc as timestamp) desc
) = 1;

