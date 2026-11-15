-- 注文の売上の合計と、明細の売上の合計が一致するかを確かめる(2つの表を比べるため、列の下には書けない)
-- 違いがあるときだけ1行を返す。dbt は「1行でも返れば失敗」と判定する
select
    o.total_orders,                                   -- 注文の側の合計(fact_orders.order_amount)
    i.total_items                                     -- 明細の側の合計(fact_order_items.item_amount)
from (select sum(order_amount) as total_orders from {{ ref('fact_orders') }}) as o
cross join (select sum(item_amount) as total_items from {{ ref('fact_order_items') }}) as i
where abs(o.total_orders - i.total_items) > 0.005    -- 1セント未満の違いは、丸めの誤差として許す
