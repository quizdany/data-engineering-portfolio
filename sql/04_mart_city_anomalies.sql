create or replace table gold.mart_city_anomalies as
with daily as (
    select * from gold.mart_daily_weather
),
baselines as (
    select
        city,
        country,
        avg(avg_temperature_c) as baseline_avg_temperature_c,
        avg(total_precipitation_mm) as baseline_precipitation_mm
    from daily
    group by city, country
)
select
    d.city,
    d.country,
    d.observation_date,
    d.avg_temperature_c,
    round(d.avg_temperature_c - b.baseline_avg_temperature_c, 2) as temperature_anomaly_c,
    d.total_precipitation_mm,
    round(d.total_precipitation_mm - b.baseline_precipitation_mm, 2) as precipitation_anomaly_mm
from daily d
join baselines b
    on d.city = b.city
    and d.country = b.country;

