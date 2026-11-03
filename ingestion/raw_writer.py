"""検証を通った出来事に監査カラムを足し、Raw(取り込んだ日ごとの Parquet)に書く。"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.schema import EVENT_COLUMNS

# Raw の Parquet の列と型(Bronze の bronze.tf と同じ並び)。
# 型を明示するのは、出来事のない日(0 行)でも、ほかの日と同じ型のファイルにするため
# (pandas に任せると、0 行の列は型が決まらず null 型になる)
RAW_SCHEMA = pa.schema(
    [
        ("order_id", pa.string()),
        ("customer_id", pa.string()),
        ("order_purchase_timestamp", pa.timestamp("us")),
        ("order_estimated_delivery_date", pa.timestamp("us")),
        ("event_type", pa.string()),
        ("event_rank", pa.int32()),  # Glue の int 列と合わせる
        ("event_time", pa.timestamp("us")),
        ("order_status", pa.string()),
        ("is_synthetic", pa.bool_()),
        ("_ingested_at", pa.timestamp("us")),
        ("_source_file", pa.string()),
        ("_batch_id", pa.string()),
    ]
)


def write_events(
    records: pd.DataFrame,
    ingest_date: str | pd.Timestamp,
    raw_dir: Path,
    batch_id: str,
) -> Path:
    """ある取り込み日のイベントに監査カラムを足し、日付ごとの Parquet に書き出す。"""
    day = pd.Timestamp(ingest_date)
    # ファイル名は日付入り(例: orders_events_20171004.parquet)
    file_name = f"orders_events_{day:%Y%m%d}.parquet"
    # 置き場所は、取り込んだ日ごとのフォルダ(例: raw/olist/orders_events/ingest_date=2017-10-04/)
    out_path = (
        raw_dir / "olist" / "orders_events" / f"ingest_date={day:%Y-%m-%d}" / file_name
    )

    # Raw に書く列だけを取り出し、監査カラムを足す(_ingested_at は UTC、タイムゾーンの印なし)
    table = records[EVENT_COLUMNS].assign(
        _ingested_at=pd.Timestamp.now(tz="UTC").tz_localize(None),
        _source_file=file_name,
        _batch_id=batch_id,
    )

    # 決めた型の表に変換して、Parquet で書く(preserve_index=False: 行番号の列は書かない)
    arrow_table = pa.Table.from_pandas(table, schema=RAW_SCHEMA, preserve_index=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table, out_path)
    # 書いたファイルの場所を返す
    return out_path
