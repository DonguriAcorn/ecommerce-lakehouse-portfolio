"""orders 以外の表の CSV から、届くファイルの元になる表を作る(業務システムの代わり)。

orders と違い、出来事に分ける必要はない。行ごとに「届く日(arrival_date)」を付けるだけ(ADR 0011)。
届く日の規則: order_items は親の注文の購入日、reviews は max(客が答えた日, 親の購入日)、
一括型(customers など)は最初の日に全件。
"""

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from ingestion.schema import FIRST_DAY, ORDERS_EVENTS, SNAPSHOT, TableSpec


def read_csv_as_text(csv_path: Path) -> pd.DataFrame:
    """CSV を、すべての値を文字列のまま読む。

    keep_default_na=False と na_values=[""]: 空欄だけを空にする("NA" のような文字は値として残す)。
    encoding="utf-8-sig": 先頭の BOM(英訳の CSV にある見えない印)を外す。
    """
    return pd.read_csv(
        csv_path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig"
    )


def purchase_dates(olist_dir: Path) -> pd.Series:
    """注文 ID → 購入日(時刻を切り捨てた日付)の対応を返す。子の表の届く日に使う。"""
    orders = read_csv_as_text(olist_dir / ORDERS_EVENTS.source_csv)
    purchased = pd.to_datetime(orders["order_purchase_timestamp"]).dt.normalize()
    return pd.Series(purchased.values, index=orders["order_id"])


def items_arrival(rows: pd.DataFrame, purchase: pd.Series) -> pd.Series:
    """order_items: 親の注文の購入日に届く(明細は注文と同時にできる)。"""
    return rows["order_id"].map(purchase)


def reviews_arrival(rows: pd.DataFrame, purchase: pd.Series) -> pd.Series:
    """reviews: 客が答えた日に届く。ただし、親の注文の購入日より前にはしない。"""
    answered = pd.to_datetime(rows["review_answer_timestamp"]).dt.normalize()
    return pd.concat([answered, rows["order_id"].map(purchase)], axis=1).max(axis=1)


# 追記型の表ごとの、届く日の規則。(CSV の行, 購入日の対応) → 行ごとの届く日
ARRIVAL_RULES: dict[str, Callable[[pd.DataFrame, pd.Series], pd.Series]] = {
    "order_items": items_arrival,
    "reviews": reviews_arrival,
}


def build_table_records(spec: TableSpec, olist_dir: Path) -> pd.DataFrame:
    """CSV を読み、registry の列だけを残して、行ごとの届く日(arrival_date)を付ける。"""
    rows = read_csv_as_text(olist_dir / spec.source_csv)
    if spec.kind == SNAPSHOT:
        # 一括型: 全件が最初の日に届く
        arrival = pd.Series(FIRST_DAY, index=rows.index)
    else:
        # 追記型: 表ごとの規則で決める
        arrival = ARRIVAL_RULES[spec.name](rows, purchase_dates(olist_dir))

    # 親の注文が見つからず、届く日が決まらない行があれば止める(測定では 0 件)
    if arrival.isna().any():
        missing = int(arrival.isna().sum())
        raise ValueError(f"{spec.name}: 届く日が決まらない行が {missing} 件あります")
    return rows[list(spec.columns)].assign(arrival_date=arrival)
