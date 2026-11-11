-- One row per real customer (customer_unique_id), with lifetime value and churn.
-- "Today" is the latest order date in the data: the simulation clock.
with orders as (
    select * from {{ ref('fct_orders') }}
),
customers as (
    select * from {{ ref('stg_olist__customers') }}
),
zip_codes as (
    select * from {{ ref('int_zip_codes') }}
),
-- latest REVENUE order: a trailing canceled order must not move the clock
-- (the dataset ends with a few canceled orders weeks after sales stop)
as_of as (
    select max(purchase_date) as as_of_date from orders where is_revenue_order
),

-- location as of the customer's most recent order
latest_location as (
    select c.customer_unique_id, c.zip_code_prefix, c.city, c.state
    from customers c
    join orders o using (customer_id)
    qualify row_number() over (partition by c.customer_unique_id order by o.purchased_at desc) = 1
),

stats as (
    select
        customer_unique_id,
        count(*)                                        as total_orders,
        count_if(is_revenue_order)                      as revenue_orders,
        min(purchased_at)                               as first_order_at,
        min(iff(is_revenue_order, purchase_date, null)) as first_purchase_date,
        max(iff(is_revenue_order, purchase_date, null)) as last_purchase_date,
        sum(revenue)                                    as lifetime_revenue,
        sum(iff(is_revenue_order, item_count, 0))       as lifetime_items,
        avg(review_score)                               as avg_review_score
    from orders
    group by customer_unique_id
)

select
    s.customer_unique_id,
    l.zip_code_prefix,
    l.city,
    l.state,
    z.latitude,
    z.longitude,

    s.total_orders,
    s.revenue_orders,
    s.first_order_at,
    s.first_purchase_date,
    s.last_purchase_date,
    date_trunc('month', s.first_purchase_date)::date      as cohort_month,

    s.lifetime_revenue                                    as customer_lifetime_value,
    s.lifetime_revenue / nullif(s.revenue_orders, 0)      as avg_order_value,
    s.lifetime_items,
    s.avg_review_score,

    case
        when s.revenue_orders = 0 then 'no_purchase'
        when s.revenue_orders = 1 then 'one_time'
        else 'repeat'
    end                                                   as customer_type,
    datediff('day', s.last_purchase_date, a.as_of_date)   as days_since_last_purchase,
    iff(
        s.revenue_orders > 0,
        datediff('day', s.last_purchase_date, a.as_of_date) > {{ var('churn_window_days') }},
        null
    )                                                     as is_churned,
    a.as_of_date
from stats s
cross join as_of a
left join latest_location l using (customer_unique_id)
left join zip_codes z on z.zip_code_prefix = l.zip_code_prefix
