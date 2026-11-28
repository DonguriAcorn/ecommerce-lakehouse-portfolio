"""カテゴリランキングの画面: カテゴリ別の売上・販売数・平均の星のランキングと、上位カテゴリの推移。

v1.0 のランキングはカテゴリ単位(商品単位は公開しない。ADR 0018)。
上のサマリーは決まった文型で作る(AI は使わない)。
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
)

ALL_PERIOD = "全期間"
RANK_METRICS = ["gmv", "items_sold", "avg_review_score"]  # 並べ替えに使える指標
MIN_ITEMS = 100  # 平均の星を比べるときの、販売数の下限の初期値

summary_box = render_header(
    "カテゴリランキング",
    "**どの商品カテゴリが売れているか、評価が高いか**を見る画面です。",
)
render_terms(
    [
        "**販売数**: 売れた明細の数。1つの注文で2つ買えば2と数える。",
        "**平均の星**: 1〜5 の星の平均。レビューは商品ごとではなく注文ごとなので、"
        "1つの注文に複数の商品があれば、どの商品にも同じ星を数える。",
        "**カテゴリ名**: ポルトガル語の名前の英訳。英訳がないものは元の名前、"
        "カテゴリが空の商品は unknown(売上の約 1.3%)にまとめる。",
        "**公開の範囲**: ライセンスとプライバシーへの配慮から、"
        "商品単位ではなくカテゴリ単位で出す。",
    ]
)

# ---- 絞り込み(年、並べ替えの指標、件数) ----
years = metric("gmv", grain="year")["year"].tolist()
col_year, col_metric, col_n = st.columns([1, 2, 1])
year = col_year.selectbox("年", [ALL_PERIOD, *years])
rank_by = col_metric.radio("並べ替え", RANK_METRICS, format_func=label, horizontal=True)
top_n = col_n.number_input("表示する数", min_value=5, max_value=50, value=15, step=5)

where = (("year", year),) if year != ALL_PERIOD else ()
period_text = "全期間" if year == ALL_PERIOD else f"{year}年"

# 3つの指標を、カテゴリごとに1つの表に並べる(それぞれ semantic で計算した値をつなぐだけ)
table = metric("gmv", grain="all", by=("category_name",), where=where)
for name in ["items_sold", "avg_review_score"]:
    table = table.merge(metric(name, grain="all", by=("category_name",), where=where),
                        on="category_name")

# 平均の星は、販売数が少ないカテゴリだと数件で決まってしまうので、下限を付ける
shown = table
if rank_by == "avg_review_score":
    min_items = st.number_input("販売数がこの数以上のカテゴリだけ", min_value=0,
                                value=MIN_ITEMS, step=50)
    shown = table[table["items_sold"] >= min_items]

ranked = shown.sort_values(rank_by, ascending=False).head(int(top_n))

# ---- ランキングの棒グラフ ----
chart_heading(
    f"{label(rank_by)}のランキング(上位 {int(top_n)})",
    f"{period_text}のカテゴリを、{label(rank_by)}の大きい順に上から並べた棒です。"
    "棒が長いほど値が大きく、棒にマウスを乗せると、売上・販売数・平均の星の3つが出ます。"
    "並べ替えを変えると順位が入れ替わります(売上と販売数で順位が違うカテゴリは、単価が高いか低い)。",
)
fmt = {"gmv": ",.0f", "items_sold": ",", "avg_review_score": ".2f"}  # 指標ごとの表示の形
chart = (
    alt.Chart(ranked)
    .mark_bar()
    .encode(
        x=alt.X(f"{rank_by}:Q", title=label(rank_by)),
        y=alt.Y("category_name:N", sort="-x", title="カテゴリ"),  # 値の大きい順
        tooltip=["category_name"]
        + [alt.Tooltip(f"{n}:Q", title=label(n), format=fmt[n]) for n in RANK_METRICS],
    )
    # 棒の数に合わせて高さを変える(1本 22px。多いときに棒がつぶれないように)
    .properties(height=max(200, 22 * len(ranked)))
)
st.altair_chart(chart, width="stretch")

# ---- 表(3つの指標を並べて見る) ----
st.caption("上の棒と同じカテゴリの、売上(R$)・販売数・平均の星を並べた表です。列名を押すと並べ替えられます。")
st.dataframe(
    ranked.rename(columns={"category_name": "カテゴリ", **{n: label(n) for n in RANK_METRICS}}),
    hide_index=True,
    column_config={
        # localized: 3桁区切りで出す(金額の単位はフッターに書いた BRL)
        label("gmv"): st.column_config.NumberColumn(format="localized"),
        label("items_sold"): st.column_config.NumberColumn(format="localized"),
        label("avg_review_score"): st.column_config.NumberColumn(format="%.2f"),
    },
)


# ---- 売上の上位5カテゴリの月ごとの推移 ----
chart_heading(
    "売上の上位5カテゴリの月ごとの推移",
    f"{period_text}の売上の上位5カテゴリについて、月ごとの売上を線で並べたものです。"
    "線の色がカテゴリで、凡例は売上の大きい順です。どのカテゴリがいつ伸びたかを比べられます。",
)
top5 = table.sort_values("gmv", ascending=False).head(5)["category_name"].tolist()
monthly = metric("gmv", grain="month", by=("category_name",),
                 where=(*where, ("category_name", tuple(top5))))
chart = (
    alt.Chart(monthly)
    .mark_line(point=True)
    .encode(
        x=alt.X("year_month:O", title="月"),
        y=alt.Y("gmv:Q", title=label("gmv") + "(R$)"),
        color=alt.Color("category_name:N", title="カテゴリ", sort=top5),  # 凡例も売上の順
        tooltip=["year_month", "category_name", alt.Tooltip("gmv:Q", format=",.0f")],
    )
)
st.altair_chart(chart, width="stretch")


# ---- サマリー(画面の上の箱に書く) ----
lines = []
if not table.empty:
    total = table["gmv"].sum()
    by_gmv = table.sort_values("gmv", ascending=False)
    first = by_gmv.iloc[0]
    lines.append(
        f"{period_text}の売上1位は **{first['category_name']}**(R$ {first['gmv']:,.0f}、"
        f"全カテゴリの {share(first['gmv'], total)})。"
        f"上位5カテゴリで {share(by_gmv['gmv'].head(5).sum(), total)} を占める"
        f"(カテゴリは全部で {len(table)})。"
    )
    most = table.loc[table["items_sold"].idxmax()]
    lines.append(f"販売数1位は **{most['category_name']}**({most['items_sold']:,.0f} 個)。")
    rated = table[table["items_sold"] >= MIN_ITEMS].dropna(subset=["avg_review_score"])
    if len(rated) >= 2:
        best = rated.loc[rated["avg_review_score"].idxmax()]
        worst = rated.loc[rated["avg_review_score"].idxmin()]
        lines.append(
            f"販売数 {MIN_ITEMS} 以上のカテゴリで平均の星が最も高いのは **{best['category_name']}**"
            f"({best['avg_review_score']:.2f})、最も低いのは **{worst['category_name']}**"
            f"({worst['avg_review_score']:.2f})。"
        )
render_summary(summary_box, lines)
