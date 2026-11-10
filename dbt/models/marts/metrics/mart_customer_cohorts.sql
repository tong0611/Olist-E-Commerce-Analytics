-- Retention triangle: for each first-purchase month (cohort), the share of
-- customers who purchased again N months later.
with orders as (
    select customer_unique_id, purchase_month
    from {{ ref('fct_orders') }}
    where is_revenue_order
),
customers as (
    select customer_unique_id, cohort_month
    from {{ ref('dim_customers') }}
    where cohort_month is not null
),
cohort_sizes as (
    select cohort_month, count(*) as cohort_size
    from customers
    group by 1
),
activity as (
    select distinct
        c.cohort_month,
        datediff('month', c.cohort_month, o.purchase_month) as months_since_first_purchase,
        o.customer_unique_id
    from orders o
    join customers c using (customer_unique_id)
)

select
    a.cohort_month,
    a.months_since_first_purchase,
    s.cohort_size,
    count(*)                         as active_customers,
    count(*) / s.cohort_size         as retention_rate
from activity a
join cohort_sizes s using (cohort_month)
group by 1, 2, 3
