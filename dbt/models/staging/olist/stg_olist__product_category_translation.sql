with source as (
    select * from {{ source('olist', 'product_category_translation') }}
)

select
    raw_data:product_category_name::string         as category_name_pt,
    raw_data:product_category_name_english::string as category_name,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:product_category_name') }}
