-- Revenue must be identical whether summed by order or by item line.
with by_order as (select sum(revenue) as r from {{ ref('fct_orders') }}),
     by_item  as (select sum(revenue) as r from {{ ref('fct_order_items') }}),
     by_month as (select sum(revenue) as r from {{ ref('mart_revenue_monthly') }})
select o.r as order_revenue, i.r as item_revenue, m.r as monthly_revenue
from by_order o, by_item i, by_month m
where abs(o.r - i.r) > 0.01 or abs(o.r - m.r) > 0.01
