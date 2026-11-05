"""届くファイルと Raw の形を、表ごとに決める(registry)。取り込み側と送る側(simulator)の約束ごと。

パイプライン(ingestion/)はこの形を前提に読み、simulator/ はこの形に合わせてファイルを作る。
表ごとに違う所(列と型、必須の列、キー、種類、期間)だけをここに書き、
受付の流れは共通にする(ADR 0011)。
"""

from dataclasses import dataclass

import pandas as pd

# 届くファイルで、文字列として入っている日時の書式(全表で共通)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# リプレイの期間。最初の日に一括型の表が届き、最後の日まで毎日ファイルが届く(ADR 0010)
FIRST_DAY = pd.Timestamp("2016-09-04")
LAST_DAY = pd.Timestamp("2018-10-18")

# 列の型の名前。Raw の Parquet での型は、ingestion/raw_writer.py がこの名前から決める
STRING = "string"
INT = "int"  # 32 ビットの整数(Glue の int 列と合わせる)
TIMESTAMP = "timestamp"  # 日時(届くファイルでは TIMESTAMP_FORMAT の文字列)
DECIMAL = "decimal"  # 金額。decimal(10,2)(届くファイルでは "58.90" のような文字列)
BOOL = "bool"  # true / false

# 表の種類
EVENTS = "events"  # 出来事型: 状態の変化が、起きた日に届く(orders)
APPEND = "append"  # 追記型: その日の分が毎日足される。行のない日も空のファイルが届く
SNAPSHOT = "snapshot"  # 一括型: 全件が最初の日に1回だけ届く(マスタ)


@dataclass(frozen=True)
class TableSpec:
    """1つの表の取扱説明書。frozen=True: 作ったあとに書き換えられないようにする。"""

    name: str  # 表の名前。フォルダ名、ファイル名、ログに使う(例: order_items)
    kind: str  # 種類: EVENTS、APPEND、SNAPSHOT
    source_csv: str  # 元の CSV のファイル名(data/olist/ の中)
    columns: dict[str, str]  # 列名 → 型の名前。届くファイルと Raw の列は、この順に並べる
    required: tuple[str, ...]  # 空だと隔離する列
    keys: tuple[str, ...]  # 1行を見分ける列(Silver で使う。共通の受付では重複を隔離しない)
    pii: tuple[str, ...] = ()  # 個人情報の候補の列(印だけ。隠す処理はフェーズ3)
    last_day: pd.Timestamp = LAST_DAY  # 期間の最後の日(reviews だけ後ろに延びる)

    def columns_of(self, type_name: str) -> list[str]:
        """指定した型の列を、並び順のまま返す(例: 日時の列だけ)。"""
        return [column for column, kind in self.columns.items() if kind == type_name]


def expected(spec: TableSpec, day: str | pd.Timestamp) -> bool:
    """その日に、その表のファイルが届くはずかを返す。

    出来事型と追記型は、最初の日から最後の日まで毎日。一括型は、最初の日だけ。
    """
    day = pd.Timestamp(day)
    if spec.kind == SNAPSHOT:
        return day == FIRST_DAY
    return FIRST_DAY <= day <= spec.last_day


def expected_days(spec: TableSpec) -> pd.DatetimeIndex:
    """その表のファイルが届くはずの日を、すべて返す(simulator が書く日の一覧)。"""
    if spec.kind == SNAPSHOT:
        return pd.DatetimeIndex([FIRST_DAY])
    return pd.date_range(FIRST_DAY, spec.last_day, freq="D")


# --- orders(出来事型。ADR 0010)---
ORDERS_EVENTS = TableSpec(
    name="orders_events",
    kind=EVENTS,
    source_csv="olist_orders_dataset.csv",
    columns={
        "order_id": STRING,
        "customer_id": STRING,
        "order_purchase_timestamp": TIMESTAMP,
        "order_estimated_delivery_date": TIMESTAMP,
        "event_type": STRING,
        "event_rank": INT,
        "event_time": TIMESTAMP,
        "order_status": STRING,
        "is_synthetic": BOOL,
    },
    # 空だと Silver で畳めない、または型を付けられない列(配達予定日だけは空でも通す)
    required=(
        "order_id",
        "customer_id",
        "order_purchase_timestamp",
        "event_type",
        "event_rank",
        "event_time",
        "order_status",
        "is_synthetic",
    ),
    keys=("order_id", "event_type"),
)

# --- order_items(追記型。親の注文の購入日に届く)---
ORDER_ITEMS = TableSpec(
    name="order_items",
    kind=APPEND,
    source_csv="olist_order_items_dataset.csv",
    columns={
        "order_id": STRING,
        "order_item_id": INT,  # 注文の中の明細の番号(1, 2, ...)
        "product_id": STRING,
        "seller_id": STRING,
        "shipping_limit_date": TIMESTAMP,  # 出品者が発送すべき期限
        "price": DECIMAL,
        "freight_value": DECIMAL,
    },
    required=(
        "order_id",
        "order_item_id",
        "product_id",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
    ),
    keys=("order_id", "order_item_id"),
)

# --- reviews(追記型。客が答えた日に届く。答えは最後の注文の後も続くので、期間が延びる)---
REVIEWS = TableSpec(
    name="reviews",
    kind=APPEND,
    source_csv="olist_order_reviews_dataset.csv",
    columns={
        "review_id": STRING,
        "order_id": STRING,
        "review_score": INT,  # 星の数(1〜5)
        "review_comment_title": STRING,
        "review_comment_message": STRING,  # 本文。改行・引用符・絵文字を含む
        "review_creation_date": TIMESTAMP,  # アンケートを送った日
        "review_answer_timestamp": TIMESTAMP,  # 客が答えた日時
    },
    required=(
        "review_id",
        "order_id",
        "review_score",
        "review_creation_date",
        "review_answer_timestamp",
    ),
    # review_id だけでは重複がある(814 件)ので、order_id と組にする。重複は Silver で畳む
    keys=("review_id", "order_id"),
    pii=("review_comment_title", "review_comment_message"),
    last_day=pd.Timestamp("2018-10-29"),
)

# --- customers(一括型)---
CUSTOMERS = TableSpec(
    name="customers",
    kind=SNAPSHOT,
    source_csv="olist_customers_dataset.csv",
    columns={
        "customer_id": STRING,  # 注文ごとの顧客 ID
        "customer_unique_id": STRING,  # 本人の ID(リピートの判定に使う)
        "customer_zip_code_prefix": STRING,  # 郵便番号の先頭5桁。先頭の 0 を保つため文字列
        "customer_city": STRING,
        "customer_state": STRING,
    },
    required=("customer_id", "customer_unique_id"),
    keys=("customer_id",),
    pii=("customer_zip_code_prefix", "customer_city"),
)

# --- sellers(一括型)---
SELLERS = TableSpec(
    name="sellers",
    kind=SNAPSHOT,
    source_csv="olist_sellers_dataset.csv",
    columns={
        "seller_id": STRING,
        "seller_zip_code_prefix": STRING,  # 先頭の 0 を保つため文字列
        "seller_city": STRING,
        "seller_state": STRING,
    },
    required=("seller_id",),
    keys=("seller_id",),
)

# --- products(一括型。列名の綴りの誤り _lenght は、元のまま使う)---
PRODUCTS = TableSpec(
    name="products",
    kind=SNAPSHOT,
    source_csv="olist_products_dataset.csv",
    columns={
        "product_id": STRING,
        "product_category_name": STRING,  # 空の商品が 610 件ある
        "product_name_lenght": INT,
        "product_description_lenght": INT,
        "product_photos_qty": INT,
        "product_weight_g": INT,
        "product_length_cm": INT,
        "product_height_cm": INT,
        "product_width_cm": INT,
    },
    required=("product_id",),
    keys=("product_id",),
)

# --- カテゴリの英訳(一括型)---
CATEGORY_TRANSLATION = TableSpec(
    name="product_category_name_translation",
    kind=SNAPSHOT,
    source_csv="product_category_name_translation.csv",
    columns={
        "product_category_name": STRING,
        "product_category_name_english": STRING,
    },
    required=("product_category_name", "product_category_name_english"),
    keys=("product_category_name",),
)

# 表の名前 → 取扱説明書。表を足すときは、上に TableSpec を書いて、この一覧に足す
REGISTRY = {
    spec.name: spec
    for spec in [
        ORDERS_EVENTS,
        ORDER_ITEMS,
        REVIEWS,
        CUSTOMERS,
        SELLERS,
        PRODUCTS,
        CATEGORY_TRANSLATION,
    ]
}

# --- orders だけの約束(simulator と、orders だけの追加の検証が使う)---
# 届くファイルと Raw の列(registry から作る。前と同じ並び)
EVENT_COLUMNS = list(ORDERS_EVENTS.columns)
# 届くファイルで、文字列として入っている日時の列
SOURCE_TIMESTAMP_COLUMNS = ORDERS_EVENTS.columns_of(TIMESTAMP)

# 既知の出来事の種類と、その段階の順位(大きいほど後の段階)。種類と順位が食い違う行は隔離する
EVENT_TYPE_RANKS = {"created": 0, "approved": 1, "shipped": 2, "delivered": 3, "final": 4}
# 既知の出来事の種類。これ以外は隔離する
KNOWN_EVENT_TYPES = list(EVENT_TYPE_RANKS)
