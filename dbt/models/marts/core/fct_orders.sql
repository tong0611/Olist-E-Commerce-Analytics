-- One row per order. Revenue = merchandise + freight for orders that weren't
-- canceled / unavailable (var non_revenue_statuses).
with orders as (
    select * from {{ ref('stg_olist__orders') }}
),
customers as (
    select customer_id, customer_unique_id from {{ ref('stg_olist__customers') }}
),
items as (
    select * from {{ ref('int_orders__items_agg') }}
),
payments as (
    select * from {{ ref('int_orders__payments_agg') }}
),
reviews as (
    select * from {{ ref('int_orders__reviews_agg') }}
),

joined as (
    select
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        o.order_status,
        o.order_status not in (
            {%- for s in var('non_revenue_statuses') %}'{{ s }}'{{ ", " if not loop.last }}{% endfor -%}
        )                                                   as is_revenue_order,

        o.purchased_at,
        o.purchased_at::date                                as purchase_date,
        date_trunc('month', o.purchased_at)::date           as purchase_month,
        o.approved_at,
        o.delivered_to_carrier_at,
        o.delivered_to_customer_at,
        o.estimated_delivery_at,
        datediff('hour', o.purchased_at, o.approved_at)     as hours_to_approval,
        datediff('day', o.purchased_at, o.delivered_to_customer_at) as days_to_delivery,
        case
            when o.delivered_to_customer_at is null then null
            else o.delivered_to_customer_at::date > o.estimated_delivery_at::date
        end                                                 as is_late_delivery,

        coalesce(i.item_count, 0)              as item_count,
        coalesce(i.distinct_product_count, 0)  as distinct_product_count,
        coalesce(i.distinct_seller_count, 0)   as distinct_seller_count,
        coalesce(i.items_value, 0)             as items_value,
        coalesce(i.freight_value, 0)           as freight_value,
        coalesce(i.items_value, 0) + coalesce(i.freight_value, 0) as order_value,

        coalesce(p.payment_value, 0)           as payment_value,
        p.primary_payment_type,
        p.payment_method_count,
        p.max_installments,

        r.review_score,
        r.review_count,
        r.has_review_comment
    from orders o
    left join customers c using (customer_id)
    left join items     i using (order_id)
    left join payments  p using (order_id)
    left join reviews   r using (order_id)
)

select
    *,
    iff(is_revenue_order, order_value, 0) as revenue,
    -- 1 = customer's first revenue order, 2 = second, ...  (null for non-revenue orders)
    iff(
        is_revenue_order,
        row_number() over (partition by customer_unique_id, is_revenue_order order by purchased_at, order_id),
        null
    ) as customer_order_sequence
from joined
