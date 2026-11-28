"""Olist EC ダッシュボードの入口(Streamlit)。

手元で開く: uv run streamlit run app/app.py
画面の中身は app/views/ の1ファイル1画面。
数字はすべて semantic/metrics.py の query_metric() から出す。
"""

import sys
from pathlib import Path

# リポジトリの直下を import の探し先に足す(semantic/ を読むため)。
# streamlit run は app/ を探し先にするだけなので、1つ上は自分で足す
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402  (上の探し先を足してから import する)
from common import render_footer, render_sidebar_status  # noqa: E402

# ページ全体の設定(タブの題名と、横幅いっぱいの配置)。最初の st. の呼び出しにする決まり
st.set_page_config(page_title="Olist EC ダッシュボード", layout="wide")

# 画面の一覧。1ファイル = 1画面で、左のメニューに上から並ぶ
pages = [
    st.Page("views/sales.py", title="売上 KPI", default=True),
    st.Page("views/compare.py", title="期間比較"),
    st.Page("views/repeat.py", title="リピート率"),
    st.Page("views/ranking.py", title="カテゴリランキング"),
]
current = st.navigation(pages)  # 選ばれた画面を決める

render_sidebar_status()  # 左のメニューの下に、データの更新日時を出す
current.run()  # 選ばれた画面のファイルを流す
render_footer()  # どの画面でも、下に出典とライセンスを出す
