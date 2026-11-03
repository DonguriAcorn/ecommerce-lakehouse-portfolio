"""届くイベントのファイル(orders_events)の形を決める。取り込み側と送る側(simulator)の約束ごと。

パイプライン(ingestion/)はこの形を前提に読み、simulator/ はこの形に合わせてファイルを作る。
"""

# 届くファイル(JSON Lines)と Raw(Parquet)の列。この順に並べる
EVENT_COLUMNS = [
    "order_id",
    "customer_id",
    "order_purchase_timestamp",
    "order_estimated_delivery_date",
    "event_type",
    "event_rank",
    "event_time",
    "order_status",
    "is_synthetic",
]

# 届くファイルで、文字列として入っている日時の列と、その書式
SOURCE_TIMESTAMP_COLUMNS = [
    "order_purchase_timestamp",
    "order_estimated_delivery_date",
    "event_time",
]
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# 既知の出来事の種類と、その段階の順位(大きいほど後の段階)。種類と順位が食い違う行は隔離する
EVENT_TYPE_RANKS = {"created": 0, "approved": 1, "shipped": 2, "delivered": 3, "final": 4}
# 既知の出来事の種類。これ以外は隔離する
KNOWN_EVENT_TYPES = list(EVENT_TYPE_RANKS)
