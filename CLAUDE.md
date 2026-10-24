# プロジェクトの引き継ぎメモ(2026-10-24)

## 目的
データエンジニアのポートフォリオ。EC データ(Olist)を、取り込み → 整形 → 集計 → Streamlit のダッシュボードと AI アナリストまで流す。詳細は Claude のドキュメント「データエンジニア ポートフォリオ 引き継ぎドキュメント」(要件、スコープ、フェーズ計画、決定事項)を参照する。

## 技術
S3 + Iceberg + Glue Data Catalog、Athena + dbt-athena、Airflow(ローカルの Docker、フェーズ2)、Terraform、GitHub Actions(OIDC、フェーズ4)、Streamlit + DuckDB、Snowflake 連携(フェーズ8)。環境は dev / test / prod。同じ AWS アカウントで、東京リージョン。

## 対話のルール(必ず守る)
- 初学者向け。1ステップずつ進め、ユーザーが「できた」と言うまで、次に進まない。
- コードは完成したものを出し、1行ずつ説明する。各コマンドは「何をするか」と「何のために実行するか」を書く。
- 新しいファイルは `cat > ファイル << 'EOF'`(上書き)で作る。`>>`(追記)は、重複するので、使うときは重複防止の確認を付ける。
- コードは、ユーザーが自分で書く方針。AI は、設計の相談、レビュー、説明、エラーの調査に使う。勝手に大量のコードを書かない。
- 設計判断は、docs/design と ADR に残す。

## 現在の状態
- AWS: 管理用ユーザー portfolio-admin(CLI)。root は MFA 設定済み。予算アラート設定済み。
- Terraform: terraform/bootstrap(状態ファイル用バケット)、terraform/envs/dev(main.tf、s3.tf、glue.tf、athena.tf、iam.tf)。
- dev の構成: データレイク用バケット1つ(raw/、iceberg/、athena-results/ をプレフィックスで分ける)、Glue データベース3つ(ecom_dev_bronze / silver / gold)、Athena の workgroup ecom-dev(1回1GiBの上限)、IAM ロール ecom-dev-ingest(raw/ の読み書きだけ)と ecom-dev-transform。AWS CLI のプロファイルは、ecom-dev-ingest と ecom-dev-transform。
- Python: uv、Python 3.12、pandas、pyarrow、boto3、pytest、ruff、ipykernel。ingestion/replay_orders.py(load_orders と build_events)を作成済みで、ruff は通過。コミットは、まだ。
- データ: data/olist/(Git の管理外)。orders は 99,441 件。購入日の期間は 2016-09-04 〜 2018-10-17。
- 設計メモ: docs/design/orders-vertical-slice.md、orders-data-profile.md、permissions.md。
- ノートブック: notebooks/(Git の管理外)で、build_events の中身を確認している途中。

## 次にやること
1. ノートブックで build_events の結果を確認する(出来事の合計の想定は 394,713 件)。
2. 日付ごとのスナップショットを作る(ステップ39)。
3. 日付ごとの Parquet に書き出す(ステップ40)。
4. ingest ロールで、raw/ に取り込む(ステップ41)。
5. Athena で Raw を読む外部テーブルを作り、Silver に MERGE する(ステップ42)。
- そのあと: 権限の整理(OIDC、deployer)、モジュール化、test と prod、Airflow、dbt。

## 未解決
- Olist のライセンス条件の確認(公開前までに)。
- 設計判断の ADR(Airflow、S3 の構成、環境の分け方など)を、フェーズ1の終わりに書く。
