# Gold の設計(画面から逆算)

- 日付: 2026-11-14
- 判断の記録: ADR 0015
- 使う側: フェーズ3「Gold のスター型」「SCD2」「meta / tags」「Lv1」「tests」(同じ YAML に同時に書く)

## 1. 画面ごとに必要なデータ

| 画面 | 指標 | 切り口 | 元の Silver と列 | 使う Gold |
|---|---|---|---|---|
| 売上 KPI | GMV(`price + freight_value` の合計)、注文数、平均注文額 | 日、月、州 | order_items(`price`、`freight_value`)、orders_from_events(`order_status`、`order_purchase_timestamp`)、customers(`customer_state`) | fact_order_items(GMV)、fact_orders(注文数) |
| 期間比較 | 上の指標の前月比、前年同月比 | 月、年 | 同上 | dim_date |
| リピート率 | 2注文以上の本人の割合 | 月、州 | customers(`customer_unique_id`)、orders_from_events(`customer_id`、購入日時) | fact_orders、dim_customer |
| 商品ランキング | カテゴリ別・商品別の GMV、販売数、平均の星の数 | カテゴリ、月 | order_items、products(`product_category_name`)、translation(英名)、reviews(`review_score`) | fact_order_items、dim_product |
| パイプライン健康状態 | 日ごとの成否、行数、遅延 | 日、表 | 取り込みログ(S3 の `logs/`)、dbt の結果 | Gold の対象外(フェーズ5で別に扱う) |

為替は入れない(2026-11-14 の決定)。

## 2. 粒度

| テーブル | 1行 | 主キー |
|---|---|---|
| fact_order_items | 注文の明細1行 | `order_id` + `order_item_id` |
| fact_orders | 注文1件 | `order_id` |
| dim_customer | 本人の、属性が同じだった期間1つ | `customer_unique_id` + `valid_from`(代理キー `customer_sk`) |
| dim_product | 商品1つ | `product_id` |
| dim_date | 1日 | `date_key`(日付) |

- 売上とランキングは明細から、リピート率と注文数は注文から数える。
- 明細のない注文(キャンセルなど)も、fact_orders には残る。

## 3. 列(下書き。実装の着手時に registry と突き合わせて確定する)

**fact_order_items**: `order_id`、`order_item_id`、`product_id`、`seller_id`(キーとして持つだけ)、`customer_sk`、`purchase_date`(日付)、`order_status`、`is_counted`(canceled と unavailable 以外なら true)、`price`、`freight_value`、`item_amount`(= `price + freight_value`)

**fact_orders**: `order_id`、`customer_id`、`customer_unique_id`、`customer_sk`、`purchase_date`、`order_status`、`is_counted`、`item_count`、`order_amount`(明細の `item_amount` の合計。明細なしは 0)、`review_score`(その注文の星の数。複数あるときの扱いは実装の着手時に決める)

**dim_customer**: `customer_sk`、`customer_unique_id`、`customer_state`、`customer_zip_code_prefix`、`customer_city`(本人の最新の値)、`valid_from`、`valid_to`、`is_current`

**dim_product**: `product_id`、`category_name`(英訳 → 元の名前 → `unknown` の順。ADR 0011)

**dim_date**: `date_key`、年、月、年月、四半期、曜日

## 4. SCD2(dim_customer)

- customers は 2016-09-04 に1回しか届かないので、dbt snapshot は変化を見られない。Silver の注文と顧客から、SQL で履歴を作る。
- 作り方:
  1. orders の購入日時を customers に付ける(`customer_id` は注文ごとに1つなので、1対1)。
  2. `customer_unique_id` ごとに購入日時の順に並べる。
  3. `customer_state` と `customer_zip_code_prefix` が前の注文と変わった所で、新しい期間を始める。同じ値が続く間は1つにまとめる。
  4. 期間の `valid_from` はその期間の最初の購入日時、`valid_to` は次の期間の `valid_from`(最後は null)、`is_current` は最後の期間だけ true。
- 追う列は、州と郵便番号の先頭5桁。市の名前は履歴を持たせず、本人の最新の値を持つ。
- 実データの変化: 2注文以上の本人 2,997 人のうち、州が変わった人が 39 人、郵便番号が変わった人が 250 人。
- 注文との結びつき: `fact_orders` の `customer_sk` は、`customer_id`(注文の客)から、その注文の購入日時が入る期間の行を引く。

## 5. Gold に入れないもの

- sellers: どの画面にも出ないため、作らない(`seller_id` は明細に持つだけ。画面が増えたら足す)。
- パイプライン健康状態: 元が運用ログのため。
- 為替、payments、geolocation。

## 6. 実装の着手時に決めたこと(2026-11-14)

- 売上(GMV)から外す状態は `canceled` と `unavailable`。進行中(shipped、processing など)は含める。canceled には明細のある注文が 461 件、unavailable には 6 件ある。外す条件は、fact の列 `is_counted`(外さない状態なら true)として持ち、画面と指標はこの列で絞る。
- 1注文に複数の reviews があるとき(547 件、最大 3 件)の `review_score` は、`review_answer_timestamp` が最新の1件の星を使う。
