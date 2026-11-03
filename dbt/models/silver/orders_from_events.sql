-- Silver の orders: Bronze の出来事(1注文に複数行)を、注文ごとの「いまの状態」(1注文1行)に畳む
-- Iceberg・Parquet・zstd・incremental は、dbt_project.yml の silver の設定で指定している
-- 実行時に --vars '{start_date: "YYYY-MM-DD", end_date: "YYYY-MM-DD"}' で窓(届いた日の範囲)を渡す

-- config の中は SQL でなく Jinja なので、コメントは外に書く(中に -- を書くと構文エラーになる)
-- incremental_strategy='merge': 既存の行は更新、新しい行は追加する(MERGE)
-- unique_key='order_id': 「同じ注文」を見分けるキー
-- partitioned_by: 購入月ごとに分ける(購入日時は変わらないので、行が月をまたいで動かない)
-- full_refresh=false: --full-refresh を付けても作り直さない(DROP でデータが消える事故を防ぐ)
{{ config(
    incremental_strategy='merge',
    unique_key='order_id',
    partitioned_by=['month(order_purchase_timestamp)'],
    full_refresh=false
) }}

-- 窓(start_date 〜 end_date)に届いた出来事がある注文を選ぶ
-- var() に既定値を付けていないので、渡し忘れるとエラーになる(全期間を処理する事故を防ぐ)
with window_orders as (
    select distinct order_id
    from {{ source('bronze', 'orders_events') }}
    where ingest_date between '{{ var("start_date") }}' and '{{ var("end_date") }}'
),

-- その注文の全出来事を読む(開始日の制限はなし。終了日より後に届いたものは読まない)
-- 終了日で切るので、同じ窓の再実行は、いつ流しても同じ結果になる
events as (
    select e.*
    from {{ source('bronze', 'orders_events') }} as e
    inner join window_orders as w on e.order_id = w.order_id
    where e.ingest_date <= '{{ var("end_date") }}'
),

-- 注文ごとに、順位が大きい順(同じなら時刻が新しい順)に番号を振る。1番が最新の出来事
-- 時刻の逆転がある注文が実際にあるため、順位を先にして、時刻は同順位のときだけ使う
ranked as (
    select
        *,
        row_number() over (
            partition by order_id
            order by event_rank desc, event_time desc
        ) as rn
    from events
),

-- 注文ごとに1行へ畳む
folded as (
    select
        order_id,
        -- 注文の変わらない属性は、どの行にも同じ値が入っているので max で1つ取る
        max(customer_id) as customer_id,
        -- 状態は、最新の出来事(rn = 1)の order_status
        max(order_status) filter (where rn = 1) as order_status,
        max(order_purchase_timestamp) as order_purchase_timestamp,
        -- 出来事の種類ごとの時刻を横に並べる。その出来事がなければ NULL(元の CSV の空欄と同じ)
        max(event_time) filter (where event_type = 'approved')  as order_approved_at,
        max(event_time) filter (where event_type = 'shipped')   as order_delivered_carrier_date,
        max(event_time) filter (where event_type = 'delivered') as order_delivered_customer_date,
        max(order_estimated_delivery_date) as order_estimated_delivery_date,
        -- その注文の出来事が最後に届いた日。古い情報で上書きしないためのガードに使う
        cast(max(ingest_date) as date) as _last_ingest_date
    from ranked
    group by order_id
)

select f.*
from folded as f
{% if is_incremental() %}
-- Silver にすでにテーブルがあるときだけ、古い情報で上書きしないよう絞る
left join {{ this }} as t on f.order_id = t.order_id
-- 通すのは、Silver にまだない注文か、Silver より新しく届いた注文だけ(同じ日の再実行は変化 0)
where t.order_id is null or f._last_ingest_date > t._last_ingest_date
{% endif %}
