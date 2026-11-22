# PII のハッシュ化の設計と限界

更新: 2026-11-22

## 何をしているか

- マクロ `dbt/macros/pii_hash.sql`。`salt + 値` を SHA-256 にかけ、16進の文字列にする。元には戻せない。同じ値は、いつも同じハッシュになる。
- 対象は Gold の出力だけ。
  - `customer_unique_id`(dim_customer と fact_orders): ハッシュにする。リピートの判定は、同じハッシュかどうかで行う。
  - 郵便番号: 先頭3桁に丸める。
- `customer_sk`(代理キー)は、ハッシュ前の元の ID から作る。ハッシュの方式を変えても、`customer_sk` は変わらない。
- salt は環境変数 `PII_SALT` から読む。
  - 手元の dbt: `airflow/.env` の値を `export` する。
  - Airflow: `airflow/docker-compose.yaml` が `.env` から読んでコンテナに渡す。
  - 2026-11-22 に、使い捨ての salt から本物の salt に切り替え、dev の Gold を作り直した(tests 31 本 PASS)。

## なぜこの形か

- **salt に既定値を付けない**: 未設定なら dbt が止まる。salt なしの弱いハッシュで、黙って進むのを防ぐ。
- **dim と fact の両側を同じハッシュで結ぶ**: fact_orders は dim_customer のハッシュ済みの列と結ぶので、手元と Airflow で salt が違うと結合が崩れる。salt は1つの値を、両方で共有する。
- **Olist はもともと匿名**: 本物の個人情報はない。ここは、仕組みを示すための実装。

## 限界(正直に書く)

1. **salt が SQL の文章に入る**: dbt が SQL を組み立てるときに、salt が文字列として入る。次の場所に平文で残る。
   - dbt のログ(`dbt/logs/`)
   - `dbt/target/compiled/`
   - Athena のクエリ履歴(Athena の権限があれば読める)
   salt が漏れると、ID の候補を総当たりして、ハッシュから元の ID を推測できる。
2. **Silver には生の ID が残っている**: ハッシュ化は Gold の出力だけ。Silver、Bronze、Raw には、元の `customer_unique_id` が入っている。Gold だけを読む画面や AI アナリストは守れるが、Silver を読める人は守れない。
3. **郵便番号は丸めただけ**: 先頭3桁に丸めたが、他の列と組み合わせると、個人が絞り込める可能性は残る。なお SCD2 の変化の追跡には、先頭5桁を使う(gold-design.md)。
4. **salt を変えると、ハッシュが全部変わる**: 過去のハッシュと突き合わせられなくなる。salt の入れ替え(ローテーション)の手順は作っていない。

## 本番ならこうする

- 取り込みの段階(Raw に書く前)でハッシュ化し、元の ID を下流に流さない。
- salt は Secrets Manager などに置き、SQL の文章に入れない。ハッシュはクエリでなく、取り込みのコードか UDF で計算する。
- 元の ID と別の表に分け、権限を分ける。Athena のクエリ履歴の閲覧権限も絞る。
- salt のローテーションの手順を決める。
