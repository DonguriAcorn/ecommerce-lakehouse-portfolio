# プロジェクトの引き継ぎメモ(更新: 2026-10-30)

## 目的
データエンジニアのポートフォリオ。EC データ(Olist)を、取り込み → 整形 → 集計 → Streamlit のダッシュボードと AI アナリストまで流す。要件、スコープ、フェーズ計画は docs/handoff.md(原本)を読む。タスクと進捗は docs/tasks.md を読む。

## 技術
S3 + Iceberg + Glue Data Catalog、Athena + dbt-athena、Airflow(ローカルの Docker、フェーズ2)、Terraform、GitHub Actions(OIDC、フェーズ4)、Streamlit + DuckDB、Snowflake 連携(フェーズ8、30日のトライアル)。環境は dev / test / prod。同じ AWS アカウントで、東京リージョン。

## ユーザーと対話のルール(必ず守る)
- ユーザーは、データ分析の経験はあるが、データエンジニアリングは初学者。初めての内容が多いので、**1ステップずつ**進め、ユーザーが「できた」と言うまで、次に進まない。
- コードは完成したものを示し、**1行ずつ**説明する。各コマンドは「何をするか」と「何のために実行するか」を書く。
- 既定の進め方: 完成コードと1行ずつの説明を、先に示す。ユーザーが承認してから、ファイルを書く。ユーザーが「自分で書く」と言った部分は、骨組みとヒントだけを出し、書いたコードのレビューに回る。
- ファイルは `cat > ファイル << 'EOF'`(上書き)で作る。追記(`>>`)は重複するので、使うときは、重複防止の確認(`grep -q ... ||`)を付ける。例外: docs/ の下の既存ファイルは、差分を示して承認を得たうえで、変える行だけを書き換えてよい。
- Terraform は、`plan` の内容を読んで説明してから `apply` する。削除(`-`)や置き換え(`-/+`)が出たら、必ず理由を説明する。
- 説明は、たとえ(例: 荷物の追跡スタンプ)と、実データの1〜2件の例を使い、かんたんな言葉から始める。ノートブックは1セル1処理にし、想定の出力をコメント(`# 出力:`)に書く。
- AWS の操作は、実行を CLI かコードで行い(再現性と自動化のため)、結果の確認を GUI(マネジメントコンソール)で行う。コマンドごとに、GUI ではどこが変わるかを説明する。Terraform が管理するものは、GUI で変えない。Athena のクエリエディタでの試し書きは、GUI でよい。
- シェルの変数を使う手順は、ユーザーがターミナルに直接打つよう案内する(チャットの `!` 入力や Run ボタンは、1回ごとに別のシェルになり、変数が残らないことがある)。
- シェルの変数を使う手順は、`&&` で1行にまとめて示す(チャットの `!` 入力でも、同じシェルで動くように)。受付番号などは、変数に入れず表示させる。
- チャットの `!` 入力では、長い1行のコマンドが崩れて実行されないことがある。長いコマンドは、ターミナルに直接打ってもらうか、読むだけの操作なら Claude が実行する。
- 長いエラーや出力は、要点だけを扱う(トークンの節約)。
- 設計判断は、docs/design と ADR(docs/adr)に残す。

## セッションの始め方と終わり方
- 始め方: ユーザーが「続きから」と言ったら、まず `git status -sb` で、未コミットと未 push を確認する。そのうえで、docs/tasks.md の「← 今ここ」と、下の「現在の状態」を読み、3行で要約する。「次の1手」を最初のステップとして1つだけ提案して、返事を待つ。承認なしに、ファイルの変更やコマンドの実行をしない。
- 終わり方: ユーザーが「ここまでにする」と言ったら、docs/tasks.md と「現在の状態」の更新案を示す。
  - タスクが済んだとき: `[x]` にして「← 今ここ」を次の `[ ]` に移し、「現在の状態」を書き直す。
  - 途中のとき: 「現在の状態」だけを更新する。
  - 承認されたら両方を更新し、1つのコミットにして push まで行う。
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
- sql/silver: Silver の SQL(create_orders.sql、merge_orders.sql、check_orders_rerun.sql。フェーズ2で dbt に移す)
- docs: handoff.md(要件とスコープの原本)、tasks.md(タスクと進捗)
- docs/design: orders-vertical-slice.md、orders-data-profile.md、permissions.md、error-handling.md
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
- orders の縦通し: Olist の orders(99,441 件、購入日は 2016-09-04 〜 2018-10-17)を、日付ごとにリプレイして Raw → Silver(Iceberg、MERGE)まで通した。詳細は docs/design を参照。
- テーブル定義の管理: Bronze は外部テーブルで Terraform(bronze.tf)、Silver は SQL(フェーズ2で dbt に移す)。理由は orders-vertical-slice.md の「決めたこと(2026-10-26)」を参照。
- handoff からの順番の変更(2026-10-30): dbt、ruff、pytest をフェーズ2に前倒しする。エラーの設計は Python の取り込みだけにし、dbt の失敗は Airflow の運用で扱う。

## 現在の状態
- 途中経過: エラーの設計の方針(error-handling.md)を書き、permissions.md に logs/ と quarantine/ を足した。Terraform と run_replay.py の実装は、まだ。
- 次の1手: iam.tf で、ingest ロールに logs/ と quarantine/ の書き込み(PutObject)と一覧(ListBucket)の権限を足し、plan を読んでから apply する。

## 運用メモ
- 元データは data/olist/ にある(Git の管理外)。
- 確認用のノートブック notebooks/replay_orders_explore.ipynb がある(Git の管理外、このマシンだけ)。モジュールを変えたあとは、カーネルの再起動が必要。
- 次にやること、ADR の候補、未解決のことは、docs/tasks.md にまとめた。
