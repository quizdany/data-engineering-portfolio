create or replace table silver.dim_location as
select
    row_number() over (order by country, city) as location_id,
    city,
    country,
    any_value(latitude) as latitude,
    any_value(longitude) as longitude
from silver.bronze_hourly_weather
group by city, country;

