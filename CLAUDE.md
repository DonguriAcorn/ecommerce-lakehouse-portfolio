# プロジェクトの引き継ぎメモ(更新: 2026-10-24)

## 目的
データエンジニアのポートフォリオ。EC データ(Olist)を、取り込み → 整形 → 集計 → Streamlit のダッシュボードと AI アナリストまで流す。要件、スコープ、フェーズ計画の詳細は、Claude のドキュメント「データエンジニア ポートフォリオ 引き継ぎドキュメント」を参照する(リポジトリに docs/handoff.md として保存した場合は、そちらを読む)。

## 技術
S3 + Iceberg + Glue Data Catalog、Athena + dbt-athena、Airflow(ローカルの Docker、フェーズ2)、Terraform、GitHub Actions(OIDC、フェーズ4)、Streamlit + DuckDB、Snowflake 連携(フェーズ8、30日のトライアル)。環境は dev / test / prod。同じ AWS アカウントで、東京リージョン。

## ユーザーと対話のルール(必ず守る)
- ユーザーは、データ分析の経験はあるが、データエンジニアリングは初学者。初めての内容が多いので、**1ステップずつ**進め、ユーザーが「できた」と言うまで、次に進まない。
- コードは完成したものを示し、**1行ずつ**説明する。各コマンドは「何をするか」と「何のために実行するか」を書く。
- 既定の進め方: 完成コードと1行ずつの説明を、先に示す。ユーザーが承認してから、ファイルを書く。ユーザーが「自分で書く」と言った部分は、骨組みとヒントだけを出し、書いたコードのレビューに回る。
- ファイルは `cat > ファイル << 'EOF'`(上書き)で作る。追記(`>>`)は重複するので、使うときは、重複防止の確認(`grep -q ... ||`)を付ける。
- Terraform は、`plan` の内容を読んで説明してから `apply` する。削除(`-`)や置き換え(`-/+`)が出たら、必ず理由を説明する。
- 説明は、たとえ(例: 荷物の追跡スタンプ)と、実データの1〜2件の例を使い、かんたんな言葉から始める。ノートブックは1セル1処理にし、想定の出力をコメント(`# 出力:`)に書く。
- 長いエラーや出力は、要点だけを扱う(トークンの節約)。
- 設計判断は、docs/design と ADR(docs/adr)に残す。

## セッションの始め方と終わり方
- 始め方: ユーザーが「続きから」と言ったら、まず `git status -sb` で、未コミットと未 push を確認する。そのうえで、「現在の状態」と「次にやること」を3行で要約し、最初のステップを1つだけ提案して、返事を待つ。承認なしに、ファイルの変更やコマンドの実行をしない。
- 終わり方: ユーザーが「ここまでにする」と言ったら、「現在の状態」と「次にやること」の更新案を示す。承認されたら CLAUDE.md を更新し、コミットと push の手順を案内する。
- 1つのセッションは、1〜3ステップを目安に区切る。区切りで、新しいセッションにする。

## 禁止事項(Public のリポジトリ)
- アクセスキー、パスワード、AWS のアカウント ID、トークンを、ファイルに書かない。
- 元データ(data/ 、*.parquet)とノートブック(notebooks/)は、Git に入れない(.gitignore で除外済み)。
- Terraform の状態ファイル(*.tfstate)と .terraform/ は、Git に入れない。
- コミットは `git add <ファイル名>` で、対象を指定する。`git add .` は使わない。

## リポジトリの構成
- terraform/bootstrap: 状態ファイル用の S3 バケット
- terraform/envs/dev: main.tf、s3.tf、glue.tf、athena.tf、iam.tf(test と prod は、モジュール化のあとで作る)
- ingestion: リプレイと取り込みの Python(replay_orders.py に load_orders と build_events)
- docs/design: orders-vertical-slice.md、orders-data-profile.md、permissions.md
- docs/adr: 設計判断の記録(フェーズ1の終わりに書く)
- notebooks: 確認用のノートブック(Git の管理外)
- dbt、airflow、app、semantic、tests: これから使う

## 決めたこと(要点)
- S3: 環境ごとに1バケット(`ecom-lakehouse-<環境>-<アカウント ID>`)。中を raw/、iceberg/、athena-results/ のプレフィックスで分ける。
- Glue: `ecom_<環境>_bronze` / `silver` / `gold` の3つ。
- Athena: workgroup `ecom-<環境>`、1回のクエリで読める量の上限は 1 GiB。`primary` は使わせない。
- IAM: ロールは `ecom-<環境>-ingest`(raw/ の読み書きだけ)と `ecom-<環境>-transform`。信頼ポリシーは portfolio-admin。reader と deployer は、あとで作る。AWS CLI のプロファイルは `ecom-dev-ingest` と `ecom-dev-transform`。
- Terraform: envs/dev、test、prod を並列に置き、状態は S3 のバックエンド(`use_lockfile`)。モジュール化は、フェーズ1の最後に行う。
- Python: uv、Python 3.12(pandas、pyarrow、boto3、pytest、ruff、ipykernel)。
- スコープ: 必須と推奨の要素は、すべて入れる。対象外は、セマンティックレイヤー Lv3、OpenLineage、IaC のセキュリティスキャン、障害注入、複数ステップ分析、専用のデータカタログ、CloudWatch。
- orders の縦通し: Olist の orders(99,441 件、購入日は 2016-09-04 〜 2018-10-17)を、日付ごとにリプレイして Raw → Silver(Iceberg、MERGE)まで通す。詳細は docs/design を参照。

## 現在の状態
- AWS の土台(S3、Glue、Athena、2つの IAM ロール)は、dev に作成済み。コミットと push も済み。
- Python の環境(uv)は作成済み。
- ingestion/replay_orders.py(`load_orders` と `build_events`)は作成済みで、ruff は通過。コミットと push も済み。
- orders のデータは data/olist/ にある。
- `build_events` の結果を確認済み。出来事の合計は 394,713 件で、rank ごとの件数も想定どおり。手で再現した表とも完全に一致した。出力の形は、docs/design/orders-data-profile.md の「build_events の出力」を参照。
- 確認用のノートブック notebooks/replay_orders_explore.ipynb がある(Git の管理外、このマシンだけ)。1セル1処理で、想定の出力を `# 出力:` のコメントに書いてある。

## 次にやること
1. 日付ごとのスナップショットを作る(日付 D までの出来事のうち、注文ごとに rank が最大のものを選び、D 時点の状態を作る)。
2. 日付ごとの Parquet に書き出す。
3. ingest ロールで、raw/ に取り込む。
4. Athena で Raw を読む外部テーブルを作り、Silver に MERGE する。
- そのあと: 権限の整理(OIDC、deployer)、モジュール化、test と prod、Airflow、dbt、ADR。

## 未解決
- Olist のライセンス条件の確認(公開前までに)。
- 設計判断の ADR(Airflow、S3 の構成、環境の分け方など)を、フェーズ1の終わりに書く。
