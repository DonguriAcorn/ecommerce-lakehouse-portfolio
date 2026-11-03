# ADR 0004: Raw は日付ごとの Parquet にし、型は Raw の段階で付ける

- 日付: 2026-11-03(更新)
- 状態: 採用。Raw の1行の形(出来事を1行ずつ)は ADR 0010 で決める

## 状況

届くファイル(`data/source/`)は JSON Lines で、日時は文字列で届く。Raw にどの形式で、どこで型を付けて置くかを決める必要がある。

## 決めたこと

- **置き方:** `raw/olist/orders_events/ingest_date=YYYY-MM-DD/orders_events_YYYYMMDD.parquet`。1日1ファイルの Parquet。`ingest_date` は取り込んだ日(届いた日)。
- **型は Raw の段階で付ける:** 取り込み(`ingestion/ingest_events.py`)で、日時を `timestamp`(UTC、タイムゾーンの印なし)、順位を int32、印を boolean にしてから書く。
- **監査カラム**(`_ingested_at`、`_source_file`、`_batch_id`)を、ファイルに入れる。

## 理由

- Parquet にすると、Athena が列の型を持ったまま読める。Bronze の外部テーブルが、変換なしでそのまま読める(ADR 0003)。
- 型を Raw の段階で付けると、Bronze と Silver で同じ型になり、Athena の `timestamp`(タイムゾーンなし)とも合う。

## あきらめたこと(弱い点)

- Raw が「届いた姿そのまま」ではなくなる。実務では、Raw は届いた文字列のまま持ち、型は Silver で付けることが多い。今回は、届いたファイル(`data/source/`)が手元に残るので、必要なら Raw を作り直せる。
- 日時として読めない値があると、型を付けられない。そのため、取り込みの検証で、読めない行を先に**隔離**する設計にした(ADR 0005、docs/design/error-handling.md)。
