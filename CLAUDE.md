# プロジェクトの引き継ぎメモ(更新: 2026-11-27)

## 目的
データエンジニアのポートフォリオ。EC データ(Olist)を、取り込み → 整形 → 集計 → Streamlit のダッシュボードと AI アナリストまで流す。要件、スコープ、フェーズ計画は docs/handoff.md(原本)を読む。タスク、進捗、現在の状態は docs/tasks.md を読む。

## 技術
S3 + Iceberg + Glue Data Catalog、Athena + dbt-athena、Airflow(ローカルの Docker、フェーズ2)、Terraform、GitHub Actions(OIDC、フェーズ4)、Streamlit + DuckDB、Snowflake 連携(フェーズ8、30日のトライアル)。環境は dev / prod の2つ(test は作らない。2026-11-14)。同じ AWS アカウントで、東京リージョン。

## このリポジトリの進め方
共通の進め方と教え方は、`~/.claude/CLAUDE.md` と `~/Desktop/Project/CLAUDE.md` にある。ここには、このリポジトリだけのことを書く。
- Terraform は、`plan` の内容を読んで説明してから `apply` する。削除(`-`)や置き換え(`-/+`)が出たら、理由を説明する(手順は skill の tf-plan)。
- AWS を変える操作の前は、承認を得る。実行は CLI かコードで行い(再現性と自動化のため)、結果の確認は GUI(マネジメントコンソール)で行う。コマンドごとに、GUI ではどこが変わるかを説明する。Terraform が管理するものは、GUI で変えない。Athena のクエリエディタでの試し書きは、GUI でよい。
- Iceberg の設定は、項目ごとに「何をするか」と「なぜその値か」を説明する(詳しくは .claude/rules/iceberg.md)。
- 大きな方針変更(フェーズの計画、スコープや順番の変更、データが消える恐れのある作業)では、承認の前に、skill の reviewing-plans-with-critic の手順で plan-critic に3回レビューさせる。ふだんの設計書には使わない。
- ユーザーがターミナルでファイルを作るときは `cat > ファイル << 'EOF'`(上書き)を使い、追記(`>>`)には重複防止の確認(`grep -q ... ||`)を付ける。
- docs/ の下の既存ファイルは、差分を示して承認を得てから、変える行だけを書き換える。設計判断は、docs/design と ADR(docs/adr)に残す。
- シェルの変数を使う手順と長いコマンドは、`&&` で1行にまとめ、ユーザーにターミナルへ直接打ってもらう(チャットの `!` 入力は、1回ごとに別のシェルになり、長い行が崩れることもある)。受付番号などは、変数に入れず表示させる。

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
- .claude: settings.json(Git に入る allow / ask / deny と hook の登録)、hooks(guard-bash.sh: 危ない Bash を止める)、skills(session-start、session-end、tf-plan、reviewing-plans-with-critic)、agents(plan-critic、モデルは sonnet)、rules(iceberg.md: Iceberg のファイルを触るときだけ読む)。共通の hook、deny、skill は `~/.claude` にある
- .pre-commit-config.yaml: コミットの前の gitleaks と ruff-check(`--fix` つき。ruff-format は入れない。版は uv.lock と同じ。`uv run pre-commit install` は、マシンごとに1回)
- terraform/bootstrap: 状態ファイル用の S3 バケット
- terraform/global: アカウント共通のリソース(budgets.tf、github_oidc.tf、ci_plan.tf、ci_dbt.tf、prod_boundary.tf、prod_deployer.tf。状態は S3 の global/terraform.tfstate)
- .github/workflows: pr-check.yml(PR のチェック6つ: ruff、pytest、terraform plan の3か所、dbt build)、deploy-prod.yml(main への push で、prod の plan を保存 → `environment: prod` の承認 → 保存した plan だけを `ecom-prod-deployer` で apply。変更がなければ apply は飛ぶ。2026-11-27)
- terraform/modules/lakehouse_env: 環境ごとの定義(s3.tf、glue.tf、athena.tf、iam.tf、bronze.tf、variables.tf。variables.tf に `permissions_boundary` と `transform_oidc_*` を足した。dev は null)
- terraform/envs/dev、terraform/envs/prod: main.tf(provider、backend、モジュールの呼び出し)。prod は dev の写しで、違いは state の key、タグ、`env` の3点(2026-11-25 に作った。状態は S3 の envs/prod/terraform.tfstate)
- terraform/backups: 状態ファイルのバックアップ(Git の管理外。アカウント ID が入る)
- simulator: 業務システムの代わり(パイプラインではない)。make_source_events.py(`--table` で表を選び、data/source/<表>/ に届くファイルを1回だけ作る。遅延は orders だけ)、orders_events.py(orders の CSV → 出来事の表)、table_sources.py(ほかの6表の CSV → 届く日を付けた表)
- ingestion: パイプラインの Python。run_ingest.py(`--table` と期間を指定して、届いたファイルを日付ごとに Raw へ書く実行役)、schema.py(registry。7表の列と型・種類・期間。送る側との約束)、ingest_table.py(全表で共通の、読む・検証・型)、orders_checks.py(orders だけの追加の検証)、raw_writer.py(監査カラムと Raw の書き出し)、quarantine.py(IngestStop と隔離の書き出し)、run_log.py(JSON Lines のログと、1日ごとの結果)、upload_raw.py(`--date` の1日、または `--start` / `--end` の期間の Raw を boto3 で S3 へ上げる。Airflow のコンテナには aws CLI がない)、upload_logs.py(UTC の今日の run_date の取り込みログを S3 の logs/ へ上げる)、clean_logs.py(airflow/logs/ と data/logs/ の 90 日超を消す。既定は一覧だけ、`--delete` で消す)、iceberg_maintenance.py(Silver 7表を1表ずつ ALTER → OPTIMIZE → VACUUM。保存期間 7 日を毎回入れる)、dbt_failures.py(dbt の run_results.json から失敗だけを要約して出す)
- dbt: dbt_project.yml、profiles.yml(接続先は dev、prod、ci(PR チェック用)。`--target prod` で切り替え。バケット名は環境変数 `LAKE_BUCKET`。`--project-dir dbt --profiles-dir dbt` で使う)、models/sources.yml(Bronze 7表)。Silver のモデルは models/silver/ に置く(orders_from_events と6表。6表は macros/silver_latest.sql を呼ぶ)。Gold は models/gold/(dim_date、dim_product、dim_customer、fact_orders、fact_order_items。`table` で毎回作り直し)。置き場所は macros/generate_schema_name.sql(`+schema: gold` が `ecom_<環境>_gold` になる)。2列のキーのテストは tests/generic/unique_combination.sql。Gold の YAML は表ごと(dim_customer.yml など)。tests/ には単発のテスト(gold_amount_reconcile.sql、silver_freshness.sql)。macros/pii_hash.sql は、環境変数 `PII_SALT` が必須(dbt を動かすターミナルでは `LAKE_BUCKET` と一緒に `export` する)
- .github/workflows: pr-check.yml(PR のチェック6つ。上の同名の行と同じ)
- docs: handoff.md(要件とスコープの原本)、tasks.md(タスクと進捗)
- docs/design: gold-design.md(Gold の画面ごとの設計。列、粒度、SCD2)、iceberg-maintenance.md(Iceberg の整理の手順と結果)、orders-vertical-slice.md(orders のパイプライン設計)、orders-data-profile.md(元データと出来事の作り方)、replay-tables.md(7表のリプレイの仕様)、permissions.md、error-handling.md、secrets.md
- docs/adr: 設計判断の記録(0001〜0017。以降は、判断のたびに足す)
- notebooks: 確認用のノートブック(Git の管理外)
- tests: pytest のテスト(test_orders_events.py、test_source_events.py、test_tables.py、test_dbt_failures.py、test_upload_logs.py、test_clean_logs.py、test_iceberg_maintenance.py、test_upload_raw.py の 55 本)。設定は pyproject.toml の `[tool.pytest.ini_options]` と `[tool.ruff]`
- airflow: Dockerfile(公式 3.3.2 に、uv.lock どおりの venv `/opt/project-venv` を足す)、docker-compose.yaml(LocalExecutor + Postgres の5サービス)、.env(Git の管理外。見本は .env.example)、refresh_credentials.sh(dev と prod の ingest / transform、4ロールの一時キーを `~/.ecom-airflow/credentials` に書き出す。Airflow を使う前に毎回打つ。期限は1時間)、dags/(olist_daily.py: 取り込み7表 → S3 → dbt run → dbt test。取り込みの後ろの別枝で、ログを S3 へ上げる upload_logs(失敗しても動く)。olist_backfill.py: 期間の窓の流し直し(手動、リトライ 0。画面で start_date、end_date、env(dev / prod、既定 dev)を渡す。dbt_test は silver_freshness を除外)。iceberg_maintenance.py: Silver の整理(手動、スケジュールなし。新しい DAG は一時停止で作られるので `airflow dags unpause` が要る)。手動実行で target_date を渡す)。compose は、`~/.ecom-airflow` をフォルダごと読み取り専用でコンテナの `/opt/airflow/aws` に見せ、ingestion/・dbt/・data/ も `/opt/project` にマウントする。バケット名は `.env` の `LAKE_BUCKET`(prod は `LAKE_BUCKET_PROD`)。プロジェクト直下の .dockerignore で、ビルドに送るのを pyproject.toml と uv.lock だけにする
- app、semantic: これから使う

## 決めたこと(要点)
- S3: 環境ごとに1バケット(`ecom-lakehouse-<環境>-<アカウント ID>`)。中を raw/、iceberg/、athena-results/ のプレフィックスで分ける。
- Glue: `ecom_<環境>_bronze` / `silver` / `gold` の3つ。
- Athena: workgroup `ecom-<環境>`、1回のクエリで読める量の上限は 1 GiB。`primary` は使わせない。
- IAM: ロールは `ecom-<環境>-ingest`(raw/ の読み書きだけ)と `ecom-<環境>-transform`。信頼ポリシーは portfolio-admin。reader は作らない。deployer は prod 専用の1つで、フェーズ4で作る(2026-11-14)。AWS CLI のプロファイルは `ecom-dev-ingest` と `ecom-dev-transform`。
- Terraform: envs/dev、prod を並列に置き、状態は S3 のバックエンド(`use_lockfile`)。環境の定義は terraform/modules/lakehouse_env にまとめた(2026-11-03)。
- Python: uv、Python 3.12(pandas、pyarrow、boto3、pytest、ruff、ipykernel)。
- スコープ(2026-11-14 に改訂): 必須はすべて入れ、推奨は選んで入れる。対象外は、セマンティックレイヤー Lv3、OpenLineage、IaC のセキュリティスキャン、障害注入、複数ステップ分析、専用のデータカタログ、CloudWatch に加えて、質問ログ、reader ロール、Runbook、為替 API、test 環境。フェーズ8(Snowflake)とフェーズ9(運用エージェント)は、v1.2 の後ろで任意。
- 環境と CI(2026-11-14): 環境は dev と prod の2つ。同じアカウントでは test は名前だけの分離になるため、検証は PR の `ecom_ci`(1つだけ、並行する PR は禁止)と、prod への手動承認(plan の要約を見て承認)に集める。CI のロールは3つ(plan 用、CI の dbt 用、prod の deployer)。dev は手元の portfolio-admin のまま。prod のデータは全期間。理由は、フェーズ4で書く ADR を参照。
- prod と ADR 0016(2026-11-25): 環境は dev と prod の2つで、ADR 0016 が 0001 の「3環境」を置き換えた(「名前で分ける」は有効)。prod は dev と同じモジュールで作った(21 リソース、データは空)。lake バケットの `prevent_destroy` は、モジュールに直接書いたので dev も保護される(`lifecycle` は変数にできないため)。AWS provider の版は、2026-11-26 に dev、prod、global を 6.74.0 にそろえた。
- GitHub Actions の OIDC(2026-11-26): ロール3つは terraform/global に置き(CI が自分の権限を書き換えられないため)、手元の portfolio-admin だけが apply する。`ecom-ci-plan`(読むだけ。plan は `-lock=false`)と `ecom-ci-dbt`(練習用の `ecom_ci_silver` / `ecom_ci_gold`、`iceberg/ci/`、workgroup `ecom-ci` だけに書ける。Bronze は dev を読むだけ)は作成済み。`ecom-prod-deployer` と権限境界 `ecom-prod-boundary` も作成済み(枠は prod の ingest と transform に付く。deployer は枠つきのロールしか作れず、枠と自分自身は変えられない。lake のデータは読み書きできない)。GitHub の Environments `prod` は、承認者が本人、デプロイできる枝は main だけ。信頼ポリシーの `sub` は完全一致で、PR 用(`pull_request`)と prod 用(`environment:prod`)を分け、書き込みのロールに PR 用の `sub` は許可しない。GitHub の `sub` は、名前に加えて変わらない番号(ID)が付く形(`repo:<owner>@<id>/<repo>@<id>:...`)。アカウント ID は GitHub のシークレット `AWS_ACCOUNT_ID` に置く。prod の dbt は `ecom-prod-transform` を OIDC で借りる。IAM の説明欄は英語のみ。ADR 0017、permissions.md。
- orders のパイプライン(2026-11-03): Raw は出来事を1行ずつ並べた形(ADR 0010)。業務システムの代わり(simulator/)が data/source/ に届いた日ごとの JSON Lines を置き、パイプライン(ingestion/)はそれを検証して Raw に積むだけ。期間は 2016-09-04 〜 2018-10-18 の 775 日。Silver は dbt でイベントから「いまの状態」に畳む(作成中)。詳細は docs/design/orders-vertical-slice.md。
- テーブル定義の管理: Bronze は外部テーブルで Terraform(bronze.tf)、Silver は dbt。理由は ADR 0003 と orders-vertical-slice.md を参照。bronze.tf は、7表を `local.bronze_tables` の一覧から for_each で作る(表を足すときは一覧に1件足す。列名は registry と同じ綴り。説明は日本語)(2026-11-07)。
- handoff からの順番の変更(2026-10-30): dbt、ruff、pytest をフェーズ2に前倒しする。エラーの設計は Python の取り込みだけにし、dbt の失敗は Airflow の運用で扱う。
- Claude Code の構成(2026-11-02): 絶対に止めることは .claude/settings.json の deny と hook(最後の守りは gitleaks)、いつも守ることは CLAUDE.md、ときどきやる手順は .claude/skills、大きな方針のレビューは .claude/agents/plan-critic に置く。あとで入れるものと入れないものは、tasks.md に書いた。
- シークレット(2026-11-03): 鍵を持たない形(ロールを借りる、OIDC)を第一にする。鍵が要るものは SSM SecureString(`/ecom/<環境>/<用途>`)に置く。詳細は secrets.md を参照。
- モジュール化と OIDC(2026-11-03): モジュールの入力は `env` と `admin_user_name`。アカウントに1つしか持てないもの(OIDC プロバイダ、Budgets)は global に置く。リソースの移動は `moved` で行い、plan を保存して削除 0 件を確かめてから apply する。理由は docs/adr を参照。
- AI エージェント(2026-11-03): 分析エージェント(複数ステップ+pptx)はフェーズ6、運用エージェント(質問応答と診断。読み取り専用、ローカルのみ)は新設のフェーズ9。自動修正の PR は実装しない。どちらも先に設計ステップを置く(2026-11-14 に見直し: 設計は統合 ADR 1本。分析エージェントの実装と運用エージェントは、v1.2 の後ろで任意)。細かい仕様は、該当のステップで決める。詳細は handoff §10 と tasks.md を参照。
- Silver の orders(2026-11-03): 名前は `orders_from_events`。dbt の incremental + merge で、窓(`--vars` の start_date / end_date。既定値なし)に届いた注文の全出来事を畳む。`{{ }}` の中に `--` のコメントを書かない(Jinja なので構文エラー)。transform ロールに Glue の版の権限を足した(permissions.md を更新)。
- 使うデータ(2026-11-05): orders、order_items、reviews、customers、sellers、products、translation の7つ。payments と geolocation は使わない。売上は明細の `price + freight_value` で数える(handoff §9)。カテゴリ名は、英訳 → 元の名前 → `unknown` の順で出す(カテゴリが空の商品は売上の約 1.3%)。理由は ADR 0011(1c で書く)。
- ruff と pytest(2026-11-03): ruff は E / F / I の3種類、1行 100 文字。pytest は `tests/` だけを見て、`pythonpath` にプロジェクト直下を足す。Claude が書くコードとテストには、何をしているかを日本語のコメントで残す。
- S3 のバージョニング(2026-11-03): lake バケットで有効。非現行バージョンは 14 日で削除(バケット全体のルール)。Iceberg のスナップショットは「テーブルの履歴」、バージョニングは「ファイルの履歴」で、役割が違う。

- 遅延到着の確認(2026-11-04): 本番の Raw と Silver は上書きしない。遅延ありは別の場所(`raw/olist_late/`、Bronze `orders_events_late`、Silver `orders_from_events_late`)に作り、確認が終われば消す。dbt の変数 `table_suffix: _late` が、読む元と書く先を同時に切り替える。`run_ingest.py` は `--source-dir` と `--raw-dir` で場所を指定できる。設計書は orders-vertical-slice.md を参照。
- 6表の Silver(2026-11-07): Silver は staging 寄りで結合しない(結合は Gold)。共通のマクロ `silver_latest` で、キーごとに最後に届いた1行を merge。reviews はレビュー×注文で1行。パーティションなし。詳細は replay-tables.md の「Silver」。
- Airflow(2026-11-07): ローカルの Docker Compose で 3.3.2、LocalExecutor + Postgres(同時の書き込みに強いため。SQLite は試し用)。プロジェクトのライブラリは、Airflow 本体とは別の venv(`/opt/project-venv`)に入れ、版のぶつかりを避ける。AWS へは、手元で借りたロールの一時キーだけを読み取り専用で渡す(ADR 0012)。画面は `127.0.0.1:8080` だけで開く。
- Airflow の運用(2026-11-14): リトライは2回・5分おき(dbt_test だけ 0)。通知は画面とログだけ。ログは取り込みログだけ S3 の logs/ に上げ、Airflow と dbt のログはローカルで 90 日。dbt の失敗は run_results.json の要約をタスクログに出す。
- Iceberg の整理(2026-11-14): Silver の7表を、手動の DAG `iceberg_maintenance` で OPTIMIZE → VACUUM。スナップショットは 7 日残し、設定は毎回 ALTER で入れる。実測: `orders_from_events` の S3 の Parquet が 109 → 25 個、行数と指紋は不変。ADR 0013、手順は docs/design/iceberg-maintenance.md。
- バックフィル(2026-11-14): 手動の DAG `olist_backfill` が、期間の窓(`start_date` と `end_date`)ごとに、取り込み → S3 → dbt run → dbt test を1回ずつ流す。リトライ 0。一時キーの期限(1時間)は、窓を分けて、窓の前に発行し直して対応する(ロールの最長時間は延ばさない)。実測: 30 日の窓が 1 分 40 秒、120 日が 2 分 21 秒(時間の大半は dbt)。全期間の流し直しはしない(Silver は MERGE で冪等。Silver 7表のキーの種類の数が CSV と一致)。ADR 0014。これでフェーズ2は完了。
- Gold(2026-11-14): 事実テーブルは明細(fact_order_items)と注文(fact_orders)の2つ。dim は customer / product / date(sellers は作らない)。SCD2 は購入日時の順から SQL で作り、州と郵便番号の先頭5桁を追う。売上から外す状態は canceled と unavailable(`is_counted`)。作り方は `table` で、過去の数字の固定は、必要になったら月次スナップショット表で補う。ADR 0015、docs/design/gold-design.md。
- PII のハッシュ化(2026-11-15): Gold の customer_unique_id は、salt つき SHA-256(`pii_hash`)。郵便番号は先頭3桁に丸める。salt は環境変数 `PII_SALT`(リポジトリに書かない)。customer_sk は元の ID から作る。生の ID は Silver に残る(Gold を外に見せる口にするため)。限界は、あとで docs/design に書く。
- 鮮度チェック(2026-11-15): `silver_freshness` は、毎日届く3表(orders_from_events、order_items、reviews)だけを見る。`end_date` が渡されないときはスキップ。
- prod のデータ(2026-11-26): dev と同じ全期間を、`olist_backfill` を `env=prod` にして、120 日の窓7回で入れた。dev と差分 0。切り替えは dbt の `--target`、AWS のプロファイル(`ecom-prod-ingest` / `ecom-prod-transform`)、バケット名の3つを `env` に連動させる。`PII_SALT` は dev と同じ値(dev と prod でハッシュが一致する)。`silver_freshness` は毎日の運用用で、過去の窓では誤って失敗するため、backfill の dbt_test では除外する。
- PR チェック(2026-11-27): `pr-check.yml` の6つ(ruff、pytest、plan の global / dev / prod、dbt)。dbt は接続先 `ci` で、dev の Bronze の 2016-09-04〜06 を読み、`ecom_ci_silver` / `ecom_ci_gold` に作る(マスタが 09-04 にしか届かないため、この日を含める。`silver_freshness` は除外)。`ecom_ci` は `concurrency` のグループ `ecom-ci` で1つずつ。plan の `TF_VAR_budget_alert_email` はダミー値。main には ruleset `protect-main`(PR と必須チェック6つ。承認 0、strict なし。Enforcement を Active にしないと効かない)。main へは直接 push できず、docs だけの変更も PR が要る。`ecom-ci-plan` に `iam:ListPolicies`、`iam:ListOpenIDConnectProviders`、lake の `s3:ListBucket` を足した(ListBucket がないと、Terraform は「バケットが消えた」と見なして作り直す plan を出す)。plan のジョブの緑は、`No changes.` を見て初めて意味がある。
- prod のデプロイ(2026-11-27、フェーズ4の完了): `deploy-prod.yml` の plan は `ecom-ci-plan`(信頼ポリシー `ci_plan_trust` に main の `sub` を足した。`ecom-ci-dbt` は PR 用のまま)、apply は `ecom-prod-deployer`(`environment:prod`)。タグ `DeployCheck` で、承認 → 成功まで確かめた。deployer に `s3:ListBucket`(バケットの存在確認)と、条件なしの `iam:TagRole` / `iam:UntagRole` を足した(`iam:PermissionsBoundary` の条件は、タグの操作に効かないため)。次はフェーズ5。PR チェックは、`changes` ジョブの判定で、plan と dbt を変えた場所に関係するときだけ流す(2026-11-27。流さないものは「スキップ」で、必須チェックは満たされる。`pr-check.yml` 自体が変わると全部流す)。

## 運用メモ
- 元データは data/olist/ にある(Git の管理外)。届くファイルは data/source/、Raw は data/raw/(どちらも Git の管理外。simulator と run_ingest.py で作り直せる)。
- 次にやること、ADR の候補、未解決のことは、docs/tasks.md にまとめた。
