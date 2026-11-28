"""画面どうしで共通の部品(数字の取り出し、データの更新日時、出典の表示)。"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from semantic.metrics import get_metric, query_metric, query_metric_changes

# export_pub.py が書く status.json(export の時刻、行数、最新の注文日)
STATUS_PATH = Path(__file__).resolve().parent / "data" / "status.json"


@st.cache_data  # 同じ引数なら計算し直さない(Streamlit は操作のたびに上から流し直すため)
def metric(name: str, grain: str = "month", by: tuple = (), where: tuple = ()) -> pd.DataFrame:
    """query_metric() の画面用の入口。by と where は、覚えておけるように tuple で受け取る。

    例: metric("aov", grain="year", where=(("customer_state", "SP"),))
    """
    return query_metric(name, grain=grain, by=list(by), where=dict(where))


@st.cache_data
def changes(name: str, grain: str = "month", by: tuple = (), where: tuple = ()) -> pd.DataFrame:
    """query_metric_changes() の画面用の入口(前の期間比、前年同期比つきの表)。"""
    return query_metric_changes(name, grain=grain, by=list(by), where=dict(where))


@st.cache_data
def comparable_months() -> list[str]:
    """比べる意味のある月の一覧: 注文数(全国)が最も多い月の 1 割以上ある月。

    データの端の月(2016-09 は2件、2016-10 は293件、2016-12 は1件、2018-09 は1件)を除く。
    件数が少なすぎる月の伸び率や割合は、たまたまの値で大きく振れるため。
    """
    monthly = metric("orders", grain="month")
    enough = monthly[monthly["orders"] >= monthly["orders"].max() * 0.1]
    return enough["year_month"].tolist()


def states_by_gmv() -> list[str]:
    """州の一覧を、全期間の売上が大きい順に返す(選択欄の並び。SP、RJ、MG …)。"""
    df = metric("gmv", grain="all", by=("customer_state",))
    return df.sort_values("gmv", ascending=False)["customer_state"].tolist()


def render_header(title: str, purpose: str):
    """画面の見出しと、何がわかる画面かの1行を出し、サマリーを入れる箱を返す。

    サマリーは、下の絞り込みで選んだ値から作るので、画面の最後に箱へ書き込む
    (Streamlit は上から流すので、先に箱だけ置いておく)。
    """
    st.title(title)
    st.markdown(purpose)
    return st.container()


def render_summary(box, lines: list[str]) -> None:
    """画面の上の箱に、選んだ条件での事実のサマリーを出す(AI は使わず、決まった文型で作る)。"""
    lines = [line for line in lines if line]  # 作れなかった文(None や空)は出さない
    if lines:
        box.info("**サマリー**\n" + "\n".join(f"- {line}" for line in lines))


def chart_heading(title: str, description: str) -> None:
    """グラフの見出しと、そのグラフが何を表しているかの説明(初めて見る人向け)。"""
    st.subheader(title)
    st.caption(description)


def render_terms(points: list[str]) -> None:
    """用語の定義と注意点を、開いて読む欄に出す(最初は閉じておく)。"""
    with st.expander("用語と注意点"):
        st.markdown("\n".join(f"- {p}" for p in points))


def share(part: float, total: float) -> str:
    """割合を 37.4% の形にする(サマリーの文に使う)。"""
    return f"{part / total:.1%}" if total else "—"


def label(name: str) -> str:
    """指標の表示名(metrics.yml の label)。画面の見出しに使う。"""
    return get_metric(name)["label"]


@st.cache_data
def load_status() -> dict:
    """status.json を読む。なければ空の辞書(画面は止めない)。"""
    if not STATUS_PATH.exists():
        return {}
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def render_sidebar_status() -> None:
    """左のメニューの下に、データがいつの時点のものかを出す。"""
    status = load_status()
    if status:
        st.sidebar.caption(
            f"データの最新の注文日: {status['latest_purchase_date']}  \n"
            f"集計の書き出し: {status['exported_at']}(元の環境: {status['source_env']})"
        )


def render_footer() -> None:
    """出典とライセンス(ADR 0018)。CC BY-NC-SA 4.0 の条件で、どの画面にも出す。"""
    st.divider()
    st.caption(
        "データ出典: Brazilian E-Commerce Public Dataset by Olist(Kaggle)。"
        "ライセンス: CC BY-NC-SA 4.0。"
        "この画面の集計は元データからの派生物で、同じ CC BY-NC-SA 4.0 で公開する。"
        "非商用の学習用ポートフォリオ。金額の単位はブラジルレアル(BRL)。"
    )
