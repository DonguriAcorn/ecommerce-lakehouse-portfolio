"""Olist の orders(最終状態の CSV)から、注文の出来事を1行ずつ並べた表を作る。

業務システムの代わり(パイプラインではない)。届くファイルは make_source_events.py が書く。
"""

from pathlib import Path

import pandas as pd

# 元データ(CSV)にある日時の5列。文字列から日時型への変換の対象になる
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

# 段階ごとの、出来事の種類の名前(ingestion/schema.py の KNOWN_EVENT_TYPES と同じ5つ)
RANK_TO_EVENT_TYPE = {
    RANK_CREATED: "created",
    RANK_APPROVED: "approved",
    RANK_SHIPPED: "shipped",
    RANK_DELIVERED: "delivered",
    RANK_FINAL: "final",
}


def convert_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """日時の列を日時型に変換する。"""
    # 元の表を書き換えないよう、複製してから変換する
    df = df.copy()
    for column in TIMESTAMP_COLUMNS:
        df[column] = pd.to_datetime(df[column])
    return df


def load_orders(csv_path: Path) -> pd.DataFrame:
    """CSV を読み込み、日時の列を日時型に変換する(元データは読めない日時が 0 件と確認済み)。"""
    return convert_timestamps(pd.read_csv(csv_path, dtype=str))


def build_event_records(orders: pd.DataFrame) -> pd.DataFrame:
    """注文の出来事を1行ずつ並べた表にする(届くファイルの元になる)。

    1行 = 1つの注文の1つの出来事。時刻は日付に丸めず、時刻付きで持つ。
    """
    # (日時の列, 段階の順位) の組。注文が進む順に並べる
    steps = [
        ("order_purchase_timestamp", RANK_CREATED),
        ("order_approved_at", RANK_APPROVED),
        ("order_delivered_carrier_date", RANK_SHIPPED),
        ("order_delivered_customer_date", RANK_DELIVERED),
    ]
    # どの行にも入れる、注文の変わらない属性の列
    attribute_columns = [
        "order_id",
        "customer_id",
        "order_purchase_timestamp",
        "order_estimated_delivery_date",
    ]

    # 段階ごとに作った小さな表を、あとで縦につなぐための入れ物
    parts = []
    for column, rank in steps:
        # その段階の日時が入っている注文だけを選ぶ(まだ起きていない出来事は除く)
        known = orders[orders[column].notna()]
        # 属性の列をコピーし、この出来事の情報(種類、順位、時刻、状態、作った印)を足す
        part = known[attribute_columns].copy()
        part["event_type"] = RANK_TO_EVENT_TYPE[rank]
        part["event_rank"] = rank
        part["event_time"] = known[column]  # normalize しない。時刻付きのまま持つ
        part["order_status"] = RANK_TO_STATUS[rank]  # その時点で到達した状態
        part["is_synthetic"] = False  # 元データにある本物の日時
        parts.append(part)

    # 日時の列がない最終状態は、最後に分かっている日付の翌日に起きたことにする(作った時刻)
    # 注文ごとに、4つの日時のうち一番新しいものの日付(時刻は切り捨てる)
    last_known = orders[[column for column, _ in steps]].max(axis=1).dt.normalize()
    # 最終状態の出来事が必要な注文: 日時の列がない状態の注文と、
    # 「delivered なのに配達日が空」の注文
    needs_final = orders["order_status"].isin(STATUSES_WITHOUT_TIMESTAMP) | (
        (orders["order_status"] == "delivered")
        & orders["order_delivered_customer_date"].isna()
    )
    final = orders.loc[needs_final, attribute_columns].copy()
    final["event_type"] = RANK_TO_EVENT_TYPE[RANK_FINAL]
    final["event_rank"] = RANK_FINAL
    final["event_time"] = last_known[needs_final] + pd.Timedelta(days=1)
    final["order_status"] = orders.loc[needs_final, "order_status"]  # 元データの状態
    final["is_synthetic"] = True  # 時刻を作ったので、印を付ける
    parts.append(final)

    # 5つの小さな表を縦につなぐ。event_date は「出来事が起きた日」で、届いた日を決めるために持つ
    records = pd.concat(parts, ignore_index=True)
    records["event_date"] = records["event_time"].dt.normalize()
    return records
