# プロジェクトの引き継ぎメモ(更新: 2026-11-02)

## 目的
データエンジニアのポートフォリオ。EC データ(Olist)を、取り込み → 整形 → 集計 → Streamlit のダッシュボードと AI アナリストまで流す。要件、スコープ、フェーズ計画は docs/handoff.md(原本)を読む。タスク、進捗、現在の状態は docs/tasks.md を読む。

## 技術
S3 + Iceberg + Glue Data Catalog、Athena + dbt-athena、Airflow(ローカルの Docker、フェーズ2)、Terraform、GitHub Actions(OIDC、フェーズ4)、Streamlit + DuckDB、Snowflake 連携(フェーズ8、30日のトライアル)。環境は dev / test / prod。同じ AWS アカウントで、東京リージョン。

## 学習モードの進め方(必ず守る)
- ユーザーは、データ分析の経験はあるが、データエンジニアリングと AI 開発ツールは初学者。初めての内容が多いので、**1ステップずつ**進め、ユーザーが「できた」「OK」と言うまで、次に進まない。
- コードは完成したものを示し、**1行ずつ**説明する。各コマンドは「何をするか」と「何のために実行するか」を書く。
- 既定の進め方(誰が手を動かすか):
  - 初めて出てくる考え方: Claude が、完成コードと1行ずつの説明を先に示す。ユーザーが承認してから、Claude が書く。
  - すでにある形の繰り返し: ユーザーが書く。Claude は、まねる箇所と変える点を骨組みとヒントで示し、書いたコードをレビューする。
  - AWS を変えるコマンド(`terraform apply` など): ユーザーがターミナルで打つ。
  - 読むだけの確認と、長い定型のコード: Claude が行う。
  - どれに当たるか迷うときは、ステップの初めに Claude が案を示し、AskUserQuestion で聞く。
- 予想(例: plan で追加・変更される件数)と、ステップの終わりのまとめ(1〜2行)は、Claude が答えを書いて示す。ユーザーに理解確認の質問をしない。AWS を変える操作の前の承認と、設計の選択は聞く。
- 分からないことや、選んでほしいこと(例: 保存期間、名前の付け方)は、文章でなく AskUserQuestion の選択肢で聞く。推奨の案を最初に置く。「OK」で進めるかの確認は、文章でよい。
- 説明は、目的(なぜ必要か)→ たとえ(例: 荷物の追跡スタンプ)→ 実データの1〜2件の例 → コード、の順にする。表と専門用語を最初に並べない。ノートブックは1セル1処理にし、想定の出力をコメント(`# 出力:`)に書く。
- Iceberg の設定(table_type、パーティション、プロパティ、MERGE、スナップショットなど)は、項目ごとに「何をするか」と「なぜその値か」を説明する。
- 大きな方針変更(フェーズの計画、スコープや順番の変更、データが消える恐れのある作業)では、承認の前に、批評役のサブエージェント plan-critic(.claude/agents/plan-critic.md)に計画を3回レビューさせる。ふだんの設計書には使わない。
- Claude が書くファイルは、Write / Edit ツールで作る(VS Code で差分を見て承認できる)。ユーザーがターミナルで作るときは `cat > ファイル << 'EOF'`(上書き)を使い、追記(`>>`)には重複防止の確認(`grep -q ... ||`)を付ける。docs/ の下の既存ファイルは、差分を示して承認を得てから、変える行だけを書き換える。
- Terraform は、`plan` の内容を読んで説明してから `apply` する。削除(`-`)や置き換え(`-/+`)が出たら、必ず理由を説明する。
- AWS の操作は、実行を CLI かコードで行い(再現性と自動化のため)、結果の確認を GUI(マネジメントコンソール)で行う。コマンドごとに、GUI ではどこが変わるかを説明する。Terraform が管理するものは、GUI で変えない。Athena のクエリエディタでの試し書きは、GUI でよい。
- シェルの変数を使う手順と長いコマンドは、`&&` で1行にまとめ、ユーザーにターミナルへ直接打ってもらう(チャットの `!` 入力は、1回ごとに別のシェルになり、長い行が崩れることもある)。受付番号などは、変数に入れず表示させる。読むだけの操作は Claude が実行する。
- 長いエラーや出力は、要点だけを扱う(トークンの節約)。
- 設計判断は、docs/design と ADR(docs/adr)に残す。

## セッションの始め方と終わり方
- 始め方は skill の session-start、終わり方は skill の session-end に書いた。ユーザーが「続きから」「ここまでにする」と言ったら使う。
- 1つのセッションは、1〜3ステップを目安に区切る。区切りで、新しいセッションにする。

## 禁止事項(Public のリポジトリ)
- アクセスキー、パスワード、AWS のアカウント ID、トークンを、ファイルに書かない。
- 元データ(data/ 、*.parquet)とノートブック(notebooks/)は、Git に入れない(.gitignore で除外済み)。
- Terraform の状態ファイル(*.tfstate)と .terraform/ は、Git に入れない。
- コミットは `git add <ファイル名>` で、対象を指定する。`git add .` は使わない。コミットと push は、区切りごとに Claude が行ってよい(git のコマンドの説明は不要)。
- このうち、秘密のファイルとフォルダを読むこと、`git add .` などのまとめての追加、`terraform apply` / `destroy` は、.claude/settings.json の deny と hook で止める。deny は文字列の照合なので完全ではない。最後の守りは、コミットの前の gitleaks にする。
- Claude がコミットするときは、毎回、skill の session-end の「上げてはいけないデータの確認」をしてからにする。

## リポジトリの構成
- .claude: settings.json(Git に入る allow / ask / deny と hook の登録)、hooks(guard-bash.sh: 危ない Bash を止める)、skills(session-start、session-end、tf-plan)、agents(plan-critic、モデルは sonnet)
- .pre-commit-config.yaml: コミットの前の gitleaks(`uv run pre-commit install` は、マシンごとに1回)
- terraform/bootstrap: 状態ファイル用の S3 バケット
- terraform/global: アカウント共通のリソース(Budgets、OIDC など。いまは空。状態は S3 の global/terraform.tfstate)
- terraform/envs/dev: main.tf、s3.tf、glue.tf、athena.tf、iam.tf、bronze.tf(test と prod は、モジュール化のあとで作る)
- ingestion: リプレイと取り込みの Python(replay_orders.py に load_orders、convert_timestamps、build_events、build_snapshot、write_snapshot。run_log.py に RunLog(JSON Lines のログ)。validate_orders.py に read_orders_csv、validate_orders、write_quarantine、IngestStop(停止と隔離の判定、隔離の書き出し)。run_replay.py は、期間を指定して、検証・ログ・隔離を呼びながら日付ごとに書き出す実行役)
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
- Claude Code の構成(2026-11-02): 絶対に止めることは .claude/settings.json の deny と hook(最後の守りは gitleaks)、いつも守ることは CLAUDE.md、ときどきやる手順は .claude/skills、大きな方針のレビューは .claude/agents/plan-critic に置く。あとで入れるものと入れないものは、tasks.md に書いた。

## 運用メモ
- 元データは data/olist/ にある(Git の管理外)。
- 確認用のノートブック notebooks/replay_orders_explore.ipynb がある(Git の管理外、このマシンだけ)。モジュールを変えたあとは、カーネルの再起動が必要。
- 次にやること、ADR の候補、未解決のことは、docs/tasks.md にまとめた。
- notebooks/validate_orders_explore.ipynb は、validate_orders の動きを1つずつ確認するノートブック(Git の管理外、このマシンだけ。元のコードの A〜I の対応は、先頭のセルに書いてある)。
