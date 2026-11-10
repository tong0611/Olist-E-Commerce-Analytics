with sellers as (
    select * from {{ ref('stg_olist__sellers') }}
),
zip_codes as (
    select * from {{ ref('int_zip_codes') }}
)

select
    s.seller_id,
    s.zip_code_prefix,
    s.city,
    s.state,
    z.latitude,
    z.longitude
from sellers s
left join zip_codes z using (zip_code_prefix)
