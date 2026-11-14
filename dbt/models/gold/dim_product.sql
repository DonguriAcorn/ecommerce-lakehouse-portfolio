-- 商品の表(1行 = 1商品)。カテゴリ名は 英訳 → 元の名前 → unknown の順(ADR 0011)
select
    p.product_id,                                           -- 商品の ID(主キー)
    coalesce(                                               -- 左から順に、空でない最初の値
        t.product_category_name_english,                    -- ① 英訳(英訳のないカテゴリは空になる)
        nullif(trim(p.product_category_name), ''),          -- ② 元の名前(空文字は空として扱う)
        'unknown'                                           -- ③ どちらもなければ unknown(商品 610 件)
    ) as category_name
from {{ ref('products') }} as p                             -- Silver の商品(ref は dbt のモデルの参照)
left join {{ ref('product_category_name_translation') }} as t   -- 英訳の表。left で商品を落とさない
    on p.product_category_name = t.product_category_name
