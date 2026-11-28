"""売上 KPI の画面: 売上・注文数・平均注文額のカード、月ごとの推移、州ごとの売上。

数字はすべて common.metric()(= semantic の query_metric())から出し、この画面では計算しない。
上のサマリーは、選んだ条件の数字から決まった文型で作る(AI は使わない)。
"""

import altair as alt
import streamlit as st
from common import (
    chart_heading,
    label,
    metric,
    render_header,
    render_summary,
    render_terms,
    share,
    states_by_gmv,
)

ALL_PERIOD = "全期間"

summary_box = render_header(
    "売上 KPI",
    "**どれだけ売れたか**を見る画面です。年と州を選ぶと、カードとグラフがその条件に変わります。",
)
render_terms(
    [
        "**売上(GMV)**: 商品代金 + 送料の合計。キャンセル(canceled)と在庫切れ(unavailable)の"
        "注文は数えず、配送中などの進行中の注文は数える。金額はブラジルレアル(R$)。",
        "**平均注文額**: 売上の合計 ÷ 注文数の合計(州ごとの平均をさらに平均した値ではない)。",
        "**購入者数**: その月に注文した人の数(同じ人が月に何回注文しても1人)。"
        "リピート率と同じ数え方で、キャンセルした注文の人も含む。",
        "**州**: 注文した時点の、顧客の住所の州(SP = サンパウロ州、RJ = リオデジャネイロ州 など)。",
        "**データの期間**: 2016年は9〜12月、2018年は10月まで(2018年9月以降は注文がわずか)。"
        "年の合計どうしを比べると、2016年と2018年は小さく見える。",
    ]
)

# ---- 絞り込み(年と州) ----
# 年の選択肢は、データにある年から作る(2016、2017、2018)
years = metric("gmv", grain="year")["year"].tolist()
col_year, col_state = st.columns([1, 3])
year = col_year.selectbox("年", [ALL_PERIOD, *years])
# 州の選択肢は、全期間の売上が大きい順(SP、RJ、MG …)
selected_states = col_state.multiselect("州(空なら全国)", states_by_gmv())

# 選んだ条件を、metric() に渡す形(列名と値の組の tuple)にする
where = []
if year != ALL_PERIOD:
    where.append(("year", year))
if selected_states:
    where.append(("customer_state", tuple(selected_states)))
where = tuple(where)
# サマリーの文で使う、条件の呼び方(例: 「2017年・SP、RJ」)
period_text = "全期間" if year == ALL_PERIOD else f"{year}年"
state_text = "、".join(selected_states) if selected_states else "全国"


# ---- カード(選んだ期間全体の値) ----
def card_value(name: str) -> float | None:
    """期間全体の指標の値を1つ返す。条件に合うデータがなければ None。"""
    df = metric(name, grain="all", where=where)
    return None if df.empty or df[name].isna().all() else float(df[name].iloc[0])


gmv, orders, aov = card_value("gmv"), card_value("orders"), card_value("aov")
c1, c2, c3 = st.columns(3)
# 表示の形: 金額は R$ と3桁区切り、注文数は件
c1.metric(label("gmv"), "—" if gmv is None else f"R$ {gmv:,.0f}")
c2.metric(label("orders"), "—" if orders is None else f"{orders:,.0f} 件")
c3.metric(label("aov"), "—" if aov is None else f"R$ {aov:,.2f}")


# ---- 月ごとの推移 ----
chart_heading(
    "月ごとの推移",
    "左: 月ごとの売上の合計(折れ線)。右: 月ごとの注文数(棒)と購入者数(線)。横軸はどちらも月。"
    "左と右の形が似ていれば、売上の増減は主に注文の件数で決まっています。"
    "右の棒と線がほぼ重なるのは、ほとんどの人が1か月に1回しか注文しないためです。",
)
monthly_gmv = metric("gmv", grain="month", where=where)
# 注文数と購入者数を、月で1つの表にまとめる(同じ縦軸に重ねるため)
monthly_counts = metric("orders", grain="month", where=where).merge(
    metric("buyers", grain="month", where=where), on="year_month", how="left"
)

left, right = st.columns(2)
left.caption(label("gmv") + "(R$)")
left.line_chart(monthly_gmv, x="year_month", y="gmv", x_label="月", y_label="")

right.caption(f"{label('orders')}(棒)と{label('buyers')}(線)")
base = alt.Chart(monthly_counts).encode(x=alt.X("year_month:O", title="月"))
bars = base.mark_bar(opacity=0.6).encode(
    y=alt.Y("orders:Q", title="件・人"),
    tooltip=["year_month", alt.Tooltip("orders:Q", title=label("orders"), format=",")],
)
line = base.mark_line(point=True, color="#e45756").encode(  # 線は棒と見分けやすい赤
    y="buyers:Q",
    tooltip=["year_month", alt.Tooltip("buyers:Q", title=label("buyers"), format=",")],
)
right.altair_chart(bars + line, width="stretch")  # + で、同じ軸に重ねて描く


# ---- 州ごとの売上(上位 10) ----
chart_heading(
    "州ごとの売上(上位 10)",
    "選んだ条件での、州ごとの売上の合計です。棒が長いほど売上が大きく、上から大きい順に"
    "10州まで並べています。棒にマウスを乗せると金額が出ます。",
)
by_state_all = metric("gmv", grain="all", by=("customer_state",), where=where).sort_values(
    "gmv", ascending=False
)
by_state = by_state_all.head(10)
# st.bar_chart は州名の abc 順に並ぶので、売上の大きい順に並べるために altair で描く
chart = (
    alt.Chart(by_state)
    .mark_bar()
    .encode(
        x=alt.X("gmv:Q", title=label("gmv") + "(R$)"),
        y=alt.Y("customer_state:N", sort="-x", title="州"),  # sort="-x": 棒の長い順
        tooltip=["customer_state", alt.Tooltip("gmv:Q", format=",.0f")],
    )
)
st.altair_chart(chart, width="stretch")


# ---- サマリー(画面の上の箱に書く) ----
lines = []
if gmv is not None:
    lines.append(
        f"{period_text}・{state_text}の売上は **R$ {gmv:,.0f}**(注文 {orders:,.0f} 件、"
        f"平均注文額 R$ {aov:,.2f})。"
    )
if not monthly_gmv.empty:
    peak = monthly_gmv.loc[monthly_gmv["gmv"].idxmax()]
    lines.append(f"売上が最も多い月は **{peak['year_month']}**(R$ {peak['gmv']:,.0f})。")
if len(by_state_all) >= 2:
    top = by_state_all.iloc[0]
    total = by_state_all["gmv"].sum()
    top3 = share(by_state_all["gmv"].head(3).sum(), total)  # 上位3州の合計の割合
    lines.append(
        f"州別では **{top['customer_state']}** が最大で、選んだ範囲の売上の "
        f"{share(top['gmv'], total)} を占める(上位3州で {top3})。"
    )
elif len(selected_states) == 1 and gmv is not None:
    # 1州だけ選んだときは、全国の中での大きさを書く
    national = metric("gmv", grain="all", where=tuple(w for w in where if w[0] == "year"))
    lines.append(
        f"{selected_states[0]} の売上は、{period_text}の全国の売上の "
        f"{share(gmv, national['gmv'].iloc[0])} にあたる。"
    )
render_summary(summary_box, lines)
