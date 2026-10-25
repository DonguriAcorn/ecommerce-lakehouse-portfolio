"""Olist の orders を、日付ごとのスナップショットとして再生するための処理。"""

from pathlib import Path

import pandas as pd

TIMESTAMP_COLUMNS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]

# 出来事を、起きる順に並べたときの順位(大きいほど後の段階)
RANK_CREATED = 0
RANK_APPROVED = 1
RANK_SHIPPED = 2
RANK_DELIVERED = 3
RANK_FINAL = 4

# その状態になった日時の列が、元データにない状態
STATUSES_WITHOUT_TIMESTAMP = ["invoiced", "processing", "unavailable", "canceled"]

# 段階ごとの状態の名前(RANK_FINAL は、元データの order_status を使う)
RANK_TO_STATUS = {
    RANK_CREATED: "created",
    RANK_APPROVED: "approved",
    RANK_SHIPPED: "shipped",
    RANK_DELIVERED: "delivered",
}

# 出来事が起きるまで空にしておく日時の列
EVENT_TIMESTAMP_COLUMNS = [
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
]


def load_orders(csv_path: Path) -> pd.DataFrame:
    """CSV を読み込み、日時の列を日時型に変換する。"""
    df = pd.read_csv(csv_path, dtype=str)
    for column in TIMESTAMP_COLUMNS:
        df[column] = pd.to_datetime(df[column])
    return df


def build_events(orders: pd.DataFrame) -> pd.DataFrame:
    """注文ごとの出来事(日付と段階)を、縦に並べた表にする。"""
    steps = [
        ("order_purchase_timestamp", RANK_CREATED),
        ("order_approved_at", RANK_APPROVED),
        ("order_delivered_carrier_date", RANK_SHIPPED),
        ("order_delivered_customer_date", RANK_DELIVERED),
    ]

    parts = []
    for column, rank in steps:
        known = orders[orders[column].notna()]
        parts.append(
            pd.DataFrame(
                {
                    "order_id": known["order_id"],
                    "event_date": known[column].dt.normalize(),
                    "rank": rank,
                }
            )
        )

    # 日時の列がない最終状態は、最後に分かっている日付の翌日に起きたことにする
    last_known = orders[[column for column, _ in steps]].max(axis=1).dt.normalize()
    needs_final = orders["order_status"].isin(STATUSES_WITHOUT_TIMESTAMP) | (
        (orders["order_status"] == "delivered")
        & orders["order_delivered_customer_date"].isna()
    )
    parts.append(
        pd.DataFrame(
            {
                "order_id": orders.loc[needs_final, "order_id"],
                "event_date": last_known[needs_final] + pd.Timedelta(days=1),
                "rank": RANK_FINAL,
            }
        )
    )

    return pd.concat(parts, ignore_index=True)


def build_snapshot(
    orders: pd.DataFrame, events: pd.DataFrame, snapshot_date: str | pd.Timestamp
) -> pd.DataFrame:
    """日付 D に出来事があった注文を、D 時点で分かっている情報だけで返す。"""
    day = pd.Timestamp(snapshot_date)

    # D に出来事があった注文と、その注文の D までの出来事
    changed_ids = events.loc[events["event_date"] == day, "order_id"].unique()
    past = events[(events["event_date"] <= day) & events["order_id"].isin(changed_ids)]
    latest_rank = past.groupby("order_id")["rank"].max()

    snapshot = orders[orders["order_id"].isin(changed_ids)].copy()
    rank = snapshot["order_id"].map(latest_rank)
    status = rank.map(RANK_TO_STATUS)
    snapshot["order_status"] = status.where(
        rank != RANK_FINAL, snapshot["order_status"]
    )

    # D より後に起きる出来事の日時は、まだ分からないので空にする
    for column in EVENT_TIMESTAMP_COLUMNS:
        is_known = snapshot[column].dt.normalize() <= day
        snapshot[column] = snapshot[column].where(is_known)

    return snapshot.reset_index(drop=True)


def write_snapshot(
    snapshot: pd.DataFrame,
    snapshot_date: str | pd.Timestamp,
    raw_dir: Path,
    batch_id: str,
) -> Path:
    """スナップショットに監査カラムを足し、日付ごとの Parquet に書き出す。"""
    day = pd.Timestamp(snapshot_date)
    file_name = f"orders_{day:%Y%m%d}.parquet"
    out_path = raw_dir / "olist" / "orders" / f"ingest_date={day:%Y-%m-%d}" / file_name

    # 監査カラム。_ingested_at は UTC の日時で、タイムゾーンの印は付けない
    table = snapshot.assign(
        _ingested_at=pd.Timestamp.now(tz="UTC").tz_localize(None),
        _source_file=file_name,
        _batch_id=batch_id,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)
    return out_path
