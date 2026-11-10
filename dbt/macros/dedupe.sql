{#- Keep one row per key: the version from the most recently written file.
    RAW can hold several copies of a row when a business date is re-extracted
    (overwritten file -> new ETag -> reloaded by COPY) or when snapshot
    dimensions are extracted on more than one day. -#}
{% macro dedupe(partition_by) -%}
qualify row_number() over (
    partition by {{ partition_by }}
    order by _file_last_modified desc, _loaded_at desc, _file_row_number desc
) = 1
{%- endmacro %}
