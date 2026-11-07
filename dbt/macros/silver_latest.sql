-- Silver の共通の部品: Bronze の1表を、キーごとに「最後に届いた1行」にして返す
-- 追記型(order_items、reviews)とマスタ(customers など)の6表で使う。orders は出来事を畳むので使わない
-- 引数: table_name = Bronze の表の名前、keys = 1行を見分ける列、columns = 業務の列(並び順のまま)
-- {{ }} や {% %} の中は Jinja なので、コメント(--)は外に書く
{% macro silver_latest(table_name, keys, columns) %}

-- 窓(start_date 〜 end_date)に届いた行を読む。var() に既定値がないので、渡し忘れるとエラー
with windowed as (
    select *
    from {{ source('bronze', table_name) }}
    where ingest_date between '{{ var("start_date") }}' and '{{ var("end_date") }}'
),

-- 同じキーが窓の中に2回以上あれば(同じ行の再送など)、届いた日が新しい順に番号を振る
ranked as (
    select
        *,
        row_number() over (
            partition by {{ keys | join(', ') }}
            order by ingest_date desc, _ingested_at desc
        ) as rn
    from windowed
),

-- キーごとに1番(最新)だけを残し、列をそろえる(Bronze の ingest_date と作業用の rn は出さない)
latest as (
    select
        {{ columns | join(',\n        ') }},
        -- この行が届いた日。古い情報で上書きしないガードに使う(orders と同じ列名)
        cast(ingest_date as date) as _last_ingest_date,
        -- 監査カラム: この行を Raw に書いたときの値をそのまま残す
        _ingested_at,
        _source_file,
        _batch_id
    from ranked
    where rn = 1
)

select l.*
from latest as l
{% if is_incremental() %}
-- Silver にすでにテーブルがあるときだけ、古い情報で上書きしないよう絞る
-- キーの列ごとに「l.列 = t.列」を作り、and でつなぐ(キーが2列の表もあるため)
left join {{ this }} as t
    on {% for key in keys %}l.{{ key }} = t.{{ key }}{% if not loop.last %} and {% endif %}{% endfor %}
-- 通すのは、Silver にまだないキーか、Silver より新しく届いた行だけ(同じ日の再実行は変化 0)
where t.{{ keys[0] }} is null or l._last_ingest_date > t._last_ingest_date
{% endif %}

{% endmacro %}
