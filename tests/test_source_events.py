"""ソースを作る処理(simulator)と、届いたファイルの取り込み(ingestion)のテスト。"""

import pandas as pd
import pyarrow.parquet as pq
import pytest

from ingestion.ingest_table import convert_types, read_source, validate_rows
from ingestion.orders_checks import check_orders_events
from ingestion.quarantine import IngestStop, write_quarantine
from ingestion.raw_writer import write_raw
from ingestion.run_log import RunLog
from ingestion.schema import EVENT_COLUMNS, ORDERS_EVENTS
from simulator.make_source_events import (
    assign_arrival_dates,
    pick_late_events,
    write_source_events,
)
from simulator.orders_events import build_event_records
from tests.test_orders_events import make_orders


# --- orders の取扱説明書と追加の検証を渡す、テスト用の短い呼び方 ---
def read_source_orders(path, log, ingest_date):
    """orders の届いたファイルを、共通の受付で読む。"""
    return read_source(path, ORDERS_EVENTS, log, ingest_date)


def validate_orders(raw, log, ingest_date, **kwargs):
    """orders を、共通の検証 + orders だけの追加の検証で確かめる。"""
    return validate_rows(
        raw, ORDERS_EVENTS, log, ingest_date, extra_check=check_orders_events, **kwargs
    )


def convert_orders(good):
    """orders の良い行を、registry の型にする。"""
    return convert_types(good, ORDERS_EVENTS)


def write_orders(records, ingest_date, raw_dir, batch_id):
    """orders の行を、Raw に書く。"""
    return write_raw(records, ORDERS_EVENTS, ingest_date, raw_dir, batch_id)


def make_many_records(n: int = 200) -> pd.DataFrame:
    """遅延の割合を確かめるための、order_id だけが違う出来事の表を作る。"""
    return pd.DataFrame(
        {"order_id": [f"o{i}" for i in range(n)], "event_type": ["created"] * n}
    )


def test_pick_late_events_is_deterministic():
    """同じ seed なら何度選んでも同じ。seed を変えると、選ばれる出来事が変わる。"""
    records = make_many_records()

    first = pick_late_events(records, 0.5, "seed-a")
    second = pick_late_events(records, 0.5, "seed-a")
    other = pick_late_events(records, 0.5, "seed-b")

    # 同じ seed では、1件残らず同じ結果(Python の hash() だと、実行ごとに変わりうる)
    assert first.equals(second)
    # 別の seed では、どこかが違う
    assert not first.equals(other)
    # 割合 0 なら1件も選ばれず、割合 1 ならすべて選ばれる
    assert not pick_late_events(records, 0.0, "seed-a").any()
    assert pick_late_events(records, 1.0, "seed-a").all()


def test_assign_arrival_dates_shifts_only_late_events():
    """遅延の対象だけ、届いた日が late_days 日後ろにずれる。起きた日時(event_time)は変えない。"""
    records = build_event_records(make_orders())

    # 割合 1(すべて遅延)で、3日ずらす
    late = assign_arrival_dates(records, 1.0, 3, "seed-a")
    assert (late["arrival_date"] == late["event_date"] + pd.Timedelta(days=3)).all()
    assert late["event_time"].equals(records["event_time"])

    # 割合 0(遅延なし)なら、届いた日 = 起きた日
    on_time = assign_arrival_dates(records, 0.0, 3, "seed-a")
    assert (on_time["arrival_date"] == on_time["event_date"]).all()


def test_source_round_trip_keeps_values_and_types(tmp_path):
    """ソースに書いて、読んで、検証して、型を戻すと、元の出来事と同じ値・型になる。"""
    records = assign_arrival_dates(build_event_records(make_orders()), 0.0, 3, "seed-a")
    write_source_events(records, tmp_path / "source")
    log = RunLog(tmp_path / "logs", "orders_events", "batch1")

    # 10-02 に届いたファイルを、取り込みと同じ手順で読む
    path = tmp_path / "source" / "arrival_date=2017-10-02" / "orders_events_20171002.jsonl"
    raw = read_source_orders(path, log, "2017-10-02")
    good, bad = validate_orders(raw, log, "2017-10-02")
    result = convert_orders(good).reset_index(drop=True)

    # 隔離はなく、元の 10-02 の出来事と同じ値になる(順位は int32 にそろえて比べる)
    assert bad.empty
    expected = records.loc[records["arrival_date"] == "2017-10-02", EVENT_COLUMNS]
    expected = expected.astype({"event_rank": "int32"}).reset_index(drop=True)
    pd.testing.assert_frame_equal(result[EVENT_COLUMNS], expected, check_dtype=False)
    # 日時の列が、日時型に戻っている
    assert pd.api.types.is_datetime64_any_dtype(result["event_time"])


def test_write_source_events_writes_empty_file_for_quiet_day(tmp_path):
    """出来事のない日も空のファイルを書き、取り込みは空の表として読む(止めない)。"""
    records = assign_arrival_dates(build_event_records(make_orders()), 0.0, 3, "seed-a")
    write_source_events(records, tmp_path / "source")
    log = RunLog(tmp_path / "logs", "orders_events", "batch1")

    # テスト用のデータでは、10-07 と 10-08 に出来事がない
    path = tmp_path / "source" / "arrival_date=2017-10-07" / "orders_events_20171007.jsonl"
    assert path.exists() and path.stat().st_size == 0
    raw = read_source_orders(path, log, "2017-10-07")
    good, bad = validate_orders(raw, log, "2017-10-07")
    assert good.empty and bad.empty


def test_missing_source_file_stops(tmp_path):
    """届いたファイルがない日は、止める(届いていないことを見逃さない)。"""
    log = RunLog(tmp_path / "logs", "orders_events", "batch1")
    with pytest.raises(IngestStop, match="SOURCE_NOT_FOUND"):
        read_source_orders(tmp_path / "nothing.jsonl", log, "2017-10-02")


def test_validate_events_quarantines_bad_rows(tmp_path):
    """知らない種類、読めない日時、キーの重複の行を隔離し、理由を残す。"""
    log = RunLog(tmp_path / "logs", "orders_events", "batch1")
    good_row = {
        "order_id": "o1",
        "customer_id": "c1",
        "order_purchase_timestamp": "2017-10-02 10:56:33",
        "order_estimated_delivery_date": "2017-10-18 00:00:00",
        "event_type": "created",
        "event_rank": 0,
        "event_time": "2017-10-02 10:56:33",
        "order_status": "created",
        "is_synthetic": False,
    }
    rows = [
        good_row,
        {**good_row, "order_id": "o2", "event_type": "returned"},  # 知らない種類
        {**good_row, "order_id": "o3", "event_time": "2017-13-45 99:00:00"},  # 読めない日時
        {**good_row, "order_id": "o4"},  # o4 の created が2行(キーの重複)
        {**good_row, "order_id": "o4"},
    ]
    raw = pd.DataFrame(rows)

    # 上限を 1(全部隔離しても止めない)にして、隔離の中身だけを確かめる
    good, bad = validate_orders(raw, log, "2017-10-02", quarantine_limit=1.0)

    assert list(good["order_id"]) == ["o1"]
    reasons = dict(zip(bad["order_id"], bad["_error_codes"]))
    assert reasons["o2"] == "UNKNOWN_EVENT_TYPE"
    assert reasons["o3"] == "UNPARSABLE_TIMESTAMP"
    assert reasons["o4"] == "DUPLICATE_KEY"


def test_validate_events_stops_when_too_many_bad_rows(tmp_path):
    """隔離が上限(既定 1%)を超えたら、止める。"""
    log = RunLog(tmp_path / "logs", "orders_events", "batch1")
    # 1行だけで、その1行が知らない種類 → 100% が隔離 → 止まる
    raw = pd.DataFrame(
        [
            {
                "order_id": "o1",
                "customer_id": "c1",
                "order_purchase_timestamp": "2017-10-02 10:56:33",
                "order_estimated_delivery_date": "2017-10-18 00:00:00",
                "event_type": "returned",
                "event_rank": 0,
                "event_time": "2017-10-02 10:56:33",
                "order_status": "created",
                "is_synthetic": False,
            }
        ]
    )
    with pytest.raises(IngestStop, match="QUARANTINE_OVER_LIMIT"):
        validate_orders(raw, log, "2017-10-02")


def test_write_events_makes_expected_file(tmp_path):
    """Raw に書いたファイルが、決めた場所・列・型になっている。"""
    records = build_event_records(make_orders())
    # 10-02 に起きた出来事だけを書く
    day_records = records[records["event_date"] == pd.Timestamp("2017-10-02")]

    out_path = write_orders(day_records, "2017-10-02", tmp_path, "batch1")

    # 置き場所は、イベント用のフォルダの下の ingest_date=日付
    expected = tmp_path / "olist" / "orders_events" / "ingest_date=2017-10-02"
    assert out_path.parent == expected
    assert out_path.name == "orders_events_20171002.parquet"

    # 列は、決めた列 + 監査カラム3つ(event_date は書かない)
    written = pd.read_parquet(out_path)
    assert list(written.columns) == EVENT_COLUMNS + ["_ingested_at", "_source_file", "_batch_id"]
    # 順位は int32(Glue の int 列と合わせる)
    assert str(written["event_rank"].dtype) == "int32"
    # 監査カラムの値
    assert (written["_batch_id"] == "batch1").all()
    assert (written["_source_file"] == "orders_events_20171002.parquet").all()


def test_validate_events_checks_rank_flag_and_empty_rank(tmp_path):
    """種類と順位の食い違い、文字の印、空の順位を隔離する(型の変換で落ちない)。"""
    log = RunLog(tmp_path / "logs", "orders_events", "batch1")
    good_row = {
        "order_id": "o1",
        "customer_id": "c1",
        "order_purchase_timestamp": "2017-10-02 10:56:33",
        "order_estimated_delivery_date": "2017-10-18 00:00:00",
        "event_type": "shipped",
        "event_rank": 2,
        "event_time": "2017-10-04 19:55:00",
        "order_status": "shipped",
        "is_synthetic": False,
    }
    rows = [
        good_row,
        {**good_row, "order_id": "o2", "event_rank": 0},  # shipped なのに順位 0
        {**good_row, "order_id": "o3", "is_synthetic": "false"},  # 文字の "false"
        {**good_row, "order_id": "o4", "event_rank": None},  # 順位が空
    ]
    raw = pd.DataFrame(rows)

    good, bad = validate_orders(raw, log, "2017-10-04", quarantine_limit=1.0)

    # 良い行は o1 だけで、型の変換も通る
    assert list(good["order_id"]) == ["o1"]
    assert convert_orders(good)["event_rank"].dtype == "Int32"
    reasons = dict(zip(bad["order_id"], bad["_error_codes"]))
    assert reasons["o2"] == "INVALID_EVENT_RANK"
    assert reasons["o3"] == "INVALID_FLAG"
    assert reasons["o4"] == "EMPTY_REQUIRED"


def test_write_quarantine_handles_mixed_types(tmp_path):
    """隔離する行に型の混ざった値があっても、文字列にそろえて書ける。"""
    # 順位の列に、数と文字が混ざっている
    bad = pd.DataFrame(
        {"order_id": ["o1", "o2"], "event_rank": [0, "x"], "_error_codes": ["A", "B"]}
    )

    out_path = write_quarantine(bad, tmp_path, "batch1", "orders_events")

    # 書いたファイルが読めて、値は文字列になっている
    written = pd.read_parquet(out_path)
    assert list(written["event_rank"]) == ["0", "x"]
    assert out_path.name == "orders_events.parquet"


def test_empty_day_has_same_raw_types_as_normal_day(tmp_path):
    """出来事のない日(0 行)の Raw も、ふつうの日と同じ列の型になる。"""
    records = build_event_records(make_orders())
    normal = records[records["event_date"] == pd.Timestamp("2017-10-02")]
    # 0 行の表(取り込みで、空のファイルを読んだときと同じ形)
    empty = convert_orders(pd.DataFrame(columns=EVENT_COLUMNS))

    normal_path = write_orders(normal, "2017-10-02", tmp_path, "batch1")
    empty_path = write_orders(empty, "2017-10-07", tmp_path, "batch1")

    # 2つのファイルの列と型が、完全に同じ
    assert pq.read_schema(empty_path).equals(pq.read_schema(normal_path))
