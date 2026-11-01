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

ORDERS_CSV = Path("data/olist/olist_orders_dataset.csv")
RAW_DIR = Path("data/raw")
LOG_DIR = Path("data/logs")
QUARANTINE_DIR = Path("data/quarantine")
TABLE = "orders"
STAGE_RUN = "ORDERS_RUN"
STAGE_WRITE = "ORDERS_WRITE"


def main() -> int:
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

    days, rows = 0, 0
    try:
        raw = read_orders_csv(ORDERS_CSV, log)
        good, bad = validate_orders(raw, log)
        quarantine_path = write_quarantine(bad, QUARANTINE_DIR, batch_id)
        if quarantine_path is not None:
            print(f"隔離: {len(bad)} 行 -> {quarantine_path}")

        orders = convert_timestamps(good)
        events = build_events(orders)

        for day in pd.date_range(args.start, args.end, freq="D"):
            snapshot = build_snapshot(orders, events, day)
            try:
                out_path = write_snapshot(snapshot, day, RAW_DIR, batch_id)
            except OSError:
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
        log.write(
            "INFO",
            STAGE_RUN,
            "RUN_END",
            f"結果: 停止 ({stop}) / 書き出し {days}日 {rows}行",
        )
        return 1

    log.write(
        "INFO",
        STAGE_RUN,
        "RUN_END",
        f"結果: 成功 / 読んだ {len(raw)}行 / 隔離 {len(bad)}行"
        f" / 書き出し {days}日 {rows}行",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
