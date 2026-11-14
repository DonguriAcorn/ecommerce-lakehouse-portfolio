"""upload_raw のテスト。AWS には繋がず、期間の数え方とファイルの選び方だけ確かめる。"""

from pathlib import Path

import pytest

from ingestion.upload_raw import days_between, find_raw_files


def _make(raw_dir: Path, table: str, day: str) -> Path:
    # 空の Parquet を、ingest_date=<日> フォルダごと作る
    f = raw_dir / "olist" / table / f"ingest_date={day}" / f"{table}_{day}.parquet"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"")
    return f


def test_days_between_includes_both_ends():
    # 両端を含む3日ぶんが、順に返る
    assert days_between("2016-09-04", "2016-09-06") == ["2016-09-04", "2016-09-05", "2016-09-06"]


def test_days_between_single_day():
    # 同じ日どうしなら、その1日だけ(--date はこの形で扱う)
    assert days_between("2016-09-04", "2016-09-04") == ["2016-09-04"]


def test_days_between_crosses_month_end():
    # 月をまたいでも、カレンダーどおりに数える
    assert days_between("2016-09-30", "2016-10-01") == ["2016-09-30", "2016-10-01"]


def test_days_between_rejects_reversed_period():
    # 期間が逆なら ValueError
    with pytest.raises(ValueError):
        days_between("2016-09-06", "2016-09-04")


def test_find_raw_files_picks_only_the_period_in_date_order(tmp_path):
    # 期間内の2日(2表と1表)と、期間外の1日を置く
    d4_orders = _make(tmp_path, "orders_events", "2016-09-04")
    d4_items = _make(tmp_path, "order_items", "2016-09-04")
    d6_orders = _make(tmp_path, "orders_events", "2016-09-06")
    _make(tmp_path, "orders_events", "2016-09-07")
    # 05 日は届いていない日。期間内の3ファイルだけが、日付順(同じ日は名前順)で返る
    assert find_raw_files(tmp_path, "2016-09-04", "2016-09-06") == [
        d4_items,
        d4_orders,
        d6_orders,
    ]


def test_find_raw_files_returns_empty_when_nothing_arrived(tmp_path):
    # 1つも届いていなければ空(main はこれを失敗として扱う)
    assert find_raw_files(tmp_path, "2016-09-04", "2016-09-06") == []
