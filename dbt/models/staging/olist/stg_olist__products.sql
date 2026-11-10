with source as (
    select * from {{ source('olist', 'products') }}
)

select
    raw_data:product_id::string                       as product_id,
    raw_data:product_category_name::string            as category_name_pt,
    -- source columns are misspelled ("lenght"); fixed here
    raw_data:product_name_lenght::int                 as name_length,
    raw_data:product_description_lenght::int          as description_length,
    raw_data:product_photos_qty::int                  as photo_count,
    raw_data:product_weight_g::number(10, 1)          as weight_g,
    raw_data:product_length_cm::number(10, 1)         as length_cm,
    raw_data:product_height_cm::number(10, 1)         as height_cm,
    raw_data:product_width_cm::number(10, 1)          as width_cm,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:product_id') }}
