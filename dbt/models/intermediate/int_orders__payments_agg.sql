-- One row per order: total paid, and the payment method that covered most of it.
with payments as (
    select * from {{ ref('stg_olist__order_payments') }}
),

by_type as (
    select order_id, payment_type, sum(payment_value) as type_value
    from payments
    group by 1, 2
),

primary_type as (
    select order_id, payment_type as primary_payment_type
    from by_type
    qualify row_number() over (partition by order_id order by type_value desc, payment_type) = 1
)

select
    p.order_id,
    sum(p.payment_value)            as payment_value,
    count(*)                        as payment_count,
    count(distinct p.payment_type)  as payment_method_count,
    max(p.installments)             as max_installments,
    any_value(t.primary_payment_type) as primary_payment_type
from payments p
join primary_type t using (order_id)
group by p.order_id
