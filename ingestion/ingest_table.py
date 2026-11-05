"""届いたファイル(JSON Lines)を読み、検証し、Raw に書ける型にする。どの表でも使う共通の受付。

表ごとの違い(列、型、必須の列)は、ingestion/schema.py の registry から受け取る。
検証の流儀: 問題ごとにログを書き、当たった行を隔離し、隔離が多すぎれば止める。
表だけの検証(orders の出来事の種類など)は、extra_check として外から渡す(ADR 0011)。
"""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from ingestion.quarantine import QUARANTINE_LIMIT, IngestStop
from ingestion.run_log import RunLog
from ingestion.schema import BOOL, DECIMAL, INT, TIMESTAMP, TIMESTAMP_FORMAT, TableSpec

# ログに入れる、処理の段階の名前(どの表かは、ログの table の項目で分かる)
STAGE_LOAD = "LOAD"  # ファイルを読む段階
STAGE_VALIDATE = "VALIDATE"  # 行を検証する段階

# 金額として読める書式(例: 58.90、0、-1.5)。整数 8 桁・小数 2 桁まで(decimal(10,2) に丸めずに入る)
DECIMAL_PATTERN = r"-?\d{1,8}(\.\d{1,2})?"

# 問題の種類(code)ごとの、人が読む文。ログの message に使う
WHAT = {
    "EMPTY_REQUIRED": "必須の列が空の行があります",
    "UNPARSABLE_TIMESTAMP": "日時として読めない値があります",
    "INVALID_INT": "整数として読めない値があります",
    "INVALID_DECIMAL": "金額(小数 2 桁まで)として読めない値があります",
    "INVALID_FLAG": "true / false ではない値があります",
}

# 検証の当たり: (問題の種類, 列名) → その問題に当たる行を True にした列
Hits = dict[tuple[str, str], pd.Series]
# 表だけの追加の検証: 届いた表を受け取り、(当たり, 問題の種類ごとの文) を返す関数
ExtraCheck = Callable[[pd.DataFrame], tuple[Hits, dict[str, str]]]


def source_path(source_dir: Path, spec: TableSpec, day: pd.Timestamp) -> Path:
    """その日に届くファイルの場所(例: arrival_date=2017-10-02/order_items_20171002.jsonl)。"""
    return source_dir / f"arrival_date={day:%Y-%m-%d}" / f"{spec.name}_{day:%Y%m%d}.jsonl"


def read_source(path: Path, spec: TableSpec, log: RunLog, ingest_date: str) -> pd.DataFrame:
    """その日に届いたファイルを、値を文字列のまま読む。ファイルや列に問題があれば止める。"""
    # 届くはずの日にファイルがなければ、届いていないとみなして止める
    if not path.exists():
        log.write(
            "ERROR",
            STAGE_LOAD,
            "SOURCE_NOT_FOUND",
            f"届いたファイルがありません / {path}",
            ingest_date=ingest_date,
        )
        raise IngestStop("SOURCE_NOT_FOUND")

    # 中身が空のファイル(行のない日)は、列だけある空の表にする
    if path.stat().st_size == 0:
        return pd.DataFrame(columns=list(spec.columns))

    try:
        # dtype=False: 型を推測させない(日時と金額は文字列のまま読み、検証のあとで変換する)
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
    missing = [column for column in spec.columns if column not in raw.columns]
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


def check_types(raw: pd.DataFrame, spec: TableSpec) -> Hits:
    """型ごとに、読めない値の行を探す。空の値は当てない(空は、必須の列の確認で見る)。"""
    hits: Hits = {}
    for column, type_name in spec.columns.items():
        values = raw[column]
        if type_name == TIMESTAMP:
            # 書式を決めて読む。読めない値は NaT(日時の空)にし、「元は値があった」行だけを当てる
            parsed = pd.to_datetime(values, format=TIMESTAMP_FORMAT, errors="coerce")
            hits[("UNPARSABLE_TIMESTAMP", column)] = values.notna() & parsed.isna()
        elif type_name == INT:
            # 数として読めない値と、小数(1.5 など)を当てる
            number = pd.to_numeric(values, errors="coerce")
            hits[("INVALID_INT", column)] = values.notna() & (number.isna() | (number % 1 != 0))
        elif type_name == DECIMAL:
            # 金額の書式に、全体が合わない値を当てる(例: "12,50"、"1.234"、"abc")
            matched = values.astype(str).str.fullmatch(DECIMAL_PATTERN)
            hits[("INVALID_DECIMAL", column)] = values.notna() & ~matched
        elif type_name == BOOL:
            # JSON の true / false だけを通す。文字の "false" は bool に変えると True に化けるため
            is_bool = values.map(lambda value: isinstance(value, (bool, np.bool_)))
            hits[("INVALID_FLAG", column)] = values.notna() & ~is_bool
    return hits


def validate_rows(
    raw: pd.DataFrame,
    spec: TableSpec,
    log: RunLog,
    ingest_date: str,
    extra_check: ExtraCheck | None = None,
    quarantine_limit: float = QUARANTINE_LIMIT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """全行を検証し、(良い行, 隔離する行) を返す。隔離が多すぎれば止める。"""
    # 行のない日は、検証するものがない
    if raw.empty:
        return raw.copy(), raw.copy()

    # (問題の種類, 列名) ごとの当たりをためる箱と、問題の種類ごとの文
    hits: Hits = {}
    what = dict(WHAT)

    # --- 必須の列が空 ---(空欄も、空白だけの文字も「空」)
    for column in spec.required:
        is_blank = raw[column].isna() | raw[column].astype(str).str.strip().eq("")
        hits[("EMPTY_REQUIRED", column)] = is_blank

    # --- 型として読めない値 ---
    hits.update(check_types(raw, spec))

    # --- 表だけの追加の検証 ---(渡されたときだけ)
    if extra_check is not None:
        extra_hits, extra_what = extra_check(raw)
        hits.update(extra_hits)
        what.update(extra_what)

    # --- 当たりがあった問題ごとに、ログを1行書く ---
    for (code, column), mask in hits.items():
        if mask.any():
            # 例は、1つの列の問題だけに付ける(空の値と、複数の列の組は例にしない)
            if code == "EMPTY_REQUIRED" or "," in column:
                samples = []
            else:
                samples = raw.loc[mask, column].dropna().astype(str).unique()[:3].tolist()
            log.write(
                "WARNING",
                STAGE_VALIDATE,
                code,
                what[code],
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


def convert_types(good: pd.DataFrame, spec: TableSpec) -> pd.DataFrame:
    """検証を通った行を、registry の型にする(Raw に書く直前の形)。"""
    # 元の表を書き換えないよう、複製してから変換する
    good = good.copy()
    for column, type_name in spec.columns.items():
        if type_name == TIMESTAMP:
            good[column] = pd.to_datetime(good[column], format=TIMESTAMP_FORMAT)
        elif type_name == INT:
            # Int32: 空(null)も持てる 32 ビットの整数
            good[column] = pd.to_numeric(good[column]).astype("Int32")
        elif type_name == DECIMAL:
            # 文字列から直接 Decimal にする(float を通さないので、58.90 が 58.8999… にならない)
            good[column] = good[column].map(
                lambda value: None if pd.isna(value) else Decimal(str(value))
            )
        elif type_name == BOOL:
            # boolean: 空(null)も持てる true / false
            good[column] = good[column].astype("boolean")
        else:
            # 文字列の列は、空の日(列の型が決まらない)でも文字列として扱う
            good[column] = good[column].astype("string")
    return good
