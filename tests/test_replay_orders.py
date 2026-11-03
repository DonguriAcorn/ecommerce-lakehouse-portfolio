"""replay_orders.py の convert_timestamps を確かめるテスト。"""

import pandas as pd

from ingestion.replay_orders import TIMESTAMP_COLUMNS, convert_timestamps


def make_orders() -> pd.DataFrame:
    """テスト用の小さな orders の表を作る(2つのテストで共有する)。"""
    # 1件目は日時が入っていて、2件目は空(未配達などを想定)。
    # load_orders は dtype=str で読むので、日時は文字列のまま入れる
    data = {column: ["2017-10-02 10:56:33", None] for column in TIMESTAMP_COLUMNS}
    # 変換には関係ないが、本物の表に近づけるために order_id の列も足す
    data["order_id"] = ["o1", "o2"]
    return pd.DataFrame(data)


def test_convert_timestamps_makes_datetime_and_keeps_missing_as_nat():
    """文字列が日時型になり、空の値は NaT(日時の空)のままになる。"""
    # 検査される関数を、テスト用の表で実際に動かす
    result = convert_timestamps(make_orders())

    # 日時の5列を、1列ずつ確かめる
    for column in TIMESTAMP_COLUMNS:
        # 列の型が、日時型になっているか
        assert pd.api.types.is_datetime64_any_dtype(result[column])
        # 1件目の値が、期待する日時と同じか(型だけでなく中身も見る)
        assert result[column].iloc[0] == pd.Timestamp("2017-10-02 10:56:33")
        # 2件目の空の値が、おかしな日付に化けず、空のままか
        assert result[column].isna().iloc[1]


def test_convert_timestamps_does_not_change_original():
    """変換しても、渡した元の表は書き換わらない。"""
    orders = make_orders()

    # 変換の結果はここでは使わない。元の表が変わらないかだけを見る
    convert_timestamps(orders)

    # 元の表の値が、文字列のままか(df.copy() を消すと、ここで失敗する)
    assert orders["order_purchase_timestamp"].iloc[0] == "2017-10-02 10:56:33"
