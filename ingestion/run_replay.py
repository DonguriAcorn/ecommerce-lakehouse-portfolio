"""orders のスナップショットを、指定した期間の日付ごとに Raw に書き出す。"""

import argparse
from pathlib import Path

import pandas as pd

from ingestion.replay_orders import (
    build_events,
    build_snapshot,
    load_orders,
    write_snapshot,
)

ORDERS_CSV = Path("data/olist/olist_orders_dataset.csv")
RAW_DIR = Path("data/raw")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="最初の日付(YYYY-MM-DD)")
    parser.add_argument(
        "--end", required=True, help="最後の日付(YYYY-MM-DD、この日も含む)"
    )
    args = parser.parse_args()

    # 1回の実行を見分ける ID(例: 20261025T103000Z)
    batch_id = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")

    orders = load_orders(ORDERS_CSV)
    events = build_events(orders)

    for day in pd.date_range(args.start, args.end, freq="D"):
        snapshot = build_snapshot(orders, events, day)
        out_path = write_snapshot(snapshot, day, RAW_DIR, batch_id)
        print(f"{day:%Y-%m-%d}: {len(snapshot)} 行 -> {out_path}")


if __name__ == "__main__":
    main()
