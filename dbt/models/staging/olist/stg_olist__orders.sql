with source as (
    select * from {{ source('olist', 'orders') }}
)

select
    raw_data:order_id::string                             as order_id,
    raw_data:customer_id::string                          as customer_id,
    lower(raw_data:order_status::string)                  as order_status,
    raw_data:order_purchase_timestamp::timestamp_ntz      as purchased_at,
    raw_data:order_approved_at::timestamp_ntz             as approved_at,
    raw_data:order_delivered_carrier_date::timestamp_ntz  as delivered_to_carrier_at,
    raw_data:order_delivered_customer_date::timestamp_ntz as delivered_to_customer_at,
    raw_data:order_estimated_delivery_date::timestamp_ntz as estimated_delivery_at,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:order_id') }}
