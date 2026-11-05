"""届いたファイル(data/source/)を、指定した表と期間で、日付ごとに Raw に取り込む。

1日ずつ: 届く日か確かめる → 読む → 検証 → 隔離 → 型を付ける → 監査カラムを足して Raw に書く。
表ごとの違いは ingestion/schema.py の registry にあり、受付の流れはどの表でも同じ(ADR 0011)。
"""

import argparse
from pathlib import Path

import pandas as pd

from ingestion.ingest_table import (
    ExtraCheck,
    convert_types,
    read_source,
    source_path,
    validate_rows,
)
from ingestion.orders_checks import check_orders_events
from ingestion.quarantine import IngestStop, write_quarantine
from ingestion.raw_writer import write_raw
from ingestion.run_log import RunLog
from ingestion.schema import REGISTRY, expected

# 入力(届いたファイル)と、出力(Raw、ログ、隔離)の置き場所。すべて Git の管理外
SOURCE_ROOT = Path("data/source")  # この下の <表の名前>/ を読む
RAW_DIR = Path("data/raw")
LOG_DIR = Path("data/logs")
QUARANTINE_DIR = Path("data/quarantine")
# ログに入れる、処理の段階の名前
STAGE_RUN = "RUN"  # 実行全体の開始と終了
STAGE_WRITE = "WRITE"  # Raw への書き出し

# 表だけの追加の検証(共通の検証のあとに足す)。ない表は、共通の検証だけ
EXTRA_CHECKS: dict[str, ExtraCheck] = {"orders_events": check_orders_events}


def main() -> int:
    """実行の流れ: 引数 → 1日ずつ取り込む。成功は 0、停止は 1 を返す。"""
    # コマンドの引数(--table、--start、--end)を読み取る準備
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table", default="orders_events", choices=list(REGISTRY), help="取り込む表"
    )
    parser.add_argument("--start", required=True, help="最初の日付(YYYY-MM-DD)")
    parser.add_argument(
        "--end", required=True, help="最後の日付(YYYY-MM-DD、この日も含む)"
    )
    # 入力と出力の場所。省略すると、data/source/<表の名前>/ と data/raw/
    parser.add_argument("--source-dir", type=Path, default=None, help="届いたファイルの場所")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR, help="Raw の書き出し先")
    args = parser.parse_args()

    # 表の取扱説明書と、届いたファイルの場所
    spec = REGISTRY[args.table]
    source_dir = args.source_dir or SOURCE_ROOT / spec.name
    extra_check = EXTRA_CHECKS.get(spec.name)

    # 1回の実行を見分ける ID(例: 20261025T103000Z)
    batch_id = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    log = RunLog(LOG_DIR, spec.name, batch_id)
    log.write(
        "INFO", STAGE_RUN, "RUN_START", f"取り込みを始めます / {args.start} 〜 {args.end}"
    )

    # 終了時のまとめに使う、書いた日数、行数、隔離した行数、届かない日に置かれたファイルの数
    days, rows, quarantined, unexpected = 0, 0, 0, 0
    ingest_date = args.start
    try:
        for day in pd.date_range(args.start, args.end, freq="D"):
            ingest_date = f"{day:%Y-%m-%d}"
            # その日に届いたファイル(届いた日 = 取り込む日。ingest_date = arrival_date)
            path = source_path(source_dir, spec, day)

            # 届かないはずの日(一括型の2日目以降、期間の外)は、読まずに飛ばす。
            # ファイルが置かれていても無視し、数だけ数える
            if not expected(spec, day):
                found = int(path.exists())
                unexpected += found
                log.day_result(ingest_date, "SKIPPED_NOT_EXPECTED", unexpected_files=found)
                continue

            # 読む(ない・壊れている → 止める)、検証する(隔離が多すぎる → 止める)
            raw = read_source(path, spec, log, ingest_date)
            good, bad = validate_rows(raw, spec, log, ingest_date, extra_check=extra_check)
            # 隔離する行があれば、Parquet に書いて残す
            quarantine_path = write_quarantine(bad, QUARANTINE_DIR, batch_id, spec.name)
            if quarantine_path is not None:
                print(f"{ingest_date}: 隔離 {len(bad)} 行 -> {quarantine_path}")
                quarantined += len(bad)

            # 良い行を Raw の型にして書く
            try:
                out_path = write_raw(
                    convert_types(good, spec), spec, day, args.raw_dir, batch_id
                )
            except OSError:
                # ディスクがいっぱい、書き込み権限がない、など。理由をログに書いてから止める
                log.write(
                    "ERROR",
                    STAGE_WRITE,
                    "WRITE_FAILED",
                    "Raw の書き出しに失敗しました",
                    ingest_date=ingest_date,
                )
                raise IngestStop("WRITE_FAILED") from None
            days += 1
            rows += len(good)
            log.day_result(ingest_date, "OK", rows=len(good), quarantined=len(bad))
            print(f"{ingest_date}: {len(good)} 行 -> {out_path}")
    except IngestStop as stop:
        # 途中で止めたとき。止まった日の結果と、止まるまでに書いた量を記録して、失敗(1)で終わる
        log.day_result(ingest_date, str(stop))
        log.write(
            "INFO",
            STAGE_RUN,
            "RUN_END",
            f"結果: 停止 ({stop}) / 書き出し {days}日 {rows}行",
        )
        return 1

    # 最後まで進んだとき。書き出した量と、隔離した行数、届かない日のファイルの数を記録する
    log.write(
        "INFO",
        STAGE_RUN,
        "RUN_END",
        f"結果: 成功 / 書き出し {days}日 {rows}行 / 隔離 {quarantined}行"
        f" / 届かない日のファイル {unexpected}個",
    )
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
