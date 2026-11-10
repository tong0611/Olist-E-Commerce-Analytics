{#- Lineage columns carried from RAW into every staging model. -#}
{% macro raw_metadata() -%}
    raw_data:_batch_id::string      as _batch_id,
    raw_data:_business_date::date   as _business_date,
    _source_file,
    _file_row_number,
    _file_last_modified,
    _loaded_at
{%- endmacro %}
