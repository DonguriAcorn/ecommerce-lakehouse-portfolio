"""Olist の orders を、日付ごとのスナップショットとして再生するための処理。"""

from pathlib import Path

import pandas as pd

# 元データ(CSV)にある日時の5列。文字列から日時型への変換と、検証の対象になる
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


def convert_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """日時の列を日時型に変換する(検証を通った表に使う)。"""
    # 元の表を書き換えないよう、複製してから変換する
    df = df.copy()
    for column in TIMESTAMP_COLUMNS:
        df[column] = pd.to_datetime(df[column])
    return df


def load_orders(csv_path: Path) -> pd.DataFrame:
    """CSV を読み込み、日時の列を日時型に変換する(検証なし。確認用)。"""
    return convert_timestamps(pd.read_csv(csv_path, dtype=str))


def build_events(orders: pd.DataFrame) -> pd.DataFrame:
    """注文ごとの出来事(日付と段階)を、縦に並べた表にする。"""
    # (日時の列, その列が表す段階の順位) の組。注文が進む順に並べる
    steps = [
        ("order_purchase_timestamp", RANK_CREATED),
        ("order_approved_at", RANK_APPROVED),
        ("order_delivered_carrier_date", RANK_SHIPPED),
        ("order_delivered_customer_date", RANK_DELIVERED),
    ]

    # 段階ごとに作った小さな表を、あとで縦につなぐための入れ物
    parts = []
    for column, rank in steps:
        # その段階の日時が入っている注文だけを選ぶ(まだ起きていない出来事は除く)
        known = orders[orders[column].notna()]
        # 「どの注文が、いつ、どの段階になったか」を1行ずつ並べた表にする
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
    # 注文ごとに、4つの日時のうち一番新しいものの日付(時刻は切り捨てる)
    last_known = orders[[column for column, _ in steps]].max(axis=1).dt.normalize()
    # 最終状態の出来事が必要な注文: 日時の列がない状態の注文と、
    # 「delivered なのに配達日が空」の注文
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

    # 5つの小さな表(4段階 + 最終状態)を縦につなぎ、行番号を振り直して返す
    return pd.concat(parts, ignore_index=True)


def build_snapshot(
    orders: pd.DataFrame, events: pd.DataFrame, snapshot_date: str | pd.Timestamp
) -> pd.DataFrame:
    """日付 D に出来事があった注文を、D 時点で分かっている情報だけで返す。"""
    # 文字列で渡されても使えるよう、日時型にそろえる(この日付を、以降 D と呼ぶ)
    day = pd.Timestamp(snapshot_date)

    # D に出来事があった注文と、その注文の D までの出来事
    changed_ids = events.loc[events["event_date"] == day, "order_id"].unique()
    past = events[(events["event_date"] <= day) & events["order_id"].isin(changed_ids)]
    # 注文ごとに、D までで一番進んだ段階の順位を求める
    latest_rank = past.groupby("order_id")["rank"].max()

    # 注文の全情報から、D に変化があった注文だけを選ぶ(元の表は書き換えない)
    snapshot = orders[orders["order_id"].isin(changed_ids)].copy()
    # 各注文の「D 時点の順位」を、順位から状態の名前に直す
    rank = snapshot["order_id"].map(latest_rank)
    status = rank.map(RANK_TO_STATUS)
    # D 時点の状態を入れる。最終状態(RANK_FINAL)だけは、元データの order_status を使う
    snapshot["order_status"] = status.where(
        rank != RANK_FINAL, snapshot["order_status"]
    )

    # D より後に起きる出来事の日時は、まだ分からないので空にする
    for column in EVENT_TIMESTAMP_COLUMNS:
        # D の日付以前なら「もう分かっている」。空(NaT)は比較が False になり、空のまま
        is_known = snapshot[column].dt.normalize() <= day
        # where: 条件が True の値は残し、False の値は空にする
        snapshot[column] = snapshot[column].where(is_known)

    # 行番号を 0 から振り直して返す
    return snapshot.reset_index(drop=True)


def write_snapshot(
    snapshot: pd.DataFrame,
    snapshot_date: str | pd.Timestamp,
    raw_dir: Path,
    batch_id: str,
) -> Path:
    """スナップショットに監査カラムを足し、日付ごとの Parquet に書き出す。"""
    day = pd.Timestamp(snapshot_date)
    # ファイル名は日付入り(例: orders_20170930.parquet)
    file_name = f"orders_{day:%Y%m%d}.parquet"
    # 置き場所は、日付ごとのフォルダ(例: raw/olist/orders/ingest_date=2017-09-30/)
    out_path = raw_dir / "olist" / "orders" / f"ingest_date={day:%Y-%m-%d}" / file_name

    # 監査カラム。_ingested_at は UTC の日時で、タイムゾーンの印は付けない
    table = snapshot.assign(
        _ingested_at=pd.Timestamp.now(tz="UTC").tz_localize(None),
        _source_file=file_name,
        _batch_id=batch_id,
    )

    # フォルダがなければ作る(あっても、エラーにしない)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Parquet で書く。index=False: 行番号の列は書かない
    table.to_parquet(out_path, index=False)
    # 書いたファイルの場所を返す(呼び出し側が画面に出す)
    return out_path
