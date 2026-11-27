-- 公開用の集計が、元の Gold と合っているかを確かめる(ADR 0018)
-- 3つの確認のどれかが外れたときだけ、その行を返す。dbt は「1行でも返れば失敗」と判定する

-- 1. pub_kpi_monthly の売上の合計 = fact_orders の数える注文の売上の合計
select 'kpi_gmv' as check_name
from (select sum(gmv) as v from {{ ref('pub_kpi_monthly') }}) as p
cross join (select sum(order_amount) as v from {{ ref('fact_orders') }} where is_counted) as g
where abs(coalesce(p.v, 0) - coalesce(g.v, 0)) > 0.005   -- 1セント未満の違いは、丸めの誤差として許す

union all

-- 2. pub_category_monthly の売上の合計 = fact_order_items の数える明細の売上の合計
select 'category_gmv' as check_name
from (select sum(gmv) as v from {{ ref('pub_category_monthly') }}) as p
cross join (select sum(item_amount) as v from {{ ref('fact_order_items') }} where is_counted) as g
where abs(coalesce(p.v, 0) - coalesce(g.v, 0)) > 0.005

union all

-- 3. リピートの人数が、買った人数を超えない(1行でも超えたら失敗)
select 'repeat_le_buyers' as check_name
from {{ ref('pub_repeat_monthly') }}
where repeat_buyers > buyers
