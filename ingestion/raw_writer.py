"""検証を通った行に監査カラムを足し、Raw(取り込んだ日ごとの Parquet)に書く。どの表でも使う。"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.schema import BOOL, DECIMAL, INT, STRING, TIMESTAMP, TableSpec

# registry の型の名前 → Parquet の型(Bronze の外部テーブルの型と合わせる)
ARROW_TYPES = {
    STRING: pa.string(),
    INT: pa.int32(),  # Glue の int 列と合わせる
    TIMESTAMP: pa.timestamp("us"),
    DECIMAL: pa.decimal128(10, 2),
    BOOL: pa.bool_(),
}

# 全表の最後に付ける、監査カラム3つ
AUDIT_FIELDS = [
    ("_ingested_at", pa.timestamp("us")),
    ("_source_file", pa.string()),
    ("_batch_id", pa.string()),
]


def raw_schema(spec: TableSpec) -> pa.Schema:
    """Raw の Parquet の列と型を、registry から作る(表の列 + 監査カラム3つ)。

    型を明示するのは、行のない日(0 行)でも、ほかの日と同じ型のファイルにするため
    (pandas に任せると、0 行の列は型が決まらず null 型になる)。
    """
    fields = [(column, ARROW_TYPES[type_name]) for column, type_name in spec.columns.items()]
    return pa.schema(fields + AUDIT_FIELDS)


def raw_path(raw_dir: Path, spec: TableSpec, day: pd.Timestamp) -> Path:
    """Raw のファイルの場所。

    例: olist/order_items/ingest_date=2017-10-02/order_items_20171002.parquet
    """
    return (
        raw_dir
        / "olist"
        / spec.name
        / f"ingest_date={day:%Y-%m-%d}"
        / f"{spec.name}_{day:%Y%m%d}.parquet"
    )


def write_raw(
    records: pd.DataFrame,
    spec: TableSpec,
    ingest_date: str | pd.Timestamp,
    raw_dir: Path,
    batch_id: str,
) -> Path:
    """ある取り込み日の行に監査カラムを足し、日付ごとの Parquet に書き出す。"""
    day = pd.Timestamp(ingest_date)
    out_path = raw_path(raw_dir, spec, day)

    # Raw に書く列だけを取り出し、監査カラムを足す(_ingested_at は UTC、タイムゾーンの印なし)
    table = records[list(spec.columns)].assign(
        _ingested_at=pd.Timestamp.now(tz="UTC").tz_localize(None),
        _source_file=out_path.name,
        _batch_id=batch_id,
    )

    # 決めた型の表に変換して、Parquet で書く(preserve_index=False: 行番号の列は書かない)
    arrow_table = pa.Table.from_pandas(table, schema=raw_schema(spec), preserve_index=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table, out_path)
    # 書いたファイルの場所を返す
    return out_path
