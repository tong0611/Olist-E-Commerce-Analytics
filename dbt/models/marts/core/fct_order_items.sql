-- One row per item line. Grain for product and seller analysis.
with items as (
    select * from {{ ref('stg_olist__order_items') }}
),
orders as (
    select order_id, customer_unique_id, order_status, is_revenue_order,
           purchased_at, purchase_date, purchase_month, review_score
    from {{ ref('fct_orders') }}
)

select
    i.order_item_key,
    i.order_id,
    i.order_item_number,
    i.product_id,
    i.seller_id,
    o.customer_unique_id,
    o.order_status,
    o.is_revenue_order,
    o.purchased_at,
    o.purchase_date,
    o.purchase_month,
    i.shipping_limit_at,
    i.price,
    i.freight_value,
    i.price + i.freight_value                            as item_value,
    iff(o.is_revenue_order, i.price + i.freight_value, 0) as revenue,
    o.review_score                                       as order_review_score
from items i
join orders o using (order_id)
