# orders のデータ確認結果と、出来事の作り方

- 更新日: 2026-11-03
- 対象: `olist_orders_dataset.csv`(元データ)と、そこから作る出来事(`simulator/orders_events.py`)

## 元データの確認結果

- 件数: 99,441 件(ヘッダーを除く)
- 購入日時の期間: 2016-09-04 〜 2018-10-17
- 状態ごとの日付の入り方:

| 状態 | 件数 | 承認日時あり | 引き渡し日時あり | 配達日時あり |
|---|---|---|---|---|
| created | 5 | 0 | 0 | 0 |
| approved | 2 | 2 | 0 | 0 |
| invoiced | 314 | 314 | 0 | 0 |
| processing | 301 | 301 | 0 | 0 |
| shipped | 1,107 | 1,107 | 1,107 | 0 |
| delivered | 96,478 | 96,464 | 96,476 | 96,470 |
| canceled | 625 | 484 | 75 | 6 |
| unavailable | 609 | 609 | 0 | 0 |

### 気づいたこと

- CSV の引用符が、行や列によって、付いたり付かなかったりする。CSV として問題はないが、自前の文字列処理で分割せず、CSV を解釈するライブラリで読む。
- invoiced、processing、unavailable、canceled には、その状態になった日時の列がない。
- delivered なのに、配達日時が空の注文が 8 件、承認日時が空の注文が 14 件、引き渡し日時が空の注文が 2 件ある。
- canceled のうち、6 件は配達日時を持つ(配達後にキャンセルされた)。
- order_id の空と重複、購入日時の空、日時として読めない値は、どれも 0 件。order_status は上の8つだけ。
- 時刻の逆転と同時刻(2026-11-03 確認): 引き渡し日時が承認日時より前の注文が 1,359 件、配達日時が引き渡し日時より前の注文が 23 件、承認日時が購入日時と同じ秒の注文が 1,296 件ある。そのため、現在の状態は時刻ではなく段階の順位で決める(下の「出来事の作り方」)。

## 出来事の作り方(simulator)

元データは最終状態の1回分なので、業務システムの代わり(`simulator/`)が、注文ごとの出来事を1行ずつ作る。

| 出来事(event_type) | 順位(event_rank) | 時刻(event_time)の元 | その時点の状態(order_status) | 作った印(is_synthetic) |
|---|---|---|---|---|
| created | 0 | order_purchase_timestamp | created | false |
| approved | 1 | order_approved_at(空なら作らない) | approved | false |
| shipped | 2 | order_delivered_carrier_date(空なら作らない) | shipped | false |
| delivered | 3 | order_delivered_customer_date(空なら作らない) | delivered | false |
| final | 4 | 最後に分かっている日付の翌日 0 時(作った時刻) | 元データの order_status | true |

- final は、日時の列がない状態(invoiced、processing、unavailable、canceled)の注文と、delivered なのに配達日時が空の注文にだけ作る。
- 時刻は日付に丸めず、時刻付きで持つ。
- `customer_id`、購入日時、配達予定日は、注文の変わらない属性として、どの行にも入れる。
- 注文の現在の状態は、順位が最大の出来事で決める(時刻が逆転していても、順位を優先する)。

### 件数(2026-11-03 確認)

| event_type | 件数 |
|---|---|
| created | 99,441 |
| approved | 99,281 |
| shipped | 97,658 |
| delivered | 96,476 |
| final | 1,857(日時の列がない状態が 1,849 件、配達日時が空の delivered が 8 件) |
| 合計 | 394,713 |

- (order_id, event_type) の重複は 0 件。is_synthetic が true の行は、final の 1,857 件と同じ。

### 例

| order_id | 元の order_status | 出来事(event_type, event_time, order_status) |
|---|---|---|
| e481f51cbdc54678b7cc49136f2d6af7 | delivered | (created, 2017-10-02 10:56:33, created)、(approved, 2017-10-02 11:07:15, approved)、(shipped, 2017-10-04 19:55:00, shipped)、(delivered, 2017-10-10 21:25:13, delivered) |
| 136cce7faa42fdb2cefd53fdc79a6098 | invoiced | (created, 2017-04-11 12:22:08, created)、(approved, 2017-04-13 13:25:17, approved)、(final, 2017-04-14 00:00:00, invoiced) ← 最後の日付の翌日に作った時刻 |

## 品質テストの候補(フェーズ3)

- 状態が delivered なのに、配達日時が空(警告として扱う)
- 日付の前後関係(承認日時が購入日時より前でないか、など)
