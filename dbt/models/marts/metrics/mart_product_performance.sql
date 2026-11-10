-- One row per product: units, revenue, reviews and rank (overall and within category).
with items as (
    select * from {{ ref('fct_order_items') }} where is_revenue_order
),
products as (
    select * from {{ ref('dim_products') }}
),
agg as (
    select
        product_id,
        count(*)                    as units_sold,
        count(distinct order_id)    as orders,
        count(distinct customer_unique_id) as customers,
        sum(price)                  as merchandise_revenue,
        sum(revenue)                as revenue,
        avg(price)                  as avg_price,
        avg(order_review_score)     as avg_review_score,
        min(purchase_date)          as first_sold_date,
        max(purchase_date)          as last_sold_date
    from items
    group by 1
)

select
    p.product_id,
    p.category_name,
    p.category_label,
    a.units_sold,
    a.orders,
    a.customers,
    a.merchandise_revenue,
    a.revenue,
    a.avg_price,
    a.avg_review_score,
    a.first_sold_date,
    a.last_sold_date,
    rank() over (order by a.revenue desc)                                as revenue_rank,
    rank() over (partition by p.category_name order by a.revenue desc)   as category_revenue_rank
from agg a
join products p using (product_id)
