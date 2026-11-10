-- The most recent reconciliation check for every (business date, table) must
-- be a MATCH: dbt refuses to build on top of an incomplete or duplicated load.
select *
from {{ source('audit', 'load_reconciliation') }}
qualify row_number() over (partition by business_date, table_name order by checked_at desc) = 1
    and status != 'MATCH'
