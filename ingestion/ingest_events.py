"""届いたイベントのファイル(ソース、JSON Lines)を読み、検証し、Raw に書ける型にする。

検証の流儀: 問題ごとにログを書き、当たった行を隔離し、隔離が多すぎれば止める。
"""

from pathlib import Path

import numpy as np
import pandas as pd

from ingestion.quarantine import QUARANTINE_LIMIT, IngestStop
from ingestion.run_log import RunLog
from ingestion.schema import (
    EVENT_COLUMNS,
    EVENT_TYPE_RANKS,
    KNOWN_EVENT_TYPES,
    SOURCE_TIMESTAMP_COLUMNS,
    TIMESTAMP_FORMAT,
)

# ログに入れる、処理の段階の名前
STAGE_LOAD = "EVENTS_LOAD"  # ファイルを読む段階
STAGE_VALIDATE = "EVENTS_VALIDATE"  # 行を検証する段階

# 空だと Silver で畳めない、または型を付けられない列(配達予定日だけは空でも通す)
REQUIRED_NOT_EMPTY = [
    "order_id",
    "customer_id",
    "order_purchase_timestamp",
    "event_type",
    "event_rank",
    "event_time",
    "order_status",
    "is_synthetic",
]

# 問題の種類(code)ごとの、人が読む文。ログの message に使う
WHAT = {
    "EMPTY_REQUIRED": "必須の列が空の行があります",
    "DUPLICATE_KEY": "(order_id, event_type) が重複している行があります",
    "UNPARSABLE_TIMESTAMP": "日時として読めない値があります",
    "UNKNOWN_EVENT_TYPE": "既知の5つ以外の event_type があります",
    "INVALID_EVENT_RANK": "event_type と event_rank が食い違っています",
    "INVALID_FLAG": "is_synthetic が true / false ではありません",
}


def read_source_events(path: Path, log: RunLog, ingest_date: str) -> pd.DataFrame:
    """その日に届いたファイルを、日時を文字列のまま読む。ファイルや列に問題があれば止める。"""
    # 業務システムは毎日ファイルを届ける想定。ない日は、届いていないとみなして止める
    if not path.exists():
        log.write(
            "ERROR",
            STAGE_LOAD,
            "SOURCE_NOT_FOUND",
            f"届いたファイルがありません / {path}",
            ingest_date=ingest_date,
        )
        raise IngestStop("SOURCE_NOT_FOUND")

    # 中身が空のファイル(出来事のない日)は、列だけある空の表にする
    if path.stat().st_size == 0:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    try:
        # dtype=False: 型を推測させない。日時は文字列のまま読み、検証のあとで変換する
        raw = pd.read_json(path, lines=True, dtype=False)
    except ValueError:
        # JSON として読めない行がある(壊れたファイル)
        log.write(
            "ERROR",
            STAGE_LOAD,
            "SOURCE_NOT_FOUND",
            f"届いたファイルを読めません / {path}",
            ingest_date=ingest_date,
        )
        raise IngestStop("SOURCE_NOT_FOUND") from None

    # 決めた列のうち、ファイルにない列を集める
    missing = [column for column in EVENT_COLUMNS if column not in raw.columns]
    if missing:
        log.write(
            "ERROR",
            STAGE_LOAD,
            "MISSING_COLUMN",
            "必要な列がありません",
            column=", ".join(missing),
            count=len(missing),
            ingest_date=ingest_date,
        )
        raise IngestStop("MISSING_COLUMN")
    return raw


def validate_events(
    raw: pd.DataFrame,
    log: RunLog,
    ingest_date: str,
    quarantine_limit: float = QUARANTINE_LIMIT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """全行を検証し、(良い行, 隔離する行) を返す。隔離が多すぎれば止める。"""
    # 出来事のない日は、検証するものがない
    if raw.empty:
        return raw.copy(), raw.copy()

    # (問題の種類, 列名) ごとに、「その問題に当たる行」を True にした列をためる箱
    hits: dict[tuple[str, str], pd.Series] = {}

    # --- 必須の列が空 ---(空欄も、空白だけの文字も「空」)
    for column in REQUIRED_NOT_EMPTY:
        is_blank = raw[column].isna() | raw[column].astype(str).str.strip().eq("")
        hits[("EMPTY_REQUIRED", column)] = is_blank

    # --- (order_id, event_type) の重複 ---(keep=False: 重複した、すべての行を当てる)
    hits[("DUPLICATE_KEY", "order_id,event_type")] = raw.duplicated(
        ["order_id", "event_type"], keep=False
    )

    # --- 日時として読めない値 ---
    for column in SOURCE_TIMESTAMP_COLUMNS:
        # 書式を決めて読む。読めない値は NaT(日時の空)にする
        parsed = pd.to_datetime(raw[column], format=TIMESTAMP_FORMAT, errors="coerce")
        # 「元は値があった」のに「変換したら空になった」行だけが、読めない値
        hits[("UNPARSABLE_TIMESTAMP", column)] = raw[column].notna() & parsed.isna()

    # --- 既知の5つ以外の出来事の種類 ---
    is_known_type = raw["event_type"].isin(KNOWN_EVENT_TYPES)
    hits[("UNKNOWN_EVENT_TYPE", "event_type")] = ~is_known_type

    # --- 種類と順位の食い違い ---(順位は Silver の畳み方の要なので、種類と必ず合わせる)
    # 種類から決まる正しい順位と、届いた順位(数として読めない値は NaN)を比べる
    expected_rank = raw["event_type"].map(EVENT_TYPE_RANKS)
    received_rank = pd.to_numeric(raw["event_rank"], errors="coerce")
    # 種類が既知で、順位が空でない行だけを見る(空と未知の種類は、上で隔離する)
    hits[("INVALID_EVENT_RANK", "event_rank")] = (
        is_known_type & raw["event_rank"].notna() & (received_rank != expected_rank)
    )

    # --- 作った印が true / false でない ---
    # JSON の true / false だけを通す。文字の "false" は bool に変えると True に化けるため、隔離する
    is_bool = raw["is_synthetic"].map(lambda value: isinstance(value, (bool, np.bool_)))
    hits[("INVALID_FLAG", "is_synthetic")] = raw["is_synthetic"].notna() & ~is_bool

    # --- 当たりがあった問題ごとに、ログを1行書く ---
    for (code, column), mask in hits.items():
        if mask.any():
            # 例は、1つの列の問題だけに付ける(空の値と、2列の組は例にしない)
            if code in ("EMPTY_REQUIRED", "DUPLICATE_KEY"):
                samples = []
            else:
                samples = raw.loc[mask, column].dropna().astype(str).unique()[:3].tolist()
            log.write(
                "WARNING",
                STAGE_VALIDATE,
                code,
                WHAT[code],
                column=column,
                count=int(mask.sum()),
                samples=samples or None,
                ingest_date=ingest_date,
            )

    # --- 隔離する行を決める ---(どれか1つでも当たる行)
    any_hit = pd.concat(hits.values(), axis=1).any(axis=1)
    bad = raw[any_hit].copy()

    # --- 隔離が多すぎれば止める ---
    if len(bad) > len(raw) * quarantine_limit:
        log.write(
            "ERROR",
            STAGE_VALIDATE,
            "QUARANTINE_OVER_LIMIT",
            "隔離する行が上限を超えました",
            count=len(bad),
            ingest_date=ingest_date,
        )
        raise IngestStop("QUARANTINE_OVER_LIMIT")

    # --- 隔離の理由を、行ごとにまとめる ---(1行に複数の問題があっても、理由はすべて残す)
    codes, columns = [], []
    for index in bad.index:
        found = [key for key, mask in hits.items() if mask.loc[index]]
        codes.append(",".join(dict.fromkeys(code for code, _ in found)))
        columns.append(",".join(dict.fromkeys(column for _, column in found)))
    bad["_error_codes"] = codes
    bad["_error_columns"] = columns

    # 良い行と、隔離する行を返す
    return raw[~any_hit].copy(), bad


def convert_event_types(good: pd.DataFrame) -> pd.DataFrame:
    """検証を通った行を、Raw に書く型にする(日時は日時型、順位は int32、印は bool)。"""
    # 元の表を書き換えないよう、複製してから変換する
    good = good.copy()
    for column in SOURCE_TIMESTAMP_COLUMNS:
        good[column] = pd.to_datetime(good[column], format=TIMESTAMP_FORMAT)
    good["event_rank"] = good["event_rank"].astype("int32")
    good["is_synthetic"] = good["is_synthetic"].astype(bool)
    return good
