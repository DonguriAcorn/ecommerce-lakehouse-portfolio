-- Silver の order_items: 明細ごとに1行(キーは 注文 ID + 明細の番号)
-- 実行時に --vars '{start_date: "YYYY-MM-DD", end_date: "YYYY-MM-DD"}' で窓(届いた日の範囲)を渡す
-- incremental_strategy='merge': 同じキーの行は更新、新しいキーは追加する
-- full_refresh=false: --full-refresh を付けても作り直さない(データが消える事故を防ぐ)
-- パーティションは付けない(表が小さく、日付で絞る場面も少ないため)
-- キーは1か所に書き、config(merge の照合)とマクロ(重複除き、ガードの結合)の両方で使う
{% set keys = ['order_id', 'order_item_id'] %}

{{ config(
    incremental_strategy='merge',
    unique_key=keys,
    full_refresh=false
) }}

-- 共通の部品(macros/silver_latest.sql)で、キーごとに最後に届いた1行にする
{{ silver_latest(
    'order_items',
    keys=keys,
    columns=['order_id', 'order_item_id', 'product_id', 'seller_id',
             'shipping_limit_date', 'price', 'freight_value']
) }}
