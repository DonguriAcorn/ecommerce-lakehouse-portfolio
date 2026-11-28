"""リピート率の画面: 年ごとのリピート率、月ごとの推移、州ごとの比較。

リピート率 = その期間に注文した本人のうち、全期間で2注文以上した本人の割合(用語集 repeat_rate)。
人数は重複を除いて数えているので、月を足して年にできない。年の値は年の表(pub_repeat_yearly)から出す。
全期間の値は材料の表がないので出さない(query_metric が止める)。
上のサマリーは決まった文型で作る(AI は使わない)。
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

summary_box = render_header(
    label("repeat_rate"),
    "**一度買った人が、また買ってくれているか**を見る画面です。",
)
render_terms(
    [
        "**リピート率**: その期間に注文した人のうち、全期間(2016-09〜2018-10)で2回以上"
        "注文した人の割合。",
        "**人の数え方**: Olist は注文ごとに顧客の ID を振り直すので、同じ人を表す別の ID "
        "(customer_unique_id)で数える。キャンセルした注文も「注文した」に含める。",
        "**全体として低い理由**: Olist はいろいろな店が出品するマーケットプレイスで、"
        "1回だけ買う人が大半。リピート率が数% なのは、このデータの特徴。",
        "**後の年ほど低く出る**: 後に初めて買った人ほど、データの終わり(2018-10)までに"
        "2回目を買う時間が短いため。年の比較は、この点を割り引いて読む。",
        "**年の値は月の値を足していない**: 月ごとの人数を足すと、何か月も買った人を二重に数える。"
        "年の値は、年の中で人を数え直した表から出す。同じ理由で、全期間のリピート率は出さない。",
    ]
)

# ---- 絞り込み(州) ----
selected_states = st.multiselect("州(空なら全国)", states_by_gmv())
where = (("customer_state", tuple(selected_states)),) if selected_states else ()
state_text = "、".join(selected_states) if selected_states else "全国"


# ---- 年ごとのカード(前年との差はポイント) ----
chart_heading(
    "年ごとのリピート率",
    "その年に注文した人のうち、何% が全期間で2回以上注文したかです。矢印は前年との差"
    "(ポイント = % どうしの引き算)、下の人数はその年に注文した人の数です。",
)
yearly = changes("repeat_rate", grain="year", where=where)
yearly_buyers = metric("buyers", grain="year", where=where)
yearly = yearly.merge(yearly_buyers, on="year")  # 何人の上での割合かを並べて見せる

cards = st.columns(len(yearly))
for card, (_, row) in zip(cards, yearly.iterrows()):
    # 差は割合の差(0.0432 - 0.0428 = +0.0004 → +0.04 ポイント)
    diff = row["change_prev_year"]
    delta = None if pd.isna(diff) else f"{diff * 100:+.2f} ポイント"
    card.metric(f"{row['year']}年", f"{row['repeat_rate']:.2%}", delta=delta,
                help="矢印は前年との差")
    card.caption(f"{label('buyers')} {row['buyers']:,.0f} 人")


# ---- 月ごとの推移 ----
chart_heading(
    "月ごとの推移",
    "各月に注文した人のうち、全期間で2回以上注文した人の割合を、月ごとに並べた線です。"
    "後の月に買った人ほど、2回目を買う時間がデータの中で短いので、右に行くほど下がりやすくなります。"
    "注文の少なすぎる月(データの端)は、割合が大きく振れるので描いていません。",
)
monthly = metric("repeat_rate", grain="month", where=where)
monthly = monthly[monthly["year_month"].isin(comparable_months())]
chart = (
    alt.Chart(monthly)
    .mark_line(point=True)
    .encode(
        x=alt.X("year_month:O", title="月"),
        y=alt.Y("repeat_rate:Q", title=label("repeat_rate"), axis=alt.Axis(format="%")),
        tooltip=["year_month", alt.Tooltip("repeat_rate:Q", format=".2%")],
    )
)
st.altair_chart(chart, width="stretch")


# ---- 州ごとの比較 ----
chart_heading(
    "州ごとのリピート率",
    "選んだ年に注文した人のリピート率を、州ごとに高い順に並べた棒です(上の州の絞り込みは"
    "ここには効きません)。購入者が少ない州は数人の違いで割合が大きく動くので、"
    "購入者が下限以上の州だけを出しています。棒にマウスを乗せると人数が出ます。",
)
years = metric("buyers", grain="year")["year"].tolist()
col_year, col_min = st.columns(2)
year = col_year.selectbox("年", years, index=len(years) - 2)  # 最初は 2017 年(1年分そろった年)
min_buyers = col_min.number_input("購入者数がこの人数以上の州だけ", min_value=0, value=100, step=50)

year_where = (("year", year),)
by_state = metric("repeat_rate", grain="year", by=("customer_state",), where=year_where).merge(
    metric("buyers", grain="year", by=("customer_state",), where=year_where),
    on=["year", "customer_state"],
)
by_state = by_state[by_state["buyers"] >= min_buyers].sort_values("repeat_rate", ascending=False)

chart = (
    alt.Chart(by_state)
    .mark_bar()
    .encode(
        x=alt.X("repeat_rate:Q", title=label("repeat_rate"), axis=alt.Axis(format="%")),
        y=alt.Y("customer_state:N", sort="-x", title="州"),  # 割合の高い順
        tooltip=[
            "customer_state",
            alt.Tooltip("repeat_rate:Q", format=".2%"),
            alt.Tooltip("buyers:Q", title=label("buyers"), format=","),
        ],
    )
)
st.altair_chart(chart, width="stretch")
st.caption(f"{year}年に注文した人が {min_buyers} 人以上の州: {len(by_state)} 州。")


# ---- サマリー(画面の上の箱に書く) ----
def rate_with_people(row: pd.Series) -> str:
    """「4.32%(43,726 人中)」の形にする。"""
    return f"{row['repeat_rate']:.2%}({row['buyers']:,.0f} 人中)"


lines = []
# 1年分そろった年(2017)と、その次の年(2018)を比べる
full = yearly[yearly["year"] == "2017"]
if not full.empty:
    lines.append(
        f"{state_text}で 2017年に注文した人のリピート率は **{rate_with_people(full.iloc[0])}**。"
    )
    nxt = yearly[yearly["year"] == "2018"]
    if not nxt.empty and not pd.isna(nxt.iloc[0]["change_prev_year"]):
        r18 = nxt.iloc[0]
        lines.append(
            f"2018年は {r18['repeat_rate']:.2%}(前年差 {r18['change_prev_year'] * 100:+.2f} "
            "ポイント)。2018年はデータの終わりまでの期間が短いので、低めに出る点に注意。"
        )
if len(by_state) >= 2:
    hi, lo = by_state.iloc[0], by_state.iloc[-1]
    lines.append(
        f"{year}年の州別(購入者 {min_buyers} 人以上)では、最も高いのは **{hi['customer_state']}** "
        f"{rate_with_people(hi)}、最も低いのは **{lo['customer_state']}** {rate_with_people(lo)}。"
    )
render_summary(summary_box, lines)
