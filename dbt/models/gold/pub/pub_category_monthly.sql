-- 公開用: 月 × カテゴリの売上、販売数、平均の星(ADR 0018)。商品ランキングの画面に使う
-- 商品単位(product_id)は出さない。v1.0 のランキングはカテゴリ単位

select
    date_format(i.purchase_date, '%Y-%m')   as year_month,       -- 月
    p.category_name,                                             -- カテゴリ名(英訳 → 元の名前 → unknown)
    cast(sum(i.item_amount) as decimal(38, 2)) as gmv,           -- 売上(明細の商品代金 + 送料)
    count(*)                                as items_sold,       -- 販売数(1行 = 1明細)
    cast(round(avg(o.review_score), 2) as double) as avg_review_score, -- 平均の星。明細ごとに注文の星を数える(レビューのない注文は avg が無視する)
    -- 平均の星を、月やカテゴリをまたいで正しく出すための材料(平均の平均にしないため)
    -- アプリは sum(review_score_sum) / sum(reviewed_items) で出す
    cast(coalesce(sum(o.review_score), 0) as bigint) as review_score_sum, -- 星の合計(レビューのない明細は数えない。全部ない組は 0)
    count(o.review_score)                   as reviewed_items    -- 星のある明細の数(count(列) は空を数えない)
from {{ ref('fact_order_items') }} as i
join {{ ref('dim_product') }} as p                               -- カテゴリを引く
    on i.product_id = p.product_id
join {{ ref('fact_orders') }} as o                               -- 注文の星を引く(1明細に1注文なので行は増えない)
    on i.order_id = o.order_id
where i.is_counted                                               -- canceled と unavailable を除く
group by 1, 2
