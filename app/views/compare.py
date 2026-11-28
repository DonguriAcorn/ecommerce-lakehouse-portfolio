"""期間比較の画面: 選んだ月の前月比と前年同月比、年ごとの月別推移の重ね合わせ。

比較の計算(前の月の探し方、伸び率)は semantic の query_metric_changes() が行う。
この画面は、選んだ月の行を取り出して並べるだけ。上のサマリーは決まった文型で作る(AI は使わない)。
"""

import altair as alt
import pandas as pd
import streamlit as st
from common import (
    changes,
    chart_heading,
    comparable_months,
    label,
    metric,
    render_header,
    render_summary,
    render_terms,
    states_by_gmv,
)

from semantic.metrics import shift_period

METRICS = ["gmv", "orders", "aov"]  # この画面で比べる指標(売上、注文数、平均注文額)

summary_box = render_header(
    "期間比較",
    "**選んだ月が、前の月や1年前の同じ月と比べてどう変わったか**を見る画面です。",
)
render_terms(
    [
        "**前月比**: 当月 ÷ 前の月 − 1。季節の影響(年末の山など)を受ける。",
        "**前年同月比**: 当月 ÷ 1年前の同じ月 − 1。季節の影響が消えるので、"
        "事業が伸びているかを見るのに向いている。",
        "**売上 = 注文数 × 平均注文額** なので、売上の変化は「件数の変化」と"
        "「1件あたりの金額の変化」"
        "に分けて読める。",
        "**選べる月**: 注文の少なすぎる月(いちばん多い月の1割未満。2016-09、2016-10、2016-12、"
        "2018-09)は選べず、比べる相手にもしない。注文が数件の月と比べると、"
        "+697,878% のような意味のない伸び率になるため。比べられないところは「—」。",
    ]
)

# ---- 絞り込み(月と州) ----
# 比べる意味のある月だけを選択肢にする(決め方は common.comparable_months())
months = comparable_months()
col_month, col_state = st.columns([1, 3])
# 最初は、比べられる最後の月(2018-08)を選んでおく
month = col_month.selectbox("月", months, index=len(months) - 1)
selected_states = col_state.multiselect("州(空なら全国)", states_by_gmv())
state_text = "、".join(selected_states) if selected_states else "全国"

# 州だけで絞る(時間で絞ると前月・前年同月が消えるので、月は後から取り出す)
where = (("customer_state", tuple(selected_states)),) if selected_states else ()


def fmt(name: str, value: float) -> str:
    """指標の値を表示用の文字にする(空なら —)。"""
    if pd.isna(value):
        return "—"
    if name == "orders":
        return f"{value:,.0f} 件"
    if name == "gmv":
        return f"R$ {value:,.0f}"
    return f"R$ {value:,.2f}"  # 平均注文額は小数2桁まで


def pct(value: float) -> str | None:
    """伸び率を +12.3% の形にする(空なら None。st.metric は None なら矢印を出さない)。"""
    return None if pd.isna(value) else f"{value:+.1%}"


# 各指標の、選んだ月の1行(当月、前月、前年同月、変化)
rows = {}
for name in METRICS:
    df = changes(name, where=where)
    hit = df[df["year_month"] == month]
    rows[name] = hit.iloc[0].copy() if not hit.empty else None
    if rows[name] is None:
        continue
    # 比べる相手(前月、前年同月)が、注文の少なすぎる月なら、比較を空にする
    for n, prev_col, change_col in [(1, "prev_period", "change_prev_period"),
                                    (12, "prev_year", "change_prev_year")]:
        if shift_period(month, "month", n) not in months:
            rows[name][prev_col] = rows[name][change_col] = float("nan")


# ---- カード(当月の値と前月比。前年同月比は下に小さく) ----
cards = st.columns(len(METRICS))
for card, name in zip(cards, METRICS):
    row = rows[name]
    if row is None:  # この月・州に注文がない
        card.metric(label(name), "—")
        continue
    card.metric(label(name), fmt(name, row[name]), delta=pct(row["change_prev_period"]),
                help="矢印は前月比")
    yoy = pct(row["change_prev_year"])
    card.caption(f"前年同月比 {yoy}" if yoy else "前年同月比 —(前年同月のデータなし)")


# ---- 比較表 ----
chart_heading(
    f"{month} の比較",
    "選んだ月の値を、前の月・1年前の同じ月の値と横に並べた表です。"
    "「比」は、当月が比べる月より何% 多いか(マイナスなら少ないか)を表します。",
)
table = pd.DataFrame(
    [
        {
            "指標": label(name),
            "当月": fmt(name, rows[name][name]),
            "前月": fmt(name, rows[name]["prev_period"]),
            "前月比": pct(rows[name]["change_prev_period"]) or "—",
            "前年同月": fmt(name, rows[name]["prev_year"]),
            "前年同月比": pct(rows[name]["change_prev_year"]) or "—",
        }
        for name in METRICS
        if rows[name] is not None
    ]
)
st.dataframe(table, hide_index=True)


# ---- 年ごとの月別推移の重ね合わせ(前年同月の比較を目で見る) ----
chart_heading(
    "年ごとの月別推移",
    "横軸が1〜12月、線の色が年です。同じ月の縦の位置を比べると、1年前より増えたか減ったかが"
    "見えます(線の間が開いているほど、前年同月比が大きい)。"
    "2016年は9〜12月だけ、2018年は8月までが比べられる範囲です。",
)
name = st.radio("指標", METRICS, format_func=label, horizontal=True)
monthly = metric(name, grain="month", where=where)
# 2017-11 → 年 2017、月 11 に分けて、年ごとの線にする(表示のための並べ替え。計算はしない)
monthly["年"] = monthly["year_month"].str[:4]
monthly["月"] = monthly["year_month"].str[5:7].astype(int)
chart = (
    alt.Chart(monthly)
    .mark_line(point=True)
    .encode(
        x=alt.X("月:O", title="月"),  # O: 順序のある値(1〜12 を等間隔に並べる)
        y=alt.Y(f"{name}:Q", title=label(name)),
        color=alt.Color("年:N", title="年"),  # 年ごとに色を変える
        tooltip=["year_month", alt.Tooltip(f"{name}:Q", format=",.2f")],
    )
)
st.altair_chart(chart, width="stretch")


# ---- サマリー(画面の上の箱に書く) ----
def driver(orders_change: float, aov_change: float) -> str:
    """売上の変化が、件数と1件あたりの金額のどちらによるかを、決まった基準で言葉にする。

    基準: 片方の変化の大きさが、もう片方の 1/3 未満なら「主に大きい方による」。
    売上 = 注文数 × 平均注文額 なので、売上の変化はこの2つに分けられる。
    """
    o, a = abs(orders_change), abs(aov_change)
    if a < o / 3:
        return "主に**注文の件数**の変化によるもの"
    if o < a / 3:
        return "主に**1件あたりの金額**の変化によるもの"
    return "**注文の件数と1件あたりの金額の両方**の変化によるもの"


lines = []
g, o, a = rows["gmv"], rows["orders"], rows["aov"]
if g is not None:
    mom, yoy = pct(g["change_prev_period"]), pct(g["change_prev_year"])
    lines.append(
        f"{month}・{state_text}の売上は **{fmt('gmv', g['gmv'])}**。"
        f"前年同月比 **{yoy or '—'}**、前月比 {mom or '—'}。"
    )
    # 前年同月と比べられれば前年同月で、なければ前月で、変化の中身を分ける
    for col, word in [("change_prev_year", "前年同月"), ("change_prev_period", "前月")]:
        if not pd.isna(g[col]) and not pd.isna(o[col]) and not pd.isna(a[col]):
            lines.append(
                f"{word}と比べた売上の変化は、{driver(o[col], a[col])}"
                f"(注文数 {pct(o[col])}、平均注文額 {pct(a[col])})。"
            )
            break
render_summary(summary_box, lines)
