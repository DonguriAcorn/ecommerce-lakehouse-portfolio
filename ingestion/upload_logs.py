"""その日(run_date)の取り込みログを、S3 の logs/ へ上げる。

ローカルの data/logs/ingest/.../run_date=<日>/batch_id=<id>/events.jsonl を、
同じ形のキーで S3 の logs/ へ置く。キーはファイルの場所から決まるので、
同じ日を2回上げても同じキーを上書きするだけ(冪等)。
"""

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

import boto3

# ローカルのログの置き場所と、S3 の中の接頭辞
LOG_DIR = Path("data/logs")
S3_PREFIX = "logs"


def find_log_files(log_dir: Path, run_date: str) -> list[Path]:
    """run_date のフォルダの下にある events.jsonl を、名前順で返す。"""
    # データセット → 表 → run_date → batch_id の下の events.jsonl を探す
    # (AWS に触れないのでテストしやすい)
    return sorted(log_dir.glob(f"ingest/*/*/run_date={run_date}/*/events.jsonl"))


def s3_key(log_dir: Path, file: Path) -> str:
    """ローカルのファイルの場所から、S3 のキーを作る。"""
    # 例: logs/ingest/olist/orders_events/run_date=2026-11-14/batch_id=.../events.jsonl
    return f"{S3_PREFIX}/{file.relative_to(log_dir).as_posix()}"


def main() -> int:
    """実行の流れ: 引数 → ログを探す → 1つずつ S3 へ。成功は 0、失敗は 1 を返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    # 省略したら、UTC の今日(run_log.py がフォルダ名に使う日付と同じ決め方)
    parser.add_argument(
        "--run-date",
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="上げるログの run_date(YYYY-MM-DD)。省略すると UTC の今日",
    )
    args = parser.parse_args()

    # 上げ先のバケット名は、環境変数から読む(アカウント ID を含むので、ファイルに書かない)
    bucket = os.environ["LAKE_BUCKET"]
    # S3 の操作役(認証は AWS_PROFILE の ingest ロール。Airflow のタスクが渡す)
    s3 = boto3.client("s3")

    files = find_log_files(LOG_DIR, args.run_date)
    for file in files:
        # 1ファイルを上げる(同じキーがあれば上書き)
        key = s3_key(LOG_DIR, file)
        s3.upload_file(str(file), bucket, key)
        print(f"{file} -> s3://{bucket}/{key}")

    # ログが1つもないのは、取り込みが動く前に落ちたなどの異常。気づけるよう失敗にする
    if not files:
        print(f"run_date={args.run_date}: 上げるログがありません")
        return 1
    print(f"run_date={args.run_date}: {len(files)} ファイルを上げました")
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
