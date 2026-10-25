# orders のデータ確認結果とリプレイのルール

- 作成日: 2026-10-23
- 対象: `olist_orders_dataset.csv`

## 確認した内容

- 件数: 99,441 件(ヘッダーを除く)
- 購入日時の期間: 2016-09-04 〜 2018-10-17(約770日)
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

## 気づいたこと

- CSV の引用符が、行や列によって、付いたり付かなかったりする。CSV として問題はないが、自前の文字列処理で分割せず、CSV を解釈するライブラリで読む。
- invoiced、processing、unavailable、canceled には、その状態になった日時の列がない。
- delivered なのに、配達日時が空の注文が 8 件、承認日時が空の注文が 14 件、引き渡し日時が空の注文が 2 件ある。
- canceled のうち、6 件は配達日時を持つ(配達後にキャンセルされた)。

## リプレイのルール

各注文について、次の出来事を日付順に並べて再生する。

| 出来事 | 日付の元 | その時点の状態 |
|---|---|---|
| 購入 | order_purchase_timestamp | created |
| 承認 | order_approved_at(空なら飛ばす) | approved |
| 引き渡し | order_delivered_carrier_date(空なら飛ばす) | shipped |
| 配達 | order_delivered_customer_date(空なら飛ばす) | delivered |
| 最終状態への変化 | 下記 | 元データの order_status |

- 最終状態への変化は、日時の列がない状態(invoiced、processing、unavailable、canceled)と、delivered なのに配達日時が空の注文に適用する。最後に分かっている日付の翌日に、その状態になったことにする(合成の扱いは、orders-vertical-slice.md の「決めたこと」を参照)。
- 日付 D には、D に出来事があった注文を、D 時点で分かっている日時の列だけを埋めて出力する。まだ起きていない日時の列は空にする。
- order_estimated_delivery_date は、購入時から分かっているものとして、最初から入れる。

## 品質テストの候補(フェーズ3)

- 状態が delivered なのに、配達日時が空(警告として扱う)
- 日付の前後関係(承認日時が購入日時より前でないか、など)

## build_events の出力(2026-10-24 確認)

`ingestion/replay_orders.py` の `build_events` は、上のリプレイのルールの「出来事を並べる」部分を実装したもの。

- 入力: orders(1行 = 1つの注文、99,441行)。日時は横に並んだ4列で持つ。
- 出力: 出来事の表(1行 = 1つの出来事、394,713行)。列は次の3つ。

| 列 | 意味 |
|---|---|
| `order_id` | どの注文の出来事か |
| `event_date` | 出来事の日付(時刻は捨て、日付だけにする) |
| `rank` | 出来事の段階。0 作成、1 承認、2 引き渡し、3 配達、4 最終状態。同じ日に複数の出来事があるとき、大きいほうが後 |

- rank ごとの件数: 0 が 99,441、1 が 99,281、2 が 97,658、3 が 96,476、4 が 1,857。
- rank 4 の内訳: 日時の列がない状態(invoiced、processing、unavailable、canceled)が 1,849 件、delivered なのに配達日時が空が 8 件。両方に当てはまる注文はない。
- 確認の方法: ノートブックで関数の中身を1行ずつ再現し、関数の結果と完全に一致することを確かめた(`DataFrame.equals` が True)。

例:

| order_id | 元の order_status | 出来事(event_date, rank) |
|---|---|---|
| e481f51cbdc54678b7cc49136f2d6af7 | delivered | (2017-10-02, 0)、(2017-10-02, 1)、(2017-10-04, 2)、(2017-10-10, 3) |
| 136cce7faa42fdb2cefd53fdc79a6098 | invoiced | (2017-04-11, 0)、(2017-04-13, 1)、(2017-04-14, 4) ← 最後の日付の翌日に合成 |

使い道: 日付ごとのスナップショットの元帳にする。日付 D までの出来事のうち、注文ごとに rank が最大のものが、D 時点の状態になる(rank 4 は、元の order_status)。

## build_snapshot の出力(2026-10-25 確認)

`build_snapshot(orders, events, D)` は、日付 D の「日報」を返す。

- 行: D に出来事があった注文が、1件につき1行。同じ日に出来事が複数あっても(例: 購入と承認が同じ日)、1行にまとまる。
- 列: orders と同じ8列。`order_status` と日時の3列(承認、引き渡し、配達)だけが、D 時点の見え方に変わる。
  - `order_status`: D までの出来事のうち、rank が最大のものの状態。rank 4 のときは、元の order_status。
  - 日時の3列: D より後の日時は空(NaT)。購入日時と配達予定日は、そのまま。
- リプレイの日数は 696 日(2016-09-04 〜 2018-10-18)。出来事が1つもない日は、日報を作らない。
- 全日の合計は 310,311 行。(order_id, event_date) の組の数と一致する(取りこぼしや重複がない)。

例(D = 2017-10-04、603 行):

| order_id | 元の order_status | D 時点の order_status | 配達日時 |
|---|---|---|---|
| e481f51cbdc54678b7cc49136f2d6af7 | delivered | shipped | 空(実際は 2017-10-10) |
| 2e935fa1d39497aa0ec3f1107fbfb5b8 | unavailable | unavailable(rank 4) | 空 |

- 状態ごとの件数(2017-10-04): shipped 272、delivered 146、approved 134、created 47、unavailable 2、invoiced 2。
- 確認の方法: ノートブックで関数の中身を1行ずつ再現し、関数の結果と完全に一致することを確かめた(`DataFrame.equals` が True)。
