-- Silver の sellers: 出品者ごとに1行(マスタ。2016-09-04 にだけ届く)
-- 窓・merge・full_refresh=false・パーティションなしの考え方は order_items.sql と同じ
{% set keys = ['seller_id'] %}

{{ config(
    incremental_strategy='merge',
    unique_key=keys,
    full_refresh=false
) }}

-- 共通の部品で、キーごとに最後に届いた1行にする
{{ silver_latest(
    'sellers',
    keys=keys,
    columns=['seller_id', 'seller_zip_code_prefix', 'seller_city', 'seller_state']
) }}
