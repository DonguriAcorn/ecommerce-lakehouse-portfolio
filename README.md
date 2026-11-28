# ecommerce-lakehouse-portfolio

ブラジルの EC データ(Olist)を、**取り込み → S3 + Iceberg → dbt で整形・集計 → Streamlit のダッシュボード**まで流す、データエンジニアリングの個人ポートフォリオです。業務システムが毎日ファイルを送ってくる状況を再現し、検証・冪等性・権限・CI/CD・公開の範囲までを、実際に AWS 上で動かして確かめています。

- 公開アプリ: https://ecommerce-lakehouse-portfolio-woun4frc84qvxofobwl2ik.streamlit.app/
- 状態: v1.0(フェーズ5まで)を公開済み。AI アナリストはフェーズ6、仕上げはフェーズ7

## データの流れ

```
simulator(業務システムの代わり。届いた日ごとの JSON Lines)
  → ingestion(検証・隔離・型付け・監査カラム) → S3 raw/ → Bronze(Glue の外部テーブル)
  → dbt: Silver(Iceberg。MERGE で「いまの状態」に畳む) → Gold(事実 2・dim 3) → 公開用の集計 pub_
  → export(Parquet) → app/data/ → Streamlit + DuckDB
```

- 毎日の流れは Airflow(ローカルの Docker)が動かします。取り込み 7 表 → S3 → `dbt run` → `dbt test`。
- 対象は Olist の 7 表(orders、order_items、reviews、customers、sellers、products、カテゴリの英訳)で、期間は 2016-09-04〜2018-10-18 の 775 日です。

## 使っている技術

| 役割 | 技術 |
| --- | --- |
| 保存 | S3、Apache Iceberg、Glue Data Catalog |
| 整形・集計 | Athena、dbt(dbt-athena) |
| 取り込み | Python 3.12(pandas、pyarrow、boto3)、uv |
| 実行の管理 | Airflow 3(ローカルの Docker Compose) |
| インフラ | Terraform(環境は dev と prod。共通のモジュール) |
| CI/CD | GitHub Actions(OIDC)、ruff、pytest、gitleaks |
| アプリ | Streamlit、DuckDB、自前のセマンティックレイヤー |

## 見どころ

| テーマ | やったこと | 詳しく |
| --- | --- | --- |
| Raw は出来事の記録 | orders は状態の写しではなく、出来事を1行ずつ積む。遅れて届く出来事でも Silver の結果が変わらないことを確かめた | [ADR 0010](docs/adr/0010-raw-event-records.md)、[orders の設計](docs/design/orders-vertical-slice.md) |
| 取り込みの検証と隔離 | 送る側との約束(列・型・期間)を registry に1か所で書き、外れた行は隔離して記録する | [エラーの設計](docs/design/error-handling.md)、[7表のリプレイ](docs/design/replay-tables.md) |
| 冪等性 | Silver は MERGE。同じ日・古い日を流し直しても指紋が同じ。元の CSV と注文ごとに突き合わせて差分 0 | [バックフィル(ADR 0014)](docs/adr/0014-backfill-by-window.md) |
| Iceberg の整理 | OPTIMIZE → VACUUM で、Parquet のファイル数が 109 → 25 個。行数と指紋は変わらない | [手順と結果](docs/design/iceberg-maintenance.md)、[ADR 0013](docs/adr/0013-iceberg-maintenance.md) |
| Gold の設計 | 明細と注文の2つの事実テーブル。顧客は SCD2 で州と郵便番号の変化を追う | [Gold の設計](docs/design/gold-design.md)、[ADR 0015](docs/adr/0015-gold-grain-and-scd2.md) |
| PII | 顧客の ID は salt つき SHA-256、郵便番号は先頭3桁に丸める | [PII のハッシュ化](docs/design/pii-hashing.md) |
| 権限 | ロールは用途ごとに分け、AWS の鍵は持たない(一時キーと OIDC)。prod の deployer は権限境界つきのロールしか作れない | [権限の設計](docs/design/permissions.md)、[ADR 0017](docs/adr/0017-github-actions-oidc-roles.md)、[シークレット](docs/design/secrets.md) |
| CI/CD | PR で ruff、pytest、terraform plan(3か所)、練習用の環境での dbt build。main へのマージ後、承認すると保存した plan だけを prod に apply する | [.github/workflows/](.github/workflows/) |
| 公開の範囲 | データのライセンスに合わせ、公開するのは集計だけ。アプリは AWS に接続せず、リポジトリの Parquet を読む | [ADR 0018](docs/adr/0018-public-export-and-license.md) |
| 指標の定義 | 指標は1か所の YAML で定義し、画面は同じ関数を通して数字を出す(計算式を画面に書かない) | [semantic/metrics.yml](semantic/metrics.yml) |

設計の判断は [docs/adr/](docs/adr/) に、要件とフェーズの計画は [docs/handoff.md](docs/handoff.md) にあります。

## 手元でアプリを開く

公開用の集計(`app/data/*.parquet`)はリポジトリに入っているので、AWS がなくても開けます。

```bash
uv sync                               # ライブラリを入れる
uv run streamlit run app/app.py       # ブラウザで http://localhost:8501 が開く
```

画面は「売上 KPI」「期間比較」「リピート率」「カテゴリランキング」の4つです。パイプライン全体(AWS、Airflow)の立ち上げ手順は、フェーズ7で書き足します。

## データの出典とライセンス

- データ出典: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)(Kaggle)。ライセンスは [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。
- `app/data/` の集計は元データからの派生物で、同じ CC BY-NC-SA 4.0 で公開します。行単位のデータは公開しません。
- 非商用の学習用ポートフォリオです。金額の単位はブラジルレアル(BRL)です。
- コードのライセンスは [MIT](LICENSE) です(データには適用しません)。
