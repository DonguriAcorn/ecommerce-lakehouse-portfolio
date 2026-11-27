-- 公開用: 月 × 州の売上と注文数(ADR 0018)。アプリへ export する
-- 平均注文額は出さない(州をまたいで集めると「平均の平均」になるため、アプリが gmv / orders で出す)
-- 置き場所と作り方(ecom_<環境>_gold、table、Iceberg)は、dbt_project.yml の gold の設定が効く

select
    date_format(f.purchase_date, '%Y-%m')   as year_month,       -- 月(例: 2017-11)
    d.customer_state,                                            -- 購入した時点の州(SCD2 の行から引く)
    cast(sum(f.order_amount) as decimal(38, 2)) as gmv,          -- 売上(商品代金 + 送料)。型は contract に合わせて固定
    count(*)                                as orders            -- 注文数(1行 = 1注文)
from {{ ref('fact_orders') }} as f
join {{ ref('dim_customer') }} as d                              -- customer_sk で結ぶと、引っ越しの前後で正しい州になる
    on f.customer_sk = d.customer_sk
where f.is_counted                                               -- canceled と unavailable を除く
group by 1, 2
