-- One row per zip code prefix: centroid of its geolocation points.
-- Points outside Brazil's bounding box are bad data and are dropped.
with points as (
    select *
    from {{ ref('stg_olist__geolocation') }}
    where latitude  between -33.75 and 5.27
      and longitude between -73.99 and -34.79
)

select
    zip_code_prefix,
    avg(latitude)       as latitude,
    avg(longitude)      as longitude,
    mode(city)          as city,
    mode(state)         as state,
    count(*)            as point_count
from points
group by zip_code_prefix
