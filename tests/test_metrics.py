"""semantic/metrics.py(セマンティックレイヤーの読み込み関数)のテスト。

定義は本物の semantic/metrics.yml を使い、データは小さな Parquet を tmp_path に作って渡す。
(app/data/ の本物の Parquet は export のたびに変わるので、テストの答えを固定できない)
数字は、2017-11 の SP と RJ の実データの値を使い、手計算の答えと比べる。
"""

import copy
from decimal import Decimal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from semantic.metrics import (
    build_sql,
    load_definitions,
    query_metric,
    query_metric_changes,
    shift_period,
    validate_definitions,
)

# 金額の型は、export と同じ decimal(38, 2)
MONEY = pa.decimal128(38, 2)


def write(path, columns: dict, types: dict) -> None:
    """列の辞書から、型を指定して Parquet を1つ書く。"""
    table = pa.table({k: pa.array(v, type=types.get(k)) for k, v in columns.items()})
    pq.write_table(table, path)


@pytest.fixture
def data_dir(tmp_path):
    """pub_ の4表の小さな見本を作り、そのフォルダを返す。"""
    # 月 × 州の売上と注文数。2017-11 の SP と RJ は実データの値
    write(
        tmp_path / "pub_kpi_monthly.parquet",
        {
            # 2018-02 はわざと抜いてある(実データの 2016-11 と同じ、注文0件の月)
            "year_month": ["2017-11", "2017-11", "2017-12", "2018-01", "2018-03"],
            "customer_state": ["SP", "RJ", "SP", "SP", "SP"],
            "gmv": [Decimal("406854.38"), Decimal("175132.85"),
                    Decimal("100000.00"), Decimal("50000.00"), Decimal("30000.00")],
            "orders": [2949, 1036, 1000, 500, 300],
        },
        {"gmv": MONEY, "orders": pa.int64()},
    )
    # 月 × 州の人数(2017-11 は実データの値)
    write(
        tmp_path / "pub_repeat_monthly.parquet",
        {
            "year_month": ["2017-11", "2017-11", "2017-12"],
            "customer_state": ["SP", "RJ", "SP"],
            "buyers": [2953, 1030, 3000],
            "repeat_buyers": [158, 51, 200],
        },
        {"buyers": pa.int64(), "repeat_buyers": pa.int64()},
    )
    # 年 × 州の人数(2017 年の実データの値)。月を足した値とは違う数字にしてある
    write(
        tmp_path / "pub_repeat_yearly.parquet",
        {
            "year": ["2017", "2017"],
            "customer_state": ["SP", "RJ"],
            "buyers": [17203, 6031],
            "repeat_buyers": [796, 273],
        },
        {"buyers": pa.int64(), "repeat_buyers": pa.int64()},
    )
    # 月 × カテゴリ。カテゴリごとの平均の星は 4.0 と 5.0(平均の平均なら 4.5)
    write(
        tmp_path / "pub_category_monthly.parquet",
        {
            "year_month": ["2017-11", "2017-11"],
            "category_name": ["bed_bath_table", "toys"],
            "gmv": [Decimal("1000.00"), Decimal("500.00")],
            "items_sold": [10, 5],
            "avg_review_score": [4.0, 5.0],
            "review_score_sum": [36, 5],
            "reviewed_items": [9, 1],
        },
        {"gmv": MONEY, "items_sold": pa.int64(),
         "review_score_sum": pa.int64(), "reviewed_items": pa.int64()},
    )
    return tmp_path


def test_aov_is_ratio_of_sums(data_dir):
    # 2州をまとめた平均注文額は、合計 ÷ 合計(581,987.23 ÷ 3,985 = 146.04)
    # 州ごとの平均(137.96 と 169.05)を平均した 153.51 にはならない
    df = query_metric("aov", where={"year_month": "2017-11"}, data_dir=data_dir)
    assert df["aov"].iloc[0] == pytest.approx(146.04, abs=0.01)


def test_aov_by_state(data_dir):
    # 州で切ると、州ごとの値が出る(列は時間、州、指標の順)
    df = query_metric("aov", by=["customer_state"], where={"year_month": "2017-11"},
                      data_dir=data_dir)
    assert list(df.columns) == ["year_month", "customer_state", "aov"]
    values = dict(zip(df["customer_state"], df["aov"]))
    assert values["SP"] == pytest.approx(137.96, abs=0.01)
    assert values["RJ"] == pytest.approx(169.05, abs=0.01)


def test_gmv_rolls_up_to_year_and_quarter(data_dir):
    # rollup: true の売上は、月の表を足し上げて年と四半期にできる
    year = query_metric("gmv", grain="year", data_dir=data_dir)
    assert dict(zip(year["year"], year["gmv"])) == pytest.approx(
        {"2017": 681987.23, "2018": 80000.00}
    )
    quarter = query_metric("gmv", grain="quarter", data_dir=data_dir)
    # 11月と12月は Q4、1月と3月は Q1
    assert list(quarter["quarter"]) == ["2017-Q4", "2018-Q1"]


def test_repeat_rate_by_year_uses_yearly_table(data_dir):
    # 年別のリピート率は、年の表で数え直した人数から出す: 1,069 ÷ 23,234 = 4.60%
    # 月の表を足すと 409 ÷ 6,983 = 5.86% になり、同じ人を二重に数えた値になる
    df = query_metric("repeat_rate", grain="year", data_dir=data_dir)
    assert df["repeat_rate"].iloc[0] == pytest.approx(1069 / 23234)


def test_repeat_rate_by_quarter_is_refused(data_dir):
    # 四半期の人数を数えた表はなく、月を足すのも禁止(rollup: false)なので、止める
    with pytest.raises(ValueError, match="出せない"):
        query_metric("repeat_rate", grain="quarter", data_dir=data_dir)


def test_gmv_by_category_uses_category_table(data_dir):
    # カテゴリの列は kpi の表にないので、sources の2番目の category の表が選ばれる
    sql, _ = build_sql("gmv", by=["category_name"], data_dir=data_dir)
    assert "pub_category_monthly" in sql
    df = query_metric("gmv", by=["category_name"], data_dir=data_dir)
    assert dict(zip(df["category_name"], df["gmv"])) == pytest.approx(
        {"bed_bath_table": 1000.00, "toys": 500.00}
    )


def test_avg_review_score_is_not_average_of_averages(data_dir):
    # 星の合計 ÷ レビュー数 = 41 ÷ 10 = 4.1(カテゴリの平均を平均した 4.5 ではない)
    df = query_metric("avg_review_score", data_dir=data_dir)
    assert df["avg_review_score"].iloc[0] == pytest.approx(4.1)


def test_filter_value_is_not_mixed_into_sql(data_dir):
    # 絞り込みの値は ? の場所に入り、SQL の文字には混ざらない(SQL インジェクション対策)
    sql, params = build_sql("gmv", where={"customer_state": "SP' or '1'='1"}, data_dir=data_dir)
    assert "or '1'='1" not in sql
    assert params == ["SP' or '1'='1"]
    # そんな州はないので、結果は 0 行
    df = query_metric("gmv", where={"customer_state": "SP' or '1'='1"}, data_dir=data_dir)
    assert df.empty


def test_unknown_metric_and_column_are_refused(data_dir):
    # 定義にない指標と、絞り込めない列は止める
    with pytest.raises(ValueError, match="定義にない"):
        query_metric("profit", data_dir=data_dir)
    with pytest.raises(ValueError, match="絞り込めない"):
        query_metric("gmv", where={"customer_unique_id": "x"}, data_dir=data_dir)


def test_grain_all_gives_one_row_for_the_period(data_dir):
    # 期間全体(KPI のカード用)は1行。2017年の平均注文額 = 681,987.23 ÷ 4,985
    df = query_metric("aov", grain="all", where={"year": "2017"}, data_dir=data_dir)
    assert list(df.columns) == ["aov"]
    assert df["aov"].iloc[0] == pytest.approx(681987.23 / 4985)


def test_grain_all_is_refused_for_repeat_rate(data_dir):
    # 期間全体のリピート率は、月や年の人数を足すと二重に数えるので出さない
    with pytest.raises(ValueError, match="出せない"):
        query_metric("repeat_rate", grain="all", data_dir=data_dir)


def test_filter_accepts_tuple_of_values(data_dir):
    # 画面の複数選択(tuple)でも絞り込める。SP と RJ の 2017-11 の注文数 = 2,949 + 1,036
    df = query_metric("orders", grain="all",
                      where={"customer_state": ("SP", "RJ"), "year_month": "2017-11"},
                      data_dir=data_dir)
    assert df["orders"].iloc[0] == 3985
    # 空の選択は止める(in () は SQL の書き間違いになる)
    with pytest.raises(ValueError, match="空"):
        query_metric("orders", where={"customer_state": ()}, data_dir=data_dir)


def test_shift_period_crosses_year():
    # 年をまたいでも、前の期間・前年同期が正しく出る
    assert shift_period("2017-01", "month", 1) == "2016-12"
    assert shift_period("2017-01", "month", 12) == "2016-01"
    assert shift_period("2017-Q1", "quarter", 1) == "2016-Q4"
    assert shift_period("2017", "year", 1) == "2016"


def test_changes_match_by_period_not_by_row(data_dir):
    # 前月比は「1行前」ではなく「1か月前の月」と比べる
    df = query_metric_changes("gmv", data_dir=data_dir).set_index("year_month")
    # 2017-12 の前月は 2017-11(全国 581,987.23)。100,000 ÷ 581,987.23 - 1
    assert df.loc["2017-12", "change_prev_period"] == pytest.approx(100000 / 581987.23 - 1)
    # 2018-03 の前月 2018-02 は行がないので空(1行前の 2018-01 と比べてはいけない)
    assert pd.isna(df.loc["2018-03", "prev_period"])
    assert pd.isna(df.loc["2018-03", "change_prev_period"])


def test_changes_for_ratio_are_differences(data_dir):
    # 割合(リピート率)の変化は差(ポイント)。SP の 2017-12 と 2017-11
    df = query_metric_changes("repeat_rate", by=["customer_state"],
                              where={"customer_state": "SP"}, data_dir=data_dir)
    row = df.set_index("year_month").loc["2017-12"]
    assert row["change_prev_period"] == pytest.approx(200 / 3000 - 158 / 2953)


def test_changes_refuse_time_filter(data_dir):
    # 時間で絞ると前の期間が消えるので止める
    with pytest.raises(ValueError, match="時間で絞り込めない"):
        query_metric_changes("gmv", where={"year": "2017"}, data_dir=data_dir)


def test_real_definitions_are_valid():
    # 本物の metrics.yml が読めて、7つの指標があること(主な5つと、補助の2つ)
    defs = load_definitions()
    names = [m["name"] for m in defs["metrics"]]
    assert names == ["gmv", "orders", "aov", "repeat_rate", "avg_review_score",
                     "items_sold", "buyers"]


def test_validate_finds_missing_table():
    # sources に、tables にない表を書いたら止まる(書き間違いを読み込み時に見つける)
    defs = copy.deepcopy(load_definitions())
    defs["metrics"][0]["sources"] = ["pub_not_exists"]
    with pytest.raises(ValueError, match="tables にない"):
        validate_definitions(defs)
