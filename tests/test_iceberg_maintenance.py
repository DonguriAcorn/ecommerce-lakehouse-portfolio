"""iceberg_maintenance のテスト。Athena には繋がず、流す SQL の文面だけ確かめる。"""

from ingestion.iceberg_maintenance import SNAPSHOT_AGE_SECONDS, TABLES, build_statements


def test_build_statements_order_and_content():
    sqls = build_statements("ecom_dev_silver", "orders_from_events")
    # 順番は、設定 → OPTIMIZE → VACUUM(VACUUM が最後でないと、まとめる前のファイルを消せない)
    assert sqls[0].startswith("ALTER TABLE ecom_dev_silver.orders_from_events SET TBLPROPERTIES")
    assert sqls[1] == "OPTIMIZE ecom_dev_silver.orders_from_events REWRITE DATA USING BIN_PACK"
    assert sqls[2] == "VACUUM ecom_dev_silver.orders_from_events"


def test_snapshot_age_is_seven_days():
    # 保存期間が 7 日(604800 秒)で、設定の文面にも入っている
    assert SNAPSHOT_AGE_SECONDS == 7 * 86400
    assert "'604800'" in build_statements("db", "t")[0]


def test_tables_are_the_seven_silver_tables():
    # 7表で、重複がない
    assert len(TABLES) == 7 and len(set(TABLES)) == 7
