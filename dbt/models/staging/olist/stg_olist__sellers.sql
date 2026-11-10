with source as (
    select * from {{ source('olist', 'sellers') }}
)

select
    raw_data:seller_id::string              as seller_id,
    lpad(raw_data:seller_zip_code_prefix::string, 5, '0') as zip_code_prefix,
    initcap(raw_data:seller_city::string)   as city,
    upper(raw_data:seller_state::string)    as state,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:seller_id') }}
