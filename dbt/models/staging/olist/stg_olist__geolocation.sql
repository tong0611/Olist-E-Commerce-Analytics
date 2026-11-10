-- Static reference table with no key (many points per zip prefix): keep only
-- the rows from the most recently written file.
with source as (
    select * from {{ source('olist', 'geolocation') }}
)

select
    lpad(raw_data:geolocation_zip_code_prefix::string, 5, '0') as zip_code_prefix,
    raw_data:geolocation_lat::float                as latitude,
    raw_data:geolocation_lng::float                as longitude,
    initcap(raw_data:geolocation_city::string)     as city,
    upper(raw_data:geolocation_state::string)      as state,
    {{ raw_metadata() }}
from source
qualify dense_rank() over (order by _file_last_modified desc, _source_file desc) = 1
