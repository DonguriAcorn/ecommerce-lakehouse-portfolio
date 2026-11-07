-- Silver の customers: 顧客(注文ごとの顧客 ID)ごとに1行
-- マスタなので 2016-09-04 にだけ届く。ほかの日の窓では0件で、変化 0 になる(それで正しい)
-- 窓・merge・full_refresh=false・パーティションなしの考え方は order_items.sql と同じ
{% set keys = ['customer_id'] %}

{{ config(
    incremental_strategy='merge',
    unique_key=keys,
    full_refresh=false
) }}

-- 共通の部品で、キーごとに最後に届いた1行にする
{{ silver_latest(
    'customers',
    keys=keys,
    columns=['customer_id', 'customer_unique_id', 'customer_zip_code_prefix',
             'customer_city', 'customer_state']
) }}
