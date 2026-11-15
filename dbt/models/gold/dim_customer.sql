-- 顧客の表(SCD2)。1行 = 本人(customer_unique_id)の、州と郵便番号が同じだった期間
-- customers は1回しか届かないため snapshot は使えない。注文の購入日時の順から期間を作る(ADR 0015)

with purchases as (                                          -- 1. 注文ごとの「そのときの住所」
    select
        c.customer_unique_id,                                -- 本人の ID
        c.customer_id,                                       -- 注文ごとの顧客 ID(同じ時刻の並びの決め手)
        c.customer_state,                                    -- 州
        c.customer_zip_code_prefix,                          -- 郵便番号の先頭5桁
        c.customer_city,                                     -- 市(履歴は持たず、最新の値を使う)
        o.order_purchase_timestamp as purchased_at           -- 購入日時
    from {{ ref('customers') }} as c
    join {{ ref('orders_from_events') }} as o                -- customer_id は注文ごとに1つなので1対1
        on c.customer_id = o.customer_id
),

flagged as (                                                 -- 2. 前の注文から住所が変わった所に旗(1)を立てる
    select
        *,
        case
            when customer_state is distinct from lag(customer_state) over w
              or customer_zip_code_prefix is distinct from lag(customer_zip_code_prefix) over w
            then 1                                           -- 前と違う(最初の注文は前が空なので、必ず 1)
            else 0
        end as changed
    from purchases
    window w as (partition by customer_unique_id order by purchased_at, customer_id)
),

numbered as (                                                -- 3. 旗を累計して、期間の番号にする
    select
        *,
        sum(changed) over (
            partition by customer_unique_id
            order by purchased_at, customer_id
            rows between unbounded preceding and current row -- 先頭から現在の行まで
        ) as period_no
    from flagged
),

periods as (                                                 -- 4. 期間ごとに1行にまとめる
    select
        customer_unique_id,
        period_no,
        customer_state,                                      -- 期間の中では同じ値
        customer_zip_code_prefix,                            -- 同上
        min(purchased_at) as valid_from                      -- 期間の最初の購入日時
    from numbered
    group by customer_unique_id, period_no, customer_state, customer_zip_code_prefix
),

latest_city as (                                             -- 市は、本人の最新の注文の値
    select
        customer_unique_id,
        max_by(customer_city, purchased_at) as customer_city -- 購入日時が最新の行の市
    from purchases
    group by customer_unique_id
)

select
    to_hex(md5(to_utf8(                                      -- 代理キー: 本人 + 期間の始まりから作る(毎回同じ値)
        p.customer_unique_id || '|' || cast(p.valid_from as varchar)
    ))) as customer_sk,
    {{ pii_hash('p.customer_unique_id') }} as customer_unique_id,  -- 出力だけハッシュにする(customer_sk は上で元の ID から作るので変わらない)
    p.customer_state,
    substr(p.customer_zip_code_prefix, 1, 3) as customer_zip_code_prefix,  -- 先頭3桁に丸める(5桁より戻しにくくする)
    l.customer_city,
    p.valid_from,                                            -- この住所になった最初の購入日時
    lead(p.valid_from) over (                                -- 次の期間の始まり = この期間の終わり
        partition by p.customer_unique_id order by p.valid_from
    ) as valid_to,                                           -- 最後の期間は空
    lead(p.valid_from) over (
        partition by p.customer_unique_id order by p.valid_from
    ) is null as is_current                                  -- 次がなければ、いまの住所
from periods as p
join latest_city as l
    on p.customer_unique_id = l.customer_unique_id
