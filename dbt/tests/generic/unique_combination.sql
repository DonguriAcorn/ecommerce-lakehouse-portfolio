-- 自作の汎用テスト: 指定した列の組が、表の中で重複していないかを確かめる
-- キーが2列の表(order_items、reviews)で使う。1列のキーは dbt 標準の unique を使う
-- 重複した組を返す。dbt は「1行でも返れば失敗」と判定する
{% test unique_combination(model, columns) %}

select
    {{ columns | join(', ') }},
    count(*) as n_rows
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1

{% endtest %}
