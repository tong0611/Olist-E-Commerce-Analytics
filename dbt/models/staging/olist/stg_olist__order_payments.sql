with source as (
    select * from {{ source('olist', 'order_payments') }}
)

select
    raw_data:order_id::string                 as order_id,
    raw_data:payment_sequential::int          as payment_sequence,
    lower(raw_data:payment_type::string)      as payment_type,
    raw_data:payment_installments::int        as installments,
    raw_data:payment_value::number(12, 2)     as payment_value,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:order_id, raw_data:payment_sequential') }}
