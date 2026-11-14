-- 日付の表(1行 = 1日)。期間の比較(月、四半期、前年同月)の切り口になる
-- Olist の購入日は 2016-09-04〜2018-10-18。前年比のため、2016〜2018 の年の全体を作る
select
    d                                       as date_key,        -- 日付そのもの(主キー)
    year(d)                                 as year,            -- 年
    month(d)                                as month,           -- 月(1〜12)
    date_format(d, '%Y-%m')                 as year_month,      -- 年月(例: 2017-11。月別の集計の見出し)
    quarter(d)                              as quarter,         -- 四半期(1〜4)
    day_of_week(d)                          as day_of_week      -- 曜日(1 = 月曜 … 7 = 日曜)
from unnest(                                -- 配列を1行ずつに広げる
    sequence(date '2016-01-01', date '2018-12-31', interval '1' day)  -- 1日刻みの日付の配列
) as t(d)                                   -- 広げた列の名前を d にする
