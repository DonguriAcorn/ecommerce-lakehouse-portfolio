"""export_pub.py のうち、AWS に触れない部分のテスト。"""

from datetime import datetime, timezone
from decimal import Decimal

import pyarrow as pa
import pytest

from ingestion.export_pub import build_status, build_table, check_columns


def test_build_table_types_and_nulls():
    """文字列の行が、列の型どおりに変換され、空(None)は空のまま残る。"""
    # Athena の ColumnInfo と同じ形の列の情報
    column_info = [
        {"Name": "year_month", "Type": "varchar"},
        {"Name": "gmv", "Type": "decimal", "Precision": 38, "Scale": 2},
        {"Name": "items_sold", "Type": "bigint"},
        {"Name": "avg_review_score", "Type": "double"},
    ]
    rows = [
        ["2017-11", "1234.50", "10", "4.25"],
        ["2017-12", "99.99", "1", None],  # 星のない組は空
    ]
    table = build_table(column_info, rows)

    # 型が Parquet 向けに付いている
    assert table.schema.field("gmv").type == pa.decimal128(38, 2)
    assert table.schema.field("items_sold").type == pa.int64()
    assert table.schema.field("avg_review_score").type == pa.float64()
    # 値が正しく変換され、空は空のまま
    assert table.column("gmv").to_pylist() == [Decimal("1234.50"), Decimal("99.99")]
    assert table.column("avg_review_score").to_pylist() == [4.25, None]


def test_check_columns_stops_on_forbidden():
    """本人の ID が入っていたら、書く前に止まる。"""
    with pytest.raises(RuntimeError, match="customer_unique_id"):
        check_columns("pub_x", ["year_month", "customer_unique_id"])


def test_check_columns_allows_public_columns():
    """公開してよい列だけなら、止まらない。"""
    check_columns("pub_kpi_monthly", ["year_month", "customer_state", "gmv", "orders"])


def test_build_status():
    """時刻は UTC の形で、行数はそのまま入る。"""
    now = datetime(2026, 11, 28, 12, 0, 0, tzinfo=timezone.utc)
    status = build_status("dev", {"pub_kpi_monthly": 600}, "2018-10-17", now)
    assert status == {
        "exported_at": "2026-11-28T12:00:00Z",
        "source_env": "dev",
        "latest_purchase_date": "2018-10-17",
        "row_counts": {"pub_kpi_monthly": 600},
    }
