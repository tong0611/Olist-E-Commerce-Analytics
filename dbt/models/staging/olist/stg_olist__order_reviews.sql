-- review_id is not unique in the source: the same review can be attached to
-- several orders. The grain here is (review_id, order_id).
with source as (
    select * from {{ source('olist', 'order_reviews') }}
)

select
    raw_data:review_id::string                       as review_id,
    raw_data:order_id::string                        as order_id,
    raw_data:review_score::int                       as review_score,
    nullif(trim(raw_data:review_comment_title::string), '')   as comment_title,
    nullif(trim(raw_data:review_comment_message::string), '') as comment_message,
    raw_data:review_creation_date::timestamp_ntz     as created_at,
    raw_data:review_answer_timestamp::timestamp_ntz  as answered_at,
    {{ raw_metadata() }}
from source
{{ dedupe('raw_data:review_id, raw_data:order_id') }}
