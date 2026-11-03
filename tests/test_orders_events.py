"""simulator/orders_events.py(CSV から出来事の表を作る)を確かめるテスト。"""

import pandas as pd

from ingestion.schema import EVENT_TYPE_RANKS
from simulator.orders_events import (
    RANK_FINAL,
    RANK_TO_EVENT_TYPE,
    TIMESTAMP_COLUMNS,
    build_event_records,
    convert_timestamps,
)


def make_raw_orders() -> pd.DataFrame:
    """CSV を読んだ直後(日時が文字列)の、小さな orders の表を作る。"""
    # 1件目は日時が入っていて、2件目は空(未配達などを想定)。
    # load_orders は dtype=str で読むので、日時は文字列のまま入れる
    data = {column: ["2017-10-02 10:56:33", None] for column in TIMESTAMP_COLUMNS}
    # 変換には関係ないが、本物の表に近づけるために order_id の列も足す
    data["order_id"] = ["o1", "o2"]
    return pd.DataFrame(data)


def make_orders() -> pd.DataFrame:
    """日時を日時型にした、小さな orders の表を作る。3件で、3つの型の注文を表す。"""
    ts = pd.Timestamp
    na = pd.NaT
    return pd.DataFrame(
        {
            "order_id": ["o1", "o2", "o3"],
            "customer_id": ["c1", "c2", "c3"],
            # o1: 配達まで終わった注文 / o2: 購入だけでキャンセル / o3: delivered だが配達日が空
            "order_status": ["delivered", "canceled", "delivered"],
            "order_purchase_timestamp": [
                ts("2017-10-02 10:56:33"),
                ts("2017-10-05 08:00:00"),
                ts("2017-10-03 09:00:00"),
            ],
            "order_approved_at": [ts("2017-10-02 11:07:15"), na, ts("2017-10-03 09:30:00")],
            "order_delivered_carrier_date": [
                ts("2017-10-04 19:55:00"),
                na,
                ts("2017-10-05 10:00:00"),
            ],
            "order_delivered_customer_date": [ts("2017-10-09 21:25:13"), na, na],
            "order_estimated_delivery_date": [
                ts("2017-10-18"),
                ts("2017-10-20"),
                ts("2017-10-19"),
            ],
        }
    )


def fold_status(records: pd.DataFrame, day: str) -> dict[str, str]:
    """その日までの出来事を、注文ごとに畳んだ状態を返す(Silver と同じ規則)。

    規則: 順位(event_rank)が大きいほど新しい。順位が同じなら、時刻(event_time)が新しいほう。
    """
    upto = records[records["event_date"] <= pd.Timestamp(day)]
    latest = upto.sort_values(["event_rank", "event_time"]).groupby("order_id").tail(1)
    return dict(zip(latest["order_id"], latest["order_status"]))


def test_convert_timestamps_makes_datetime_and_keeps_missing_as_nat():
    """文字列が日時型になり、空の値は NaT(日時の空)のままになる。"""
    # 検査される関数を、テスト用の表で実際に動かす
    result = convert_timestamps(make_raw_orders())

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
    orders = make_raw_orders()

    # 変換の結果はここでは使わない。元の表が変わらないかだけを見る
    convert_timestamps(orders)

    # 元の表の値が、文字列のままか(df.copy() を消すと、ここで失敗する)
    assert orders["order_purchase_timestamp"].iloc[0] == "2017-10-02 10:56:33"


def test_event_types_and_ranks_match_schema():
    """送る側の出来事の種類と順位の組が、受け取り側(schema.py)の約束と一致する。"""
    # 送る側の {順位: 種類} を {種類: 順位} に裏返して、受け取り側と比べる
    sent = {event_type: rank for rank, event_type in RANK_TO_EVENT_TYPE.items()}
    assert sent == EVENT_TYPE_RANKS


def test_event_rows_keep_time_rank_and_status():
    """本物の出来事は、時刻付きの event_time、段階の順位、到達した状態を持つ。"""
    records = build_event_records(make_orders())

    # o1 の出来事を、順位の順に取り出す
    o1 = records[records["order_id"] == "o1"].sort_values("event_rank")
    # 4つの出来事(購入、承認、引き渡し、配達)がある
    assert list(o1["event_type"]) == ["created", "approved", "shipped", "delivered"]
    # 順位は 0 から 3
    assert list(o1["event_rank"]) == [0, 1, 2, 3]
    # 時刻が日付に丸められず、元の時刻のまま入っている(承認の行で確かめる)
    assert o1.iloc[1]["event_time"] == pd.Timestamp("2017-10-02 11:07:15")
    # 各行の状態は、その時点で到達した状態
    assert list(o1["order_status"]) == ["created", "approved", "shipped", "delivered"]
    # 元データにある日時なので、作った印は付かない
    assert not o1["is_synthetic"].any()


def test_final_event_is_synthetic_with_next_day():
    """日時の列がない最終状態は、最後に分かっている日の翌日 0 時で、作った印が付く。"""
    records = build_event_records(make_orders())

    # 最終状態の行だけを取り出す(o2: キャンセル、o3: 配達日が空の delivered)
    final = records[records["event_type"] == "final"].set_index("order_id")
    assert sorted(final.index) == ["o2", "o3"]
    # 順位は最終状態の順位
    assert (final["event_rank"] == RANK_FINAL).all()
    # 作った時刻なので、印が true
    assert final["is_synthetic"].all()
    # o2 は 10-05 が最後 → 10-06 の 0 時
    assert final.loc["o2", "event_time"] == pd.Timestamp("2017-10-06 00:00:00")
    # 状態は、元データの order_status(o3 は delivered のまま)
    assert final.loc["o2", "order_status"] == "canceled"
    assert final.loc["o3", "order_status"] == "delivered"


def test_attributes_are_same_on_every_row_and_key_is_unique():
    """注文の属性はどの行でも同じで、(order_id, event_type) は重複しない。"""
    records = build_event_records(make_orders())

    # 注文ごとに、属性の値の種類が 1 つだけ(食い違わない)
    for column in ["customer_id", "order_purchase_timestamp", "order_estimated_delivery_date"]:
        assert (records.groupby("order_id")[column].nunique() == 1).all()
        # 属性が空の行もない(窓に created がなくても NULL にならない前提)
        assert records[column].notna().all()
    # イベントのキーに重複がない
    assert not records.duplicated(["order_id", "event_type"]).any()


def test_folding_events_gives_expected_status_each_day():
    """その日までの出来事を畳むと、その日時点の状態になる。"""
    records = build_event_records(make_orders())

    # 10-02: o1 は購入と承認が同じ日。順位の大きい approved になる
    assert fold_status(records, "2017-10-02") == {"o1": "approved"}
    # 10-05: o1 は出荷済み、o3 も出荷済み、o2 は購入したばかり
    assert fold_status(records, "2017-10-05") == {
        "o1": "shipped",
        "o2": "created",
        "o3": "shipped",
    }
    # 10-06: o2 はキャンセル、o3 は合成の最終状態(delivered)
    assert fold_status(records, "2017-10-06") == {
        "o1": "shipped",
        "o2": "canceled",
        "o3": "delivered",
    }
    # 10-10: o1 も配達済み
    assert fold_status(records, "2017-10-10")["o1"] == "delivered"


def test_folding_prefers_rank_over_time():
    """時刻が逆転していても(引き渡しが承認より前)、順位の大きい出来事を最新とみなす。"""
    orders = make_orders()
    # o1 の引き渡しの日時を、承認より前にずらす(Olist にもある、時刻の逆転)
    orders.loc[0, "order_delivered_carrier_date"] = pd.Timestamp("2017-10-02 11:00:00")
    records = build_event_records(orders)

    # 時刻なら approved(11:07)が最後だが、順位で shipped を選ぶ
    assert fold_status(records, "2017-10-02")["o1"] == "shipped"
