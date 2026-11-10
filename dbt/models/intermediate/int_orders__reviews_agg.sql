-- One row per order. A few orders have several reviews: keep the latest score.
with reviews as (
    select * from {{ ref('stg_olist__order_reviews') }}
)

select
    order_id,
    count(*) as review_count,
    max_by(review_score, created_at) as review_score,
    min(created_at)                  as first_reviewed_at,
    boolor_agg(comment_message is not null) as has_review_comment
from reviews
group by order_id
