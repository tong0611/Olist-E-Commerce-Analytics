with source as (
    select * from {{ source('olist', 'order_items') }}
)

select
    {{ dbt_utils.generate_surrogate_key(["raw_data:order_id::string", "raw_data:order_item_id::int"]) }} as order_item_key,
    raw_data:order_id::string                   as order_id,
    raw_data:order_item_id::int                 as order_item_number,
    raw_data:product_id::string                 as product_id,
    raw_data:seller_id::string                  as seller_id,
    raw_data:shipping_limit_date::timestamp_ntz as shipping_limit_at,
    raw_data:price::number(12, 2)               as price,
    raw_data:freight_value::number(12, 2)       as freight_value,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:order_id, raw_data:order_item_id') }}
