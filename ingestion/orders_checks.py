"""orders の出来事だけの追加の検証。共通の受付(ingestion/ingest_table.py)の validate_rows に渡す。

出来事の種類と順位は Silver の畳み方の要なので、受付の段階で必ず合わせる(ADR 0010)。
"""

import pandas as pd

from ingestion.ingest_table import Hits
from ingestion.schema import EVENT_TYPE_RANKS, KNOWN_EVENT_TYPES, ORDERS_EVENTS

# 問題の種類(code)ごとの、人が読む文。共通の文に足して、ログの message に使う
WHAT = {
    "DUPLICATE_KEY": "(order_id, event_type) が重複している行があります",
    "UNKNOWN_EVENT_TYPE": "既知の5つ以外の event_type があります",
    "INVALID_EVENT_RANK": "event_type と event_rank が食い違っています",
}


def check_orders_events(raw: pd.DataFrame) -> tuple[Hits, dict[str, str]]:
    """キーの重複、未知の種類、種類と順位の食い違いを探し、(当たり, 文) を返す。"""
    hits: Hits = {}

    # --- キー (order_id, event_type) の重複 ---(keep=False: 重複した、すべての行を当てる)
    keys = list(ORDERS_EVENTS.keys)
    hits[("DUPLICATE_KEY", ",".join(keys))] = raw.duplicated(keys, keep=False)

    # --- 既知の5つ以外の出来事の種類 ---
    is_known_type = raw["event_type"].isin(KNOWN_EVENT_TYPES)
    hits[("UNKNOWN_EVENT_TYPE", "event_type")] = ~is_known_type

    # --- 種類と順位の食い違い ---(順位は Silver の畳み方の要なので、種類と必ず合わせる)
    # 種類から決まる正しい順位と、届いた順位(数として読めない値は NaN)を比べる
    expected_rank = raw["event_type"].map(EVENT_TYPE_RANKS)
    received_rank = pd.to_numeric(raw["event_rank"], errors="coerce")
    # 種類が既知で、順位が空でない行だけを見る(空と未知の種類は、ほかの確認で隔離する)
    hits[("INVALID_EVENT_RANK", "event_rank")] = (
        is_known_type & raw["event_rank"].notna() & (received_rank != expected_rank)
    )
    return hits, WHAT
