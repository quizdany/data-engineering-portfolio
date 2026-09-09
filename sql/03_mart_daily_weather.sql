create or replace table gold.mart_daily_weather as
select
    location_id,
    city,
    country,
    cast(observed_at as date) as observation_date,
    round(avg(temperature_c), 2) as avg_temperature_c,
    round(min(temperature_c), 2) as min_temperature_c,
    round(max(temperature_c), 2) as max_temperature_c,
    round(avg(relative_humidity_pct), 2) as avg_relative_humidity_pct,
    round(sum(precipitation_mm), 2) as total_precipitation_mm,
    round(avg(wind_speed_kmh), 2) as avg_wind_speed_kmh,
    count(*) as hourly_observations
from silver.fact_hourly_weather
group by location_id, city, country, cast(observed_at as date);

