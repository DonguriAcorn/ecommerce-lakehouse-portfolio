"""届いた orders のイベントのファイル(data/source/)を、指定した期間の日付ごとに Raw に取り込む。

1日ずつ: 読む → 検証 → 隔離 → 型を付ける → 監査カラムを足して Raw に書く(ADR 0010)。
"""

import argparse
from pathlib import Path

import pandas as pd

from ingestion.ingest_events import convert_event_types, read_source_events, validate_events
from ingestion.quarantine import IngestStop, write_quarantine
from ingestion.raw_writer import write_events
from ingestion.run_log import RunLog

# 入力(届いたファイル)と、出力(Raw、ログ、隔離)の置き場所。すべて Git の管理外
SOURCE_DIR = Path("data/source/orders_events")
RAW_DIR = Path("data/raw")
LOG_DIR = Path("data/logs")
QUARANTINE_DIR = Path("data/quarantine")
# ログに入れる、テーブル名と処理の段階の名前
TABLE = "orders_events"
STAGE_RUN = "EVENTS_RUN"  # 実行全体の開始と終了
STAGE_WRITE = "EVENTS_WRITE"  # Raw への書き出し


def main() -> int:
    """実行の流れ: 引数 → 1日ずつ取り込む。成功は 0、停止は 1 を返す。"""
    # コマンドの引数(--start、--end)を読み取る準備
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="最初の日付(YYYY-MM-DD)")
    parser.add_argument(
        "--end", required=True, help="最後の日付(YYYY-MM-DD、この日も含む)"
    )
    # 入力と出力の場所。省略すると、これまでと同じ場所(遅延ありの確認では別の場所を指定する)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR, help="届いたファイルの場所")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR, help="Raw の書き出し先")
    args = parser.parse_args()

    # 1回の実行を見分ける ID(例: 20261025T103000Z)
    batch_id = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    log = RunLog(LOG_DIR, TABLE, batch_id)
    log.write(
        "INFO", STAGE_RUN, "RUN_START", f"取り込みを始めます / {args.start} 〜 {args.end}"
    )

    # 終了時のまとめに使う、日数、書いた行数、隔離した行数
    days, rows, quarantined = 0, 0, 0
    try:
        for day in pd.date_range(args.start, args.end, freq="D"):
            ingest_date = f"{day:%Y-%m-%d}"
            # その日に届いたファイル(届いた日 = 取り込む日。ingest_date = arrival_date)
            # 場所は引数 --source-dir から(省略時は SOURCE_DIR)
            path = (
                args.source_dir
                / f"arrival_date={ingest_date}"
                / f"orders_events_{day:%Y%m%d}.jsonl"
            )
            # 読む(ない・壊れている → 止める)、検証する(隔離が多すぎる → 止める)
            raw = read_source_events(path, log, ingest_date)
            good, bad = validate_events(raw, log, ingest_date)
            # 隔離する行があれば、Parquet に書いて残す
            quarantine_path = write_quarantine(bad, QUARANTINE_DIR, batch_id, TABLE)
            if quarantine_path is not None:
                print(f"{ingest_date}: 隔離 {len(bad)} 行 -> {quarantine_path}")
                quarantined += len(bad)

            # 良い行を Raw の型にして書く
            try:
                # 書き出し先は引数 --raw-dir から(省略時は RAW_DIR)
                out_path = write_events(convert_event_types(good), day, args.raw_dir, batch_id)
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
            print(f"{ingest_date}: {len(good)} 行 -> {out_path}")
    except IngestStop as stop:
        # 途中で止めたとき。停止の理由と、止まるまでに書いた量を記録して、失敗(1)で終わる
        log.write(
            "INFO",
            STAGE_RUN,
            "RUN_END",
            f"結果: 停止 ({stop}) / 書き出し {days}日 {rows}行",
        )
        return 1

    # 最後まで進んだとき。書き出した量と、隔離した行数を記録して、成功(0)で終わる
    log.write(
        "INFO",
        STAGE_RUN,
        "RUN_END",
        f"結果: 成功 / 書き出し {days}日 {rows}行 / 隔離 {quarantined}行",
    )
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
