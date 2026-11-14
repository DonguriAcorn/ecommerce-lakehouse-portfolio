{# dbt が「モデルをどの Glue DB に作るか」を決めるときに呼ぶ関数を上書きする #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {# +schema の指定がなければ、profiles.yml の既定(ecom_dev_silver)。Silver はこちら #}
        {{ target.schema }}
    {%- else -%}
        {# 指定があれば ecom_<環境>_<指定名>。Gold の +schema: gold は ecom_dev_gold になる #}
        ecom_{{ target.name }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
