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
