-- Silver の products: 商品ごとに1行(マスタ。2016-09-04 にだけ届く)
-- 列名の綴りの誤り _lenght は、元データのまま(Bronze と同じ綴りでないと読めない)
-- カテゴリが空の商品(610 件)は、ここでは直さない。名前の補い方は Gold で決める
-- 窓・merge・full_refresh=false・パーティションなしの考え方は order_items.sql と同じ
{% set keys = ['product_id'] %}

{{ config(
    incremental_strategy='merge',
    unique_key=keys,
    full_refresh=false
) }}

-- 共通の部品で、キーごとに最後に届いた1行にする
{{ silver_latest(
    'products',
    keys=keys,
    columns=['product_id', 'product_category_name', 'product_name_lenght',
             'product_description_lenght', 'product_photos_qty', 'product_weight_g',
             'product_length_cm', 'product_height_cm', 'product_width_cm']
) }}
