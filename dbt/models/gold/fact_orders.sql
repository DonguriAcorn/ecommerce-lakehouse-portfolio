-- 注文の表(1行 = 1注文)。注文数とリピート率は、ここから数える
-- 明細のない注文(キャンセルなど)も残す。そのときの金額は 0、明細数は 0

with items as (                                              -- 注文ごとの明細の集計(1注文 = 1行にしてから結合する)
    select
        order_id,
        count(*)                       as item_count,        -- 明細の数
        sum(price + freight_value)     as order_amount       -- 商品代金 + 送料の合計
    from {{ ref('order_items') }}
    group by order_id
),

latest_review as (                                           -- 注文ごとの、最後に答えたレビューの星
    select
        order_id,
        max_by(review_score, review_answer_timestamp) as review_score  -- 答えた日時が最新の行の星
    from {{ ref('reviews') }}
    group by order_id
)

select
    o.order_id,                                              -- 注文の ID(主キー)
    o.customer_id,                                           -- 注文ごとの顧客 ID
    c.customer_unique_id,                                    -- 本人の ID(リピートの判定に使う)
    d.customer_sk,                                           -- その注文の時点の、顧客の期間の行
    cast(o.order_purchase_timestamp as date) as purchase_date,   -- 購入日(dim_date とつなぐ)
    o.order_status,                                          -- 注文の状態
    o.order_status not in ('canceled', 'unavailable') as is_counted,  -- 売上に数えるか(設計書の決定)
    coalesce(i.item_count, 0)    as item_count,              -- 明細なしは 0
    coalesce(i.order_amount, 0)  as order_amount,            -- 明細なしは 0
    r.review_score                                           -- レビューのない注文は空
from {{ ref('orders_from_events') }} as o
join {{ ref('customers') }} as c
    on o.customer_id = c.customer_id
join {{ ref('dim_customer') }} as d                          -- 購入日時が入る期間の1行を引く
    on c.customer_unique_id = d.customer_unique_id
   and o.order_purchase_timestamp >= d.valid_from            -- 期間の始まり(含む)
   and (d.valid_to is null or o.order_purchase_timestamp < d.valid_to)  -- 期間の終わり(含まない)
left join items as i                                         -- 明細のない注文を落とさない
    on o.order_id = i.order_id
left join latest_review as r                                 -- レビューのない注文を落とさない
    on o.order_id = r.order_id
