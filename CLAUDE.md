# プロジェクトの引き継ぎメモ(更新: 2026-10-27)

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
- AWS の操作は、実行を CLI かコードで行い(再現性と自動化のため)、結果の確認を GUI(マネジメントコンソール)で行う。コマンドごとに、GUI ではどこが変わるかを説明する。Terraform が管理するものは、GUI で変えない。Athena のクエリエディタでの試し書きは、GUI でよい。
- シェルの変数を使う手順は、ユーザーがターミナルに直接打つよう案内する(チャットの `!` 入力や Run ボタンは、1回ごとに別のシェルになり、変数が残らないことがある)。
- シェルの変数を使う手順は、`&&` で1行にまとめて示す(チャットの `!` 入力でも、同じシェルで動くように)。受付番号などは、変数に入れず表示させる。
- チャットの `!` 入力では、長い1行のコマンドが崩れて実行されないことがある。長いコマンドは、ターミナルに直接打ってもらうか、読むだけの操作なら Claude が実行する。
- 長いエラーや出力は、要点だけを扱う(トークンの節約)。
- 設計判断は、docs/design と ADR(docs/adr)に残す。

## セッションの始め方と終わり方
- 始め方: ユーザーが「続きから」と言ったら、まず `git status -sb` で、未コミットと未 push を確認する。そのうえで、「現在の状態」と「次にやること」を3行で要約し、最初のステップを1つだけ提案して、返事を待つ。承認なしに、ファイルの変更やコマンドの実行をしない。
- 終わり方: ユーザーが「ここまでにする」と言ったら、「現在の状態」と「次にやること」の更新案を示す。承認されたら CLAUDE.md を更新し、コミットと push まで行う。
- 1つのセッションは、1〜3ステップを目安に区切る。区切りで、新しいセッションにする。

## 禁止事項(Public のリポジトリ)
- アクセスキー、パスワード、AWS のアカウント ID、トークンを、ファイルに書かない。
- 元データ(data/ 、*.parquet)とノートブック(notebooks/)は、Git に入れない(.gitignore で除外済み)。
- Terraform の状態ファイル(*.tfstate)と .terraform/ は、Git に入れない。
- コミットは `git add <ファイル名>` で、対象を指定する。`git add .` は使わない。コミットと push は、区切りごとに Claude が行ってよい(git のコマンドの説明は不要)。

## リポジトリの構成
- terraform/bootstrap: 状態ファイル用の S3 バケット
- terraform/envs/dev: main.tf、s3.tf、glue.tf、athena.tf、iam.tf、bronze.tf(test と prod は、モジュール化のあとで作る)
- ingestion: リプレイと取り込みの Python(replay_orders.py に load_orders、build_events、build_snapshot、write_snapshot。run_replay.py は、期間を指定して日付ごとに書き出す実行役)
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
- ingestion/replay_orders.py に、4つの関数がそろった(load_orders、build_events、build_snapshot、write_snapshot)。出来事の合計は 394,713 件、リプレイは 696 日で全日の合計 310,311 行。
- ingestion/run_replay.py で、2017-10-04〜06 の3日分(603 / 476 / 511 行、11 列)を書き出し、S3 の raw/olist/orders/ingest_date=…/ にアップロード済み。
- Bronze の外部テーブル ecom_dev_bronze.orders を、Terraform(terraform/envs/dev/bronze.tf、aws_glue_catalog_table)で作成した。
  - ingest_date(string)を、パーティション射影で扱う(2016-09-01〜2018-12-31、1日刻み)。
  - クエリエディタで試したテーブルは DROP し、Terraform で作り直した。
  - 3日分の件数と、例の注文(e481f51c…、10-04 は shipped)が読めることを確認済み。コミットと push も済み。
- Bronze を外部テーブルにした理由と、列が増えたときの手順は、docs/design/orders-vertical-slice.md の「決めたこと(2026-10-26)」を参照。
- ingest ロールで iceberg/ に入れないことの確認は、スキップした。
- Silver(ecom_dev_silver.orders、Iceberg)を、sql/silver/create_orders.sql で作成した(transform ロール、AWS CLI から Athena で実行)。
  - 定義は Terraform ではなく SQL で管理する(のちに dbt)。理由と設定値は、設計書の「決めたこと(2026-10-26)」を参照。
  - MERGE の判定用に `_ingest_date`(date)を、ALTER TABLE で追加した。create_orders.sql にも反映済み。
- sql/silver/merge_orders.sql で、10-04〜06 を MERGE した。Silver は 1,308 行で、Bronze の3日分の order_id の種類の数と一致した。コミットと push も済み。
- 再実行の確認が終わり、**orders の縦通しは完了**した。スナップショットは1つ(再実行では変わる行がなく、Athena はスナップショットを作らない)。差分は 0、件数は 1308 / 1308、protected_orders は 175、leaked_rows は 0。結果は設計書の「検証の結果(2026-10-27)」に記録した。
- Silver の中身(Iceberg)を確認した。台帳(metadata.json)が3つ(CREATE、ALTER、MERGE)、.avro が2つ、データのファイルが3つ(購入月の 2017-08 / 09 / 10 で、7 / 527 / 774 行)。スナップショットの operation は overwrite だった。
- order_estimated_delivery_date が _ingest_date より後なのは、仕様どおり(購入時に決まる予定日。リプレイで空にするのは、承認、引き渡し、配達の3列だけ)。
- orders のデータは data/olist/ にある。
- 確認用のノートブック notebooks/replay_orders_explore.ipynb がある(Git の管理外、このマシンだけ)。モジュールを変えたあとは、カーネルの再起動が必要。

## 次にやること
1. エラーの設計: ログを S3 に残し、原因をメッセージに書き出す。
   - メッセージの形は `[処理_段階] 何が / どの列で / 何件 (例: …)`。例: `[ORDERS_VALIDATE] order_status に想定外の値があります: 3件`。
   - 置き場所は S3 の logs/(JSON Lines。実行ごとに `run_date=` と `run_id=` で分ける)。不良な行は quarantine/ に隔離する。
   - 最初の対象は Python の取り込み(run_replay.py)。Athena の MERGE の失敗(QueryExecutionId と理由)は、そのあとに入れる。
   - ingest ロールに logs/ と quarantine/ への書き込みを、Terraform で足す。
   - まず設計書(docs/design)に方針を書いてから、コードに入る。
2. そのあと: 権限の整理(OIDC、deployer。ingest ロールで iceberg/ に入れないことの確認も、ここで行う)、モジュール化、test と prod、Airflow、dbt、ADR。
- ADR の候補(フェーズ1の終わり): Bronze を外部テーブルにした理由、Raw をスナップショットの形にした理由、Raw の段階で型を付けた Parquet にした簡略化、エラーのログを S3 に JSON Lines で残す理由。

## 未解決
- Olist のライセンス条件の確認(公開前までに)。
- 設計判断の ADR(Airflow、S3 の構成、環境の分け方など)を、フェーズ1の終わりに書く。
