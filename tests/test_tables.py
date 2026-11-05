"""7つの表の共通の受付(registry、届く日の規則、型、ログ)を確かめるテスト(ADR 0011)。"""

import json
import sys
from decimal import Decimal

import pandas as pd
import pyarrow.parquet as pq
import pytest

from ingestion import run_ingest
from ingestion.ingest_table import convert_types, read_source, source_path, validate_rows
from ingestion.raw_writer import write_raw
from ingestion.run_log import RunLog
from ingestion.schema import (
    BOOL,
    CATEGORY_TRANSLATION,
    DECIMAL,
    FIRST_DAY,
    INT,
    LAST_DAY,
    ORDER_ITEMS,
    REGISTRY,
    REVIEWS,
    SELLERS,
    TIMESTAMP,
    expected,
)
from simulator.make_source_events import write_source_events
from simulator.table_sources import build_table_records, items_arrival, reviews_arrival

# 型ごとの、届くファイルに入る正しい値の例(空の日と行のある日の型を比べるときに使う)
SAMPLE_VALUES = {
    TIMESTAMP: "2017-10-02 10:56:33",
    INT: "1",
    DECIMAL: "58.90",
    BOOL: False,
}


def sample_row(spec) -> dict:
    """registry の型に合った、正しい値の1行を作る(文字列の列は "x")。"""
    return {column: SAMPLE_VALUES.get(kind, "x") for column, kind in spec.columns.items()}


def write_csv(path, header: str, *lines: str, bom: bool = False) -> None:
    """小さな CSV を書く(bom=True で、先頭に BOM を付ける)。"""
    text = "\n".join([header, *lines]) + "\n"
    path.write_text(("﻿" if bom else "") + text, encoding="utf-8")


def make_olist(tmp_path):
    """テスト用の小さな元データ(orders、order_items、reviews、sellers、英訳)を作る。"""
    olist = tmp_path / "olist"
    olist.mkdir()
    # o1 は 2017-10-02、o2 は 2017-10-05 に購入
    write_csv(
        olist / "olist_orders_dataset.csv",
        "order_id,customer_id,order_status,order_purchase_timestamp",
        "o1,c1,delivered,2017-10-02 10:56:33",
        "o2,c2,delivered,2017-10-05 08:00:00",
    )
    write_csv(
        olist / "olist_order_items_dataset.csv",
        "order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,freight_value",
        "o1,1,p1,s1,2017-10-06 10:56:33,58.90,13.29",
        "o2,1,p2,s1,2017-10-09 08:00:00,0.10,0.20",
    )
    # r1 は購入より前の日に答えた(くせのある行)。r2 は購入の 3 日後に答えた。
    # r2 の本文には、改行・引用符・絵文字を入れる
    write_csv(
        olist / "olist_order_reviews_dataset.csv",
        "review_id,order_id,review_score,review_comment_title,review_comment_message,"
        "review_creation_date,review_answer_timestamp",
        "r1,o1,5,,,2017-09-30 00:00:00,2017-10-01 12:00:00",
        'r2,o2,1,ruim,"caixa ""amassada""\nnão gostei 😞",2017-10-07 00:00:00,2017-10-08 09:00:00',
    )
    # 郵便番号の先頭の 0 と、"NA" という名前の市(空と取り違えない)
    write_csv(
        olist / "olist_sellers_dataset.csv",
        "seller_id,seller_zip_code_prefix,seller_city,seller_state",
        "s1,01001,NA,SP",
    )
    # 英訳の CSV は、先頭に BOM が付いている(元データと同じ)
    write_csv(
        olist / "product_category_name_translation.csv",
        "product_category_name,product_category_name_english",
        "beleza_saude,health_beauty",
        bom=True,
    )
    return olist


def test_registry_lists_only_existing_columns():
    """どの表も、必須・キー・PII の列が、列の一覧の中にある(打ち間違いを防ぐ)。"""
    assert len(REGISTRY) == 7
    for name, spec in REGISTRY.items():
        assert name == spec.name
        assert set(spec.required) <= set(spec.columns)
        assert set(spec.keys) <= set(spec.columns)
        assert set(spec.pii) <= set(spec.columns)


def test_expected_follows_kind_and_period():
    """追記型は期間の毎日、一括型は最初の日だけ。reviews だけ期間が 2018-10-29 まで延びる。"""
    # 一括型: 最初の日だけ
    assert expected(SELLERS, FIRST_DAY)
    assert not expected(SELLERS, "2017-10-02")
    # 追記型: 最初の日から最後の日まで。期間の外は届かない
    assert expected(ORDER_ITEMS, "2017-10-02")
    assert expected(ORDER_ITEMS, LAST_DAY)
    assert not expected(ORDER_ITEMS, "2018-10-19")
    assert not expected(ORDER_ITEMS, "2016-09-03")
    # reviews は、最後の注文の後も答えが届く
    assert expected(REVIEWS, "2018-10-29")
    assert not expected(REVIEWS, "2018-10-30")


def test_arrival_rules_for_items_and_reviews():
    """明細は親の購入日、レビューは max(答えた日, 購入日) に届く。"""
    purchase = pd.Series(pd.to_datetime(["2017-10-02", "2017-10-05"]), index=["o1", "o2"])
    items = pd.DataFrame({"order_id": ["o1", "o2"]})
    assert list(items_arrival(items, purchase)) == list(purchase)

    reviews = pd.DataFrame(
        {
            "order_id": ["o1", "o2"],
            # o1 は購入より前に答えている → 購入日に寄せる。o2 は答えた日
            "review_answer_timestamp": ["2017-10-01 12:00:00", "2017-10-08 09:00:00"],
        }
    )
    arrival = reviews_arrival(reviews, purchase)
    assert list(arrival) == list(pd.to_datetime(["2017-10-02", "2017-10-08"]))


def test_build_table_records_keeps_text_values(tmp_path):
    """CSV の値を文字列のまま保つ(先頭の 0、"NA" の市、BOM 付きの列名)。一括型は最初の日に届く。"""
    olist = make_olist(tmp_path)

    sellers = build_table_records(SELLERS, olist)
    assert sellers.loc[0, "seller_zip_code_prefix"] == "01001"
    assert sellers.loc[0, "seller_city"] == "NA"
    assert (sellers["arrival_date"] == FIRST_DAY).all()

    # BOM が外れて、1列目の名前がそのまま読める
    translation = build_table_records(CATEGORY_TRANSLATION, olist)
    assert translation.loc[0, "product_category_name"] == "beleza_saude"


def ingest_one_day(spec, source_dir, day, tmp_path):
    """1日分を、取り込みと同じ手順(読む → 検証 → 型 → Raw)で書き、Raw の表を返す。"""
    log = RunLog(tmp_path / "logs", spec.name, "batch1")
    raw = read_source(source_path(source_dir, spec, pd.Timestamp(day)), spec, log, day)
    good, bad = validate_rows(raw, spec, log, day)
    assert bad.empty
    out_path = write_raw(convert_types(good, spec), spec, day, tmp_path / "raw", "batch1")
    return pq.read_table(out_path).to_pandas()


def test_order_items_round_trip_keeps_exact_amounts(tmp_path):
    """明細を親の購入日のファイルに書き、取り込むと、金額が誤差なく decimal になる。"""
    olist = make_olist(tmp_path)
    records = build_table_records(ORDER_ITEMS, olist)
    days = pd.date_range("2017-10-01", "2017-10-06", freq="D")
    write_source_events(records, tmp_path / "source", ORDER_ITEMS, days)

    # 行のない日(10-03)も、空のファイルがある
    empty = source_path(tmp_path / "source", ORDER_ITEMS, pd.Timestamp("2017-10-03"))
    assert empty.exists() and empty.stat().st_size == 0

    written = ingest_one_day(ORDER_ITEMS, tmp_path / "source", "2017-10-05", tmp_path)
    # o2 の明細だけが 10-05 に届き、0.10 + 0.20 がちょうど 0.30 になる
    # (float だと 0.30000000000000004)
    assert list(written["order_id"]) == ["o2"]
    assert written.loc[0, "price"] == Decimal("0.10")
    assert written.loc[0, "price"] + written.loc[0, "freight_value"] == Decimal("0.30")
    # Parquet の型は int32(Glue の int 列と合わせる)
    raw_file = next((tmp_path / "raw").rglob("*.parquet"))
    assert str(pq.read_schema(raw_file).field("order_item_id").type) == "int32"


def test_reviews_text_survives_round_trip(tmp_path):
    """レビューの本文の改行・引用符・絵文字が、届くファイルと Raw を通っても変わらない。"""
    olist = make_olist(tmp_path)
    records = build_table_records(REVIEWS, olist)
    days = pd.date_range("2017-10-01", "2017-10-08", freq="D")
    write_source_events(records, tmp_path / "source", REVIEWS, days)

    written = ingest_one_day(REVIEWS, tmp_path / "source", "2017-10-08", tmp_path)
    assert written.loc[0, "review_comment_message"] == 'caixa "amassada"\nnão gostei 😞'
    # 空のタイトルは、空文字でなく null になる
    first = ingest_one_day(REVIEWS, tmp_path / "source", "2017-10-02", tmp_path)
    assert first.loc[0, "review_id"] == "r1"
    assert pd.isna(first.loc[0, "review_comment_title"])


@pytest.mark.parametrize("spec", list(REGISTRY.values()), ids=list(REGISTRY))
def test_empty_day_has_same_raw_types_as_normal_day(spec, tmp_path):
    """どの表でも、行のない日の Raw と、行のある日の Raw が、同じ列と型になる。"""
    normal = convert_types(pd.DataFrame([sample_row(spec)]), spec)
    empty = convert_types(pd.DataFrame(columns=list(spec.columns)), spec)

    normal_path = write_raw(normal, spec, "2017-10-02", tmp_path, "batch1")
    empty_path = write_raw(empty, spec, "2017-10-03", tmp_path, "batch1")
    assert pq.read_schema(empty_path).equals(pq.read_schema(normal_path))


def test_validate_rows_quarantines_bad_numbers(tmp_path):
    """金額の書式の誤り(コンマ、小数 3 桁)と、整数でない番号を隔離する。"""
    log = RunLog(tmp_path / "logs", ORDER_ITEMS.name, "batch1")
    good_row = sample_row(ORDER_ITEMS)
    raw = pd.DataFrame(
        [
            good_row,
            {**good_row, "price": "12,50"},  # コンマ
            {**good_row, "freight_value": "1.234"},  # 小数 3 桁(丸めると値が変わる)
            {**good_row, "order_item_id": "1.5"},  # 整数でない
        ]
    )
    good, bad = validate_rows(raw, ORDER_ITEMS, log, "2017-10-02", quarantine_limit=1.0)
    assert len(good) == 1
    assert list(bad["_error_codes"]) == ["INVALID_DECIMAL", "INVALID_DECIMAL", "INVALID_INT"]


def run_main(monkeypatch, *args: str) -> int:
    """run_ingest をコマンドと同じ引数で動かす(作業フォルダは tmp_path に移してある)。"""
    monkeypatch.setattr(sys, "argv", ["run_ingest", *args])
    return run_ingest.main()


def read_day_results(tmp_path) -> list[dict]:
    """ログから、1日ごとの結果(DAY_RESULT)の行だけを取り出す。"""
    results = []
    for path in (tmp_path / "data" / "logs").rglob("events.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["code"] == "DAY_RESULT":
                results.append(record)
    return sorted(results, key=lambda record: record["ingest_date"])


def test_snapshot_reads_first_day_and_ignores_unexpected_files(tmp_path, monkeypatch):
    """一括型は最初の日だけ読む。届かないはずの日のファイルは読まずに数え、ログに残す。"""
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data" / "source" / SELLERS.name
    row = json.dumps(sample_row(SELLERS)) + "\n"
    # 最初の日の正しいファイルと、届かないはずの 2 日目に誤って置かれたファイル
    for day in [FIRST_DAY, FIRST_DAY + pd.Timedelta(days=1)]:
        path = source_path(source, SELLERS, day)
        path.parent.mkdir(parents=True)
        path.write_text(row, encoding="utf-8")

    args = ["--table", "sellers", "--start", "2016-09-04", "--end", "2016-09-06"]
    assert run_main(monkeypatch, *args) == 0

    # Raw は最初の日だけ
    raw_files = list((tmp_path / "data" / "raw" / "olist" / "sellers").rglob("*.parquet"))
    assert [path.name for path in raw_files] == ["sellers_20160904.parquet"]
    # 1日ごとの結果に、健康状態ページ用の項目がそろう
    results = read_day_results(tmp_path)
    assert [r["status"] for r in results] == ["OK", "SKIPPED_NOT_EXPECTED", "SKIPPED_NOT_EXPECTED"]
    assert [r["unexpected_files"] for r in results] == [0, 1, 0]
    assert results[0]["rows"] == 1 and results[0]["quarantined"] == 0
    assert all(r["table"] == "sellers" for r in results)


def test_missing_expected_file_stops_and_logs_day(tmp_path, monkeypatch):
    """届くはずの日にファイルがなければ止め、その日の結果に止まった理由を残す。"""
    monkeypatch.chdir(tmp_path)
    args = ["--table", "order_items", "--start", "2017-10-02", "--end", "2017-10-02"]
    assert run_main(monkeypatch, *args) == 1
    results = read_day_results(tmp_path)
    assert results[0]["status"] == "SOURCE_NOT_FOUND"
    assert results[0]["level"] == "ERROR"


def test_same_day_twice_gives_same_raw(tmp_path):
    """同じ日を2回取り込んでも、監査カラムを除いた Raw の中身は同じ(冪等)。"""
    olist = make_olist(tmp_path)
    records = build_table_records(ORDER_ITEMS, olist)
    days = pd.date_range("2017-10-01", "2017-10-06", freq="D")
    write_source_events(records, tmp_path / "source", ORDER_ITEMS, days)

    first = ingest_one_day(ORDER_ITEMS, tmp_path / "source", "2017-10-02", tmp_path)
    second = ingest_one_day(ORDER_ITEMS, tmp_path / "source", "2017-10-02", tmp_path)
    business = list(ORDER_ITEMS.columns)
    pd.testing.assert_frame_equal(first[business], second[business])
