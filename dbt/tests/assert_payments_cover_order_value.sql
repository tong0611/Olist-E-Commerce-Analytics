-- Payment total should be close to merchandise + freight. Olist has a small
-- number of known discrepancies (vouchers, installment interest), so this
-- warns instead of failing, and errors only if the problem grows.
{{ config(severity='error', warn_if='> 0', error_if='> 1000') }}
select order_id, order_value, payment_value
from {{ ref('fct_orders') }}
where is_revenue_order
  and abs(payment_value - order_value) > 1
