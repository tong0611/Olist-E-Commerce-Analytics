with days as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2016-01-01' as date)",
        end_date="cast('2019-01-01' as date)"
    ) }}
)

select
    date_day::date                          as date_day,
    year(date_day)                          as year,
    quarter(date_day)                       as quarter,
    month(date_day)                         as month,
    monthname(date_day)                     as month_name,
    date_trunc('month', date_day)::date     as month_start,
    to_char(date_day, 'YYYY-MM')            as year_month,
    weekofyear(date_day)                    as week_of_year,
    dayofweekiso(date_day)                  as day_of_week,
    dayname(date_day)                       as day_name,
    dayofweekiso(date_day) in (6, 7)        as is_weekend
from days
