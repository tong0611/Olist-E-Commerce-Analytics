-- One row per calendar month (no gaps): revenue, orders, AOV, new vs returning
-- customers, growth. "Monthly revenue run rate" stands in for MRR because
-- Olist has no subscriptions.
with orders as (
    select * from {{ ref('fct_orders') }} where is_revenue_order
),
months as (
    select distinct month_start as month
    from {{ ref('dim_date') }}
    where month_start between (select min(purchase_month) from orders)
                          and (select max(purchase_month) from orders)
),
monthly as (
    select
        purchase_month                                              as month,
        count(*)                                                    as orders,
        count(distinct customer_unique_id)                          as active_customers,
        count(distinct iff(customer_order_sequence = 1, customer_unique_id, null)) as new_customers,
        sum(revenue)                                                as revenue,
        sum(items_value)                                            as merchandise_revenue,
        sum(freight_value)                                          as freight_revenue,
        sum(item_count)                                             as items_sold
    from orders
    group by 1
)

select
    m.month,
    coalesce(x.orders, 0)                                   as orders,
    coalesce(x.active_customers, 0)                         as active_customers,
    coalesce(x.new_customers, 0)                            as new_customers,
    coalesce(x.active_customers, 0) - coalesce(x.new_customers, 0) as returning_customers,
    coalesce(x.revenue, 0)                                  as revenue,
    coalesce(x.merchandise_revenue, 0)                      as merchandise_revenue,
    coalesce(x.freight_revenue, 0)                          as freight_revenue,
    coalesce(x.items_sold, 0)                               as items_sold,
    x.revenue / nullif(x.orders, 0)                         as avg_order_value,
    lag(coalesce(x.revenue, 0)) over (order by m.month)     as prev_month_revenue,
    (coalesce(x.revenue, 0) - prev_month_revenue) / nullif(prev_month_revenue, 0) as revenue_mom_growth,
    sum(coalesce(x.revenue, 0)) over (order by m.month rows between unbounded preceding and current row) as cumulative_revenue,
    -- the dataset starts mid-2016 and stops mid-Oct 2018: flag the thin edges
    coalesce(x.orders, 0) < 100                             as is_partial_month
from months m
left join monthly x using (month)
