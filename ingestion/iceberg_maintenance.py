"""Silver の7表を、1表ずつ OPTIMIZE → VACUUM する(Iceberg の整理)。

手動で動かす。実行前に、保存期間(7日)の設定を毎回入れ直す(何度入れても同じ)。
表ごとに、整理の前後のファイル数とスナップショット数を出す。
"""

import argparse
import time

import boto3

# 7表(Silver のテーブル名)
TABLES = [
    "orders_from_events",
    "order_items",
    "reviews",
    "customers",
    "sellers",
    "products",
    "product_category_name_translation",
]
# 保存期間: 7日(604800秒)。2026-11-14 に決めた
SNAPSHOT_AGE_SECONDS = 604800


def build_statements(database: str, table: str) -> list[str]:
    """1表ぶんの SQL を、流す順番に並べて返す(AWS に触れないのでテストしやすい)。"""
    full = f"{database}.{table}"
    return [
        # 保存期間の設定。同じ値を何度入れても同じ(冪等)
        f"ALTER TABLE {full} SET TBLPROPERTIES "
        f"('vacuum_max_snapshot_age_seconds'='{SNAPSHOT_AGE_SECONDS}')",
        # 小さいファイルを、大きなファイルにまとめる(古いファイルはまだ残る)
        f"OPTIMIZE {full} REWRITE DATA USING BIN_PACK",
        # 期限切れの版と、使われなくなったファイルを消す(戻れない)
        f"VACUUM {full}",
    ]


def run_query(athena, workgroup: str, sql: str) -> list[list[str]]:
    """SQL を1本流し、終わるまで待って、結果の行を返す。失敗したら例外を出す。"""
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=workgroup)["QueryExecutionId"]
    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if status["State"] == "SUCCEEDED":
            break
        if status["State"] in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason")
            raise RuntimeError(f"{sql[:60]}... が {status['State']}: {reason}")
        time.sleep(2)
    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    # 1行目は列名なので除き、値だけの行にして返す(DDL など結果のない SQL は空になる)
    return [[c.get("VarCharValue", "") for c in r["Data"]] for r in rows[1:]]


def measure(athena, workgroup: str, database: str, table: str) -> str:
    """現在の版のファイル数・大きさ・スナップショット数を、1行の文にして返す。"""
    files = run_query(
        athena,
        workgroup,
        f'select count(*), coalesce(sum(file_size_in_bytes), 0) from "{database}"."{table}$files"',
    )[0]
    snaps = run_query(
        athena, workgroup, f'select count(*) from "{database}"."{table}$snapshots"'
    )[0]
    return f"ファイル {files[0]} 個 / {files[1]} バイト / スナップショット {snaps[0]} 個"


def main() -> int:
    """実行の流れ: 引数 → 表ごとに(前を測る → 整理 → 後を測る)。成功は 0、失敗は 1 を返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="dev", help="環境(dev / test / prod)")
    parser.add_argument("--table", action="append", help="対象の表(省略すると7表すべて)")
    args = parser.parse_args()

    # 環境から、Glue のデータベース名と Athena の workgroup を決める
    database = f"ecom_{args.env}_silver"
    workgroup = f"ecom-{args.env}"
    # Athena の操作役(認証は AWS_PROFILE の transform ロール。Airflow のタスクが渡す)
    athena = boto3.client("athena")

    failed = []
    for table in args.table or TABLES:
        try:
            print(f"[{table}] 前: {measure(athena, workgroup, database, table)}")
            for sql in build_statements(database, table):
                run_query(athena, workgroup, sql)
            print(f"[{table}] 後: {measure(athena, workgroup, database, table)}")
        except Exception as e:  # 1表の失敗で、残りの表を止めない
            print(f"[{table}] 失敗: {e}")
            failed.append(table)

    # 1つでも失敗したら、タスクを失敗にする(Airflow の画面で気づけるように)
    if failed:
        print(f"失敗した表: {', '.join(failed)}")
        return 1
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
