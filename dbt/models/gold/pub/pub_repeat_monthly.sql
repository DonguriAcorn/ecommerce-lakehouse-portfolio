-- 公開用: 月 × 州の、買った本人の数と、そのうち全期間で2注文以上の本人の数(ADR 0018)
-- リピート率は、アプリが repeat_buyers / buyers で出す(州をまたいで正しく足せるように、割合ではなく人数で持つ)
-- is_counted では絞らない(用語集の「注文のある本人」のとおり。分母を変えるかは tasks.md の未決)
-- customer_unique_id(ハッシュ)は数えるのに使うだけで、出力の列には出さない

with per_person as (                                             -- 本人ごとの、全期間の注文数
    select
        customer_unique_id,
        count(*) as n_orders
    from {{ ref('fact_orders') }}
    group by 1
)

select
    date_format(f.purchase_date, '%Y-%m')   as year_month,       -- 月
    d.customer_state,                                            -- 購入した時点の州
    count(distinct f.customer_unique_id)    as buyers,           -- その月に買った本人の数
    count(distinct case when p.n_orders >= 2
                        then f.customer_unique_id end) as repeat_buyers  -- うち、全期間で2注文以上の本人
from {{ ref('fact_orders') }} as f
join {{ ref('dim_customer') }} as d                              -- 購入した時点の州
    on f.customer_sk = d.customer_sk
join per_person as p                                             -- 本人ごとの注文数をつなぐ
    on f.customer_unique_id = p.customer_unique_id
group by 1, 2
