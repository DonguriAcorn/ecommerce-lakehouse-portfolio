# プロジェクトの引き継ぎメモ(更新: 2026-11-03)

## 目的
データエンジニアのポートフォリオ。EC データ(Olist)を、取り込み → 整形 → 集計 → Streamlit のダッシュボードと AI アナリストまで流す。要件、スコープ、フェーズ計画は docs/handoff.md(原本)を読む。タスク、進捗、現在の状態は docs/tasks.md を読む。

## 技術
S3 + Iceberg + Glue Data Catalog、Athena + dbt-athena、Airflow(ローカルの Docker、フェーズ2)、Terraform、GitHub Actions(OIDC、フェーズ4)、Streamlit + DuckDB、Snowflake 連携(フェーズ8、30日のトライアル)。環境は dev / test / prod。同じ AWS アカウントで、東京リージョン。

## 学習モードの進め方(必ず守る)
- ユーザーは、データ分析の経験はあるが、データエンジニアリングと AI 開発ツールは初学者。初めての内容が多いので、**1ステップずつ**進め、ユーザーが「できた」「OK」と言うまで、次に進まない。
- コードは完成したものを示し、**1行ずつ**説明する。各コマンドは「何をするか」と「何のために実行するか」を書く。
- Claude が書くコード(テストも含む)には、ブロックや主要な行ごとに、何をしているかを日本語のコメントで残す。周りのコードのコメントが少なくても、この方針を優先する。
- 既定の進め方(誰が手を動かすか):
  - 初めて出てくる考え方: Claude が、完成コードと1行ずつの説明を先に示す。ユーザーが承認してから、Claude が書く。
  - すでにある形の繰り返し: ユーザーが書く。Claude は、まねる箇所と変える点を骨組みとヒントで示し、書いたコードをレビューする。
  - AWS を変えるコマンド(`terraform apply` など): ユーザーがターミナルで打つ。
  - 読むだけの確認と、長い定型のコード: Claude が行う。
  - どれに当たるか迷うときは、ステップの初めに Claude が案を示し、AskUserQuestion で聞く。
- 予想(例: plan で追加・変更される件数)と、ステップの終わりのまとめ(1〜2行)は、Claude が答えを書いて示す。ユーザーに理解確認の質問をしない。AWS を変える操作の前の承認と、設計の選択は聞く。
- 分からないことや、選んでほしいこと(例: 保存期間、名前の付け方)は、文章でなく AskUserQuestion の選択肢で聞く。推奨の案を最初に置く。「OK」で進めるかの確認は、文章でよい。
- 説明は、目的(なぜ必要か)→ たとえ(例: 荷物の追跡スタンプ)→ 実データの1〜2件の例 → コード、の順にする。表と専門用語を最初に並べない。ノートブックは1セル1処理にし、想定の出力をコメント(`# 出力:`)に書く。
- 新しいタスクやステップに着手する前に、コードやコマンドより先に「このタスクは具体的に何をするか」を説明する。順番は、フェーズの説明(全体の中でいまどこか、このフェーズで何を作り、何ができたら終わりか)→ 次のタスクの位置づけ(前後のタスクとのつながり、このタスクで全体の何が進むか)→ なぜ必要か(いまの困りごと)→ たとえ → 具体的にやること(番号付きの手順、変更前と変更後の例)→ 落とし穴(あれば)→ 完了の条件の意味、にする。説明のあと、ユーザーの「OK」を待ってから手を動かす。
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
- terraform/global: アカウント共通のリソース(budgets.tf、github_oidc.tf。状態は S3 の global/terraform.tfstate)
- terraform/modules/lakehouse_env: 環境ごとの定義(s3.tf、glue.tf、athena.tf、iam.tf、bronze.tf、variables.tf)
- terraform/envs/dev: main.tf(provider、backend、モジュールの呼び出し)。test と prod は、フェーズ4で作る
- terraform/backups: 状態ファイルのバックアップ(Git の管理外。アカウント ID が入る)
- simulator: 業務システムの代わり(パイプラインではない)。make_source_events.py(`--table` で表を選び、data/source/<表>/ に届くファイルを1回だけ作る。遅延は orders だけ)、orders_events.py(orders の CSV → 出来事の表)、table_sources.py(ほかの6表の CSV → 届く日を付けた表)
- ingestion: パイプラインの Python。run_ingest.py(`--table` と期間を指定して、届いたファイルを日付ごとに Raw へ書く実行役)、schema.py(registry。7表の列と型・種類・期間。送る側との約束)、ingest_table.py(全表で共通の、読む・検証・型)、orders_checks.py(orders だけの追加の検証)、raw_writer.py(監査カラムと Raw の書き出し)、quarantine.py(IngestStop と隔離の書き出し)、run_log.py(JSON Lines のログと、1日ごとの結果)
- dbt: dbt_project.yml、profiles.yml(バケット名は環境変数 `LAKE_BUCKET`。`--project-dir dbt --profiles-dir dbt` で使う)、models/sources.yml(Bronze)。Silver のモデルは models/silver/ に置く(orders_from_events.sql と .yml がある)
- docs: handoff.md(要件とスコープの原本)、tasks.md(タスクと進捗)
- docs/design: orders-vertical-slice.md(orders のパイプライン設計)、orders-data-profile.md(元データと出来事の作り方)、replay-tables.md(7表のリプレイの仕様)、permissions.md、error-handling.md、secrets.md
- docs/adr: 設計判断の記録(0001〜0011。以降は、判断のたびに足す)
- notebooks: 確認用のノートブック(Git の管理外)
- tests: pytest のテスト(test_orders_events.py、test_source_events.py、test_tables.py の 36 本)。設定は pyproject.toml の `[tool.pytest.ini_options]` と `[tool.ruff]`
- airflow、app、semantic: これから使う

## 決めたこと(要点)
- S3: 環境ごとに1バケット(`ecom-lakehouse-<環境>-<アカウント ID>`)。中を raw/、iceberg/、athena-results/ のプレフィックスで分ける。
- Glue: `ecom_<環境>_bronze` / `silver` / `gold` の3つ。
- Athena: workgroup `ecom-<環境>`、1回のクエリで読める量の上限は 1 GiB。`primary` は使わせない。
- IAM: ロールは `ecom-<環境>-ingest`(raw/ の読み書きだけ)と `ecom-<環境>-transform`。信頼ポリシーは portfolio-admin。reader と deployer は、あとで作る。AWS CLI のプロファイルは `ecom-dev-ingest` と `ecom-dev-transform`。
- Terraform: envs/dev、test、prod を並列に置き、状態は S3 のバックエンド(`use_lockfile`)。環境の定義は terraform/modules/lakehouse_env にまとめた(2026-11-03)。
- Python: uv、Python 3.12(pandas、pyarrow、boto3、pytest、ruff、ipykernel)。
- スコープ: 必須と推奨の要素は、すべて入れる。対象外は、セマンティックレイヤー Lv3、OpenLineage、IaC のセキュリティスキャン、障害注入、複数ステップ分析、専用のデータカタログ、CloudWatch。
- orders のパイプライン(2026-11-03): Raw は出来事を1行ずつ並べた形(ADR 0010)。業務システムの代わり(simulator/)が data/source/ に届いた日ごとの JSON Lines を置き、パイプライン(ingestion/)はそれを検証して Raw に積むだけ。期間は 2016-09-04 〜 2018-10-18 の 775 日。Silver は dbt でイベントから「いまの状態」に畳む(作成中)。詳細は docs/design/orders-vertical-slice.md。
- テーブル定義の管理: Bronze は外部テーブルで Terraform(bronze.tf)、Silver は dbt。理由は ADR 0003 と orders-vertical-slice.md を参照。
- handoff からの順番の変更(2026-10-30): dbt、ruff、pytest をフェーズ2に前倒しする。エラーの設計は Python の取り込みだけにし、dbt の失敗は Airflow の運用で扱う。
- Claude Code の構成(2026-11-02): 絶対に止めることは .claude/settings.json の deny と hook(最後の守りは gitleaks)、いつも守ることは CLAUDE.md、ときどきやる手順は .claude/skills、大きな方針のレビューは .claude/agents/plan-critic に置く。あとで入れるものと入れないものは、tasks.md に書いた。
- シークレット(2026-11-03): 鍵を持たない形(ロールを借りる、OIDC)を第一にする。鍵が要るものは SSM SecureString(`/ecom/<環境>/<用途>`)に置く。詳細は secrets.md を参照。
- モジュール化と OIDC(2026-11-03): モジュールの入力は `env` と `admin_user_name`。アカウントに1つしか持てないもの(OIDC プロバイダ、Budgets)は global に置く。リソースの移動は `moved` で行い、plan を保存して削除 0 件を確かめてから apply する。理由は docs/adr を参照。
- AI エージェント(2026-11-03): 分析エージェント(複数ステップ+pptx)はフェーズ6、運用エージェント(質問応答と診断。読み取り専用、ローカルのみ)は新設のフェーズ9。自動修正の PR は実装しない。どちらも先に設計ステップを置く。細かい仕様は、該当のステップで決める。詳細は handoff §10 と tasks.md を参照。
- Silver の orders(2026-11-03): 名前は `orders_from_events`。dbt の incremental + merge で、窓(`--vars` の start_date / end_date。既定値なし)に届いた注文の全出来事を畳む。`{{ }}` の中に `--` のコメントを書かない(Jinja なので構文エラー)。transform ロールに Glue の版の権限を足した(permissions.md を更新)。
- 使うデータ(2026-11-05): orders、order_items、reviews、customers、sellers、products、translation の7つ。payments と geolocation は使わない。売上は明細の `price + freight_value` で数える(handoff §9)。カテゴリ名は、英訳 → 元の名前 → `unknown` の順で出す(カテゴリが空の商品は売上の約 1.3%)。理由は ADR 0011(1c で書く)。
- ruff と pytest(2026-11-03): ruff は E / F / I の3種類、1行 100 文字。pytest は `tests/` だけを見て、`pythonpath` にプロジェクト直下を足す。Claude が書くコードとテストには、何をしているかを日本語のコメントで残す。
- S3 のバージョニング(2026-11-03): lake バケットで有効。非現行バージョンは 14 日で削除(バケット全体のルール)。Iceberg のスナップショットは「テーブルの履歴」、バージョニングは「ファイルの履歴」で、役割が違う。

- 遅延到着の確認(2026-11-04): 本番の Raw と Silver は上書きしない。遅延ありは別の場所(`raw/olist_late/`、Bronze `orders_events_late`、Silver `orders_from_events_late`)に作り、確認が終われば消す。dbt の変数 `table_suffix: _late` が、読む元と書く先を同時に切り替える。`run_ingest.py` は `--source-dir` と `--raw-dir` で場所を指定できる。設計書は orders-vertical-slice.md を参照。

## 運用メモ
- 元データは data/olist/ にある(Git の管理外)。届くファイルは data/source/、Raw は data/raw/(どちらも Git の管理外。simulator と run_ingest.py で作り直せる)。
- 次にやること、ADR の候補、未解決のことは、docs/tasks.md にまとめた。
