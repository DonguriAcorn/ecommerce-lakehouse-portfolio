"""その日の Raw(data/raw/olist/<表>/ingest_date=<日>/)を、S3 の raw/ へ上げる。

aws s3 sync の代わり(Airflow のコンテナには aws CLI がない)。その日のフォルダだけを見るので速い。
S3 のキーはファイルの場所から決まるので、同じ日を流し直すと同じキーを上書きする(冪等)。
"""

import argparse
import os
from pathlib import Path

import boto3

# ローカルの Raw の置き場所と、S3 の中の接頭辞(ローカルの olist/... の前に raw/ を付ける)
RAW_DIR = Path("data/raw")
S3_PREFIX = "raw"


def main() -> int:
    """実行の流れ: 引数 → その日のファイルを探す → 1つずつ S3 へ。成功は 0、失敗は 1 を返す。"""
    # コマンドの引数: 上げる日(YYYY-MM-DD)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="上げる取り込み日(YYYY-MM-DD)")
    args = parser.parse_args()

    # 上げ先のバケット名は、環境変数から読む(アカウント ID を含むので、ファイルに書かない)
    bucket = os.environ["LAKE_BUCKET"]
    # S3 の操作役(認証は AWS_PROFILE の ingest ロール。Airflow のタスクが渡す)
    s3 = boto3.client("s3")

    # 全表の ingest_date=<日> フォルダを探す(届かない日の表には、フォルダがない)
    uploaded = 0
    for file in sorted(RAW_DIR.glob(f"olist/*/ingest_date={args.date}/*.parquet")):
        # 例: olist/orders_events/ingest_date=2016-09-04/orders_events_20160904.parquet
        key = f"{S3_PREFIX}/{file.relative_to(RAW_DIR).as_posix()}"
        # 1ファイルを上げる(同じキーがあれば上書き)
        s3.upload_file(str(file), bucket, key)
        print(f"{file} -> s3://{bucket}/{key}")
        uploaded += 1

    # 1つも上げられなければ失敗にする(取り込み忘れで、空のまま先へ進まないため)
    if uploaded == 0:
        print(f"{args.date}: 上げるファイルがありません")
        return 1
    print(f"{args.date}: {uploaded} ファイルを上げました")
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
