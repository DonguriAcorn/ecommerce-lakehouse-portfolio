-- Silver のカテゴリの英訳: カテゴリ(ポルトガル語の名前)ごとに1行(マスタ。2016-09-04 にだけ届く)
-- 英訳がないカテゴリが2つある(pc_gamer など)。ここでは足さず、Gold で「英訳 → 元の名前 → unknown」にする
-- 窓・merge・full_refresh=false・パーティションなしの考え方は order_items.sql と同じ
{% set keys = ['product_category_name'] %}

{{ config(
    incremental_strategy='merge',
    unique_key=keys,
    full_refresh=false
) }}

-- 共通の部品で、キーごとに最後に届いた1行にする
{{ silver_latest(
    'product_category_name_translation',
    keys=keys,
    columns=['product_category_name', 'product_category_name_english']
) }}
