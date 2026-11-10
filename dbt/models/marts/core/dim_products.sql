with products as (
    select * from {{ ref('stg_olist__products') }}
),
translations as (
    select * from {{ ref('stg_olist__product_category_translation') }}
)

select
    p.product_id,
    p.category_name_pt,
    -- 2 Portuguese categories have no English translation in the source, and
    -- some products have no category at all
    coalesce(t.category_name, p.category_name_pt, 'unknown') as category_name,
    initcap(replace(coalesce(t.category_name, p.category_name_pt, 'unknown'), '_', ' ')) as category_label,
    p.name_length,
    p.description_length,
    p.photo_count,
    p.weight_g,
    p.length_cm,
    p.height_cm,
    p.width_cm,
    p.length_cm * p.height_cm * p.width_cm as volume_cm3
from products p
left join translations t using (category_name_pt)
