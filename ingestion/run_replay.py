"""orders のスナップショットを、指定した期間の日付ごとに Raw に書き出す。"""

import argparse
from pathlib import Path

import pandas as pd

from ingestion.replay_orders import (
    build_events,
    build_snapshot,
    convert_timestamps,
    write_snapshot,
)
from ingestion.run_log import RunLog
from ingestion.validate_orders import (
    IngestStop,
    read_orders_csv,
    validate_orders,
    write_quarantine,
)

# 入力(元の CSV)と、出力(Raw、ログ、隔離)の置き場所。すべて Git の管理外
ORDERS_CSV = Path("data/olist/olist_orders_dataset.csv")
RAW_DIR = Path("data/raw")
LOG_DIR = Path("data/logs")
QUARANTINE_DIR = Path("data/quarantine")
# ログに入れる、テーブル名と処理の段階の名前
TABLE = "orders"
STAGE_RUN = "ORDERS_RUN"  # 実行全体の開始と終了
STAGE_WRITE = "ORDERS_WRITE"  # Raw への書き出し


def main() -> int:
    """実行の流れ: 引数 → 読む → 検証 → 隔離 → 日付ごとに書く。成功は 0、停止は 1 を返す。"""
    # コマンドの引数(--start、--end)を読み取る準備
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="最初の日付(YYYY-MM-DD)")
    parser.add_argument(
        "--end", required=True, help="最後の日付(YYYY-MM-DD、この日も含む)"
    )
    args = parser.parse_args()

    # 1回の実行を見分ける ID(例: 20261025T103000Z)
    batch_id = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    log = RunLog(LOG_DIR, TABLE, batch_id)
    log.write(
        "INFO",
        STAGE_RUN,
        "RUN_START",
        f"取り込みを始めます / {args.start} 〜 {args.end}",
    )

    # 終了時のまとめに使う、書き出した日数と行数
    days, rows = 0, 0
    try:
        # CSV を読む(ファイルがない、列が足りないときは、ここで止まる)
        raw = read_orders_csv(ORDERS_CSV, log)
        # 全行を検証し、良い行と隔離する行に分ける(隔離が多すぎれば、ここで止まる)
        good, bad = validate_orders(raw, log)
        # 隔離する行があれば、Parquet に書いて残す
        quarantine_path = write_quarantine(bad, QUARANTINE_DIR, batch_id)
        if quarantine_path is not None:
            print(f"隔離: {len(bad)} 行 -> {quarantine_path}")

        # 検証を通った行だけ、日時型に変換し、出来事の表を作る
        orders = convert_timestamps(good)
        events = build_events(orders)

        # 指定した期間を1日ずつ進め、その日のスナップショットを Raw に書く
        for day in pd.date_range(args.start, args.end, freq="D"):
            snapshot = build_snapshot(orders, events, day)
            try:
                out_path = write_snapshot(snapshot, day, RAW_DIR, batch_id)
            except OSError:
                # ディスクがいっぱい、書き込み権限がない、など。理由をログに書いてから止める
                log.write(
                    "ERROR",
                    STAGE_WRITE,
                    "WRITE_FAILED",
                    "Raw の書き出しに失敗しました",
                    ingest_date=f"{day:%Y-%m-%d}",
                )
                raise IngestStop("WRITE_FAILED") from None
            days += 1
            rows += len(snapshot)
            print(f"{day:%Y-%m-%d}: {len(snapshot)} 行 -> {out_path}")
    except IngestStop as stop:
        # 途中で止めたとき。停止の理由と、止まるまでに書いた量を記録して、失敗(1)で終わる
        log.write(
            "INFO",
            STAGE_RUN,
            "RUN_END",
            f"結果: 停止 ({stop}) / 書き出し {days}日 {rows}行",
        )
        return 1

    # 最後まで進んだとき。読んだ行数、隔離した行数、書き出した量を記録して、成功(0)で終わる
    log.write(
        "INFO",
        STAGE_RUN,
        "RUN_END",
        f"結果: 成功 / 読んだ {len(raw)}行 / 隔離 {len(bad)}行"
        f" / 書き出し {days}日 {rows}行",
    )
    return 0


# このファイルをコマンドとして実行したときだけ、main を動かす(import したときは動かさない)
if __name__ == "__main__":
    raise SystemExit(main())
