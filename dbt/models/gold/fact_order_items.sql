-- 明細の表(1行 = 注文の1明細)。売上とランキングは、ここから数える
-- 注文の列(顧客、日付、状態)は fact_orders から借りる(結びつけの計算を1か所にするため)

select
    i.order_id,                                              -- 注文の ID(キーの1列目)
    i.order_item_id,                                         -- 明細の番号(キーの2列目)
    i.product_id,                                            -- 商品(dim_product とつなぐ)
    i.seller_id,                                             -- 出品者の ID(キーとして持つだけ)
    f.customer_sk,                                           -- 注文の時点の顧客(dim_customer とつなぐ)
    f.purchase_date,                                         -- 購入日(dim_date とつなぐ)
    f.order_status,                                          -- 注文の状態
    f.is_counted,                                            -- 売上に数えるか
    i.price,                                                 -- 商品代金
    i.freight_value,                                         -- 送料
    i.price + i.freight_value as item_amount                 -- 明細の売上(商品代金 + 送料)
from {{ ref('order_items') }} as i
join {{ ref('fact_orders') }} as f                           -- 注文の列を借りる
    on i.order_id = f.order_id
