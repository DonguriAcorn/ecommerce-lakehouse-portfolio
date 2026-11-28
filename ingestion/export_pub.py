"""公開用の pub_ の4表を Athena で読み、app/data/ に Parquet と status.json を書く(ADR 0018)。

実行: AWS_PROFILE=ecom-dev-transform uv run python -m ingestion.export_pub --env dev
"""

import argparse
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

# 書き出す表と、並べる順(毎回同じ順にして、Git の差分を「中身が変わった所」だけにする)
TABLES = {
    "pub_kpi_monthly": "year_month, customer_state",
    "pub_repeat_monthly": "year_month, customer_state",
    "pub_repeat_yearly": "year, customer_state",  # 年別のリピート率用(月別は足せないため)
    "pub_category_monthly": "year_month, category_name",
}
# 公開してはいけない列。dbt の contract でも止まるが、書く直前にもう一度確かめる(二重の守り)
FORBIDDEN_COLUMNS = {
    "customer_unique_id",
    "customer_sk",
    "customer_id",
    "order_id",
    "product_id",
    "customer_zip_code_prefix",
}


def arrow_type(info: dict) -> pa.DataType:
    """Athena の列の型(ColumnInfo)を、Parquet の型に置き換える。"""
    t = info["Type"]
    if t == "varchar":
        return pa.string()
    if t == "bigint":
        return pa.int64()
    if t == "double":
        return pa.float64()
    if t == "decimal":  # 金額。小数の誤差が出ないよう、decimal のまま持つ
        return pa.decimal128(info["Precision"], info["Scale"])
    raise ValueError(f"想定していない型: {t}")


def convert(value: str | None, typ: pa.DataType):
    """Athena から文字列で届く値を、型に合わせた Python の値にする。空は None のまま。"""
    if value is None:
        return None
    if pa.types.is_int64(typ):
        return int(value)
    if pa.types.is_float64(typ):
        return float(value)
    if pa.types.is_decimal(typ):
        return Decimal(value)
    return value


def build_table(column_info: list[dict], rows: list[list[str | None]]) -> pa.Table:
    """列の情報と、文字列の行から、型つきの表(Arrow)を作る(AWS に触れないのでテストしやすい)。"""
    names = [c["Name"] for c in column_info]
    types = [arrow_type(c) for c in column_info]
    # 列ごとに、全行の値を型に合わせて変換し、1本の配列にする
    columns = [
        pa.array([convert(row[i], types[i]) for row in rows], type=types[i])
        for i in range(len(names))
    ]
    return pa.table(columns, names=names)


def check_columns(table_name: str, names: list[str]) -> None:
    """公開してはいけない列が入っていたら、書く前に止める。"""
    bad = FORBIDDEN_COLUMNS & set(names)
    if bad:
        raise RuntimeError(f"{table_name} に公開できない列があります: {sorted(bad)}")


def build_status(
    env: str, row_counts: dict[str, int], latest_purchase_date: str, now: datetime
) -> dict:
    """健康状態ページ用の status.json の中身を作る。"""
    return {
        "exported_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),  # export した時刻(UTC)
        "source_env": env,  # どの環境の Gold から作ったか
        "latest_purchase_date": latest_purchase_date,  # データの中の最新の購入日
        "row_counts": row_counts,  # 表ごとの行数
    }


def run(athena, workgroup: str, sql: str) -> tuple[list[dict], list[list[str | None]]]:
    """SQL を流して終わるまで待ち、列の情報と、全部の行(1000 行を超えてもページをめくる)を返す。"""
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=workgroup)["QueryExecutionId"]
    # 終わるまで2秒おきに状態を見る。失敗したら例外で止める
    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if status["State"] == "SUCCEEDED":
            break
        if status["State"] in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason")
            raise RuntimeError(f"{sql[:60]}... が {status['State']}: {reason}")
        time.sleep(2)

    column_info, rows = [], []
    # get_query_results は1回に 1000 行までなので、ページをめくって全部読む
    pages = athena.get_paginator("get_query_results").paginate(QueryExecutionId=qid)
    for i, page in enumerate(pages):
        result = page["ResultSet"]
        if i == 0:
            column_info = result["ResultSetMetadata"]["ColumnInfo"]
        # 空の値(NULL)は VarCharValue が付かないので、get で None にする
        page_rows = [[c.get("VarCharValue") for c in r["Data"]] for r in result["Rows"]]
        rows.extend(page_rows[1:] if i == 0 else page_rows)  # 1ページ目の1行目は列名なので除く
    return column_info, rows


def main() -> int:
    """流れ: 引数 → 3表を読んで Parquet に書く → 最新の購入日を読む → status.json を書く。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="dev", choices=["dev", "prod"], help="読む Gold の環境")
    parser.add_argument("--out-dir", default="app/data", help="書き出す場所")
    args = parser.parse_args()

    # 環境から、Glue のデータベース名と Athena の workgroup を決める
    database = f"ecom_{args.env}_gold"
    workgroup = f"ecom-{args.env}"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    athena = boto3.client("athena")  # 認証は AWS_PROFILE の transform ロール

    # 3表を1つずつ、読む → 確かめる → Parquet に書く
    row_counts = {}
    for table_name, order_by in TABLES.items():
        sql = f"select * from {database}.{table_name} order by {order_by}"
        column_info, rows = run(athena, workgroup, sql)
        table = build_table(column_info, rows)
        check_columns(table_name, table.column_names)
        pq.write_table(table, out_dir / f"{table_name}.parquet", compression="zstd")
        row_counts[table_name] = table.num_rows
        print(f"[{table_name}] {table.num_rows} 行を書いた")

    # 健康状態ページ用: データの中の最新の購入日
    sql = f"select cast(max(purchase_date) as varchar) from {database}.fact_orders"
    _, latest = run(athena, workgroup, sql)
    status = build_status(args.env, row_counts, latest[0][0], datetime.now(timezone.utc))
    (out_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    print(f"status.json を書いた: {status}")
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
