-- 毎日届く3表が、Airflow の target_date(end_date)の分まで届いているかを確かめる
-- 古い表があるときだけ、その表を1行ずつ返す。dbt は「1行でも返れば失敗」と判定する
{% if var('end_date', none) is none %}
    -- 日付が渡されていない(手元の dbt test など)ときは、何も調べずに 0 行を返す(PASS)
    select cast(null as varchar) as table_name, cast(null as date) as latest_ingest_date
    where false
{% else %}
    select table_name, latest_ingest_date
    from (
        select 'orders_from_events' as table_name, max(_last_ingest_date) as latest_ingest_date
        from {{ ref('orders_from_events') }}
        union all
        select 'order_items', max(_last_ingest_date) from {{ ref('order_items') }}
        union all
        select 'reviews', max(_last_ingest_date) from {{ ref('reviews') }}
    )
    -- 最新の届いた日が、target_date より前(または空)なら、その表は古い
    where latest_ingest_date is null
       or latest_ingest_date < cast('{{ var("end_date") }}' as date)
{% endif %}
