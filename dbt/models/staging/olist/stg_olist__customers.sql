-- customer_id is created per ORDER. customer_unique_id identifies the person
-- and is the key for every customer-level metric.
with source as (
    select * from {{ source('olist', 'customers') }}
)

select
    raw_data:customer_id::string              as customer_id,
    raw_data:customer_unique_id::string       as customer_unique_id,
    lpad(raw_data:customer_zip_code_prefix::string, 5, '0') as zip_code_prefix,
    initcap(raw_data:customer_city::string)   as city,
    upper(raw_data:customer_state::string)    as state,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:customer_id') }}
