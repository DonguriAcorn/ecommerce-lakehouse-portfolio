"""指定した期間の Raw(data/raw/olist/<表>/ingest_date=<日>/)を、S3 の raw/ へ上げる。

1日だけ(--date)でも、期間(--start と --end)でも使える。
aws s3 sync の代わり(Airflow のコンテナには aws CLI がない)。日のフォルダだけを見るので速い。
S3 のキーはファイルの場所から決まるので、同じ日を流し直すと同じキーを上書きする(冪等)。
"""

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

import boto3

# ローカルの Raw の置き場所と、S3 の中の接頭辞(ローカルの olist/... の前に raw/ を付ける)
RAW_DIR = Path("data/raw")
S3_PREFIX = "raw"


def days_between(start: str, end: str) -> list[str]:
    """start から end まで(両端を含む)の日付を、YYYY-MM-DD の文字列で順に返す。"""
    # 文字列を日付に直す(形が違えば、ここで ValueError になる)
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    # 期間が逆なら、黙って 0 件で終わらず、ここで止める
    if last < first:
        raise ValueError(f"期間が逆です: {start} > {end}")
    # first から1日ずつ足して、last までの日数ぶん並べる(+ 1 は最後の日を含めるため)
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def find_raw_files(raw_dir: Path, start: str, end: str) -> list[Path]:
    """期間の各日のフォルダにある Parquet を、日付順、その中で名前順に返す。"""
    files: list[Path] = []
    for day in days_between(start, end):
        # 全表の ingest_date=<日> フォルダを探す(届かない日の表には、フォルダがない)
        # 例: olist/orders_events/ingest_date=2016-09-04/orders_events_20160904.parquet
        files.extend(sorted(raw_dir.glob(f"olist/*/ingest_date={day}/*.parquet")))
    return files


def main() -> int:
    """実行の流れ: 引数 → 期間のファイルを探す → 1つずつ S3 へ。成功は 0、失敗は 1 を返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    # 1日だけ(従来どおり)か、期間(--start と --end)のどちらか
    parser.add_argument("--date", help="上げる取り込み日(YYYY-MM-DD)")
    parser.add_argument("--start", help="期間の最初の日(YYYY-MM-DD)")
    parser.add_argument("--end", help="期間の最後の日(YYYY-MM-DD、この日も含む)")
    args = parser.parse_args()

    # --date は「最初も最後も同じ日の期間」として扱い、以降のコードを1本にする
    if args.date:
        start, end = args.date, args.date
    elif args.start and args.end:
        start, end = args.start, args.end
    else:
        # 使い方を表示して終了する
        parser.error("--date か、--start と --end の両方を指定してください")

    # 上げ先のバケット名は、環境変数から読む(アカウント ID を含むので、ファイルに書かない)
    bucket = os.environ["LAKE_BUCKET"]
    # S3 の操作役(認証は AWS_PROFILE の ingest ロール。Airflow のタスクが渡す)
    s3 = boto3.client("s3")

    uploaded = 0
    for file in find_raw_files(RAW_DIR, start, end):
        key = f"{S3_PREFIX}/{file.relative_to(RAW_DIR).as_posix()}"
        # 1ファイルを上げる(同じキーがあれば上書き)
        s3.upload_file(str(file), bucket, key)
        print(f"{file} -> s3://{bucket}/{key}")
        uploaded += 1

    # 期間ぜんたいで1つも上げられなければ失敗にする(取り込み忘れで、空のまま先へ進まないため)
    if uploaded == 0:
        print(f"{start}〜{end}: 上げるファイルがありません")
        return 1
    print(f"{start}〜{end}: {uploaded} ファイルを上げました")
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
