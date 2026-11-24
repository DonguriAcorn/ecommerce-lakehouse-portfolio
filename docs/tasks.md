# タスクと進捗

全体の流れと、どこまで済んだかを一覧にする。要件とスコープの原本は [handoff.md](handoff.md)、設計の理由と検証結果は [design/](design/) を見る。

## 使い方

- `[x]` 済み / `[ ]` まだ / `[~]` やらないと決めた(理由を書く)
- 済みの基準: 動作を確認し、コミットと push まで済んだもの。
- 「← 今ここ」は、常に1か所だけ付ける。
- 印: 〔必須〕〔推奨〕は handoff §7 の区分。〔追加〕は handoff §8 に無く、あとから足したもの。
- 遅れたときに後ろへ回す順: 〔後回し候補1〕分析エージェントの実装 → 〔後回し候補2〕パイプライン健康状態ページ → 〔後回し候補3〕dbt docs の公開。必須は落とさない。(質問ログと Runbook は `[~]` にした。2026-11-14)
- スコープの方針(2026-11-14 に改訂): 必須はすべて入れ、推奨は選んで入れる。環境は dev と prod の2つ(test は作らない)。
- README と ADR は、全フェーズで随時書き足す。
- 対象外(バックログ)と、入れないと決めたものは、handoff §7 を参照。
- 更新するのは、セッションの終わり(「ここまでにする」)。下の「現在の状態」と一緒に更新案を示し、承認を得てからコミットする。

## 現在の状態

- 途中経過: フェーズ1は済み。フェーズ2で、dbt の土台(dbt-athena、profiles.yml は環境変数 `LAKE_BUCKET`、dbt debug 済み)を作った。計画を見直し(plan-critic 3回)、orders の Raw をイベント単位にした(ADR 0010)。コードは simulator/(業務システムの代わり。data/source/ に届いた日ごとの JSON Lines を作る)と ingestion/(パイプライン。検証・隔離・型・監査カラムで Raw へ)に分けた。Bronze `orders_events` を Terraform で作り、S3 に 2016-09-04〜2017-10-06 の Raw(398 ファイル、110,739 行)を上げた。見直しで、検証の抜けと空の日の Raw の型のずれを直した(pytest 19 本)。旧版(スナップショット)のコード、ノートブック、AWS の Raw / Bronze / Silver は消した(plan-critic 3回)。2c で、dbt の Silver `ecom_dev_silver.orders_from_events` を作った(3日分 1,308 行、dbt tests 7本 PASS、比較用コピー baseline との差分は業務の8列で双方向 0 件)。確認後に baseline は DROP した。dbt-athena が古い版を整理するため、transform ロールに Glue の `GetTableVersions` / `DeleteTableVersion` を足した(plan は 0 追加・1 変更・0 削除)。2d で、全期間を Raw に上げ(775 ファイル、394,713 行)、Silver を全期間で作った(99,441 行)。元の CSV と注文ごとに突き合わせて、業務の 8 列で差分 0。同じ日と古い日の再実行でも、Silver の指紋は同じ(冪等)。3 で、遅れて届く出来事(5%、3 日遅れ)を別の Raw / Bronze / Silver に流し、遅延なしの Silver と業務の 8 列で差分 0、再実行でも同じ(冪等)を確かめた。dbt は `--vars` の `table_suffix: _late` で、読む Bronze と書く Silver を同時に切り替える。これで orders の縦の1本(フェーズ2の前半)は完成。確認用の遅延ありデータ(Silver / Bronze / S3 / ローカル)は 2026-11-04 に消した。リプレイの共通化は、計画を plan-critic で計6回レビューし、承認済み(2026-11-05)。同じ日に 1a〜5 を進めた。payments は外し、売上は price + freight、カテゴリ名は英訳 → 元の名前 → `unknown` に決めた(カテゴリが空は売上の約 1.3%)。reviews は客が答えた日に届く形に変え、reviews だけ期間を 2018-10-29 まで延ばした(ADR 0011、replay-tables.md)。コードは registry(ingestion/schema.py、7表)と共通の受付(ingest_table.py。orders だけの検証は orders_checks.py)に作り直し、ingest_events.py は消した。pytest 36 本、ruff 0 件。ローカルで6表の Raw を作った(隔離 0 行、金額の合計は CSV と 1 セントまで一致、再実行で差分 0)。orders の Raw は新しいコードで作り直しても全 775 ファイルで差分 0(Bronze / Silver に影響なし)。ログの段階の名前は LOAD / VALIDATE / RUN / WRITE に変え、1日ごとの結果(DAY_RESULT)を足した。2026-11-07 に、6表の Raw を S3 に上げ、リプレイの共通化を終えた。orders の Silver に監査カラム3つ(最後に届いた出来事の値)を足し、業務の8列の指紋は前後で同じ。同じ日に、6表の Bronze を作った(bronze.tf を「表の一覧 + for_each」にし、orders_events は `moved` で移した。説明は日本語。plan は 6 追加・1 変更・0 削除)。Athena で7表を数え、ローカルの Raw と行数・キーの種類の数・列ごとの空でない行の数が一致した。同じ日に、6表の Silver を dbt で作った(共通のマクロ `silver_latest`。キーごとに最後に届いた1行。merge、`full_refresh=false`、パーティションなし、監査カラム3つ)。Silver は staging 寄りで結合しない(結合は Gold)。reviews はレビュー×注文で1行(重複 814 件は、同じレビューが複数の注文に付いたもので中身は同じ)。3日の窓 → 再実行で変化 0 → 全期間の順に流し、dbt tests 48 本 PASS、7表とも Silver と Bronze のキーの種類の数が一致した。同じ日に、Airflow の土台に着手した。AWS への認証は、手元で ingest / transform ロールを借りた一時キーを、コンテナに読み取り専用で渡す方式に決めた(ADR 0012)。ステップ1で、ローカルの Docker Compose に Airflow 3.3.2(LocalExecutor + Postgres、5サービス)を起こし、すべて healthy、コンテナの中の別の venv(`/opt/project-venv`、uv.lock どおり)で dbt-core 1.12.6 / athena 1.11.1 が動くことを確かめた。ステップ2で、一時キーを手元で発行して(refresh_credentials.sh)コンテナへ読み取り専用で渡す形を実装し、2つのロールで get-caller-identity が通ることを確かめた(2026-11-11)。ステップ3で、1日分の DAG olist_daily を作り(取り込み7表 → S3 → dbt run → dbt test)、画面から 2016-09-04 を流して全タスクが成功した(2026-11-11)。ステップ4で、同じ日を CLI でもう1回流し、Silver の指紋(業務の8列)・Silver の行数・Bronze の行数が前後で同じことを確かめた(2026-11-13)。これで「Airflow の土台」は完成。ログは、Airflow のタスクのログが airflow/logs/、取り込みのログが data/logs/、隔離が data/quarantine/、dbt が dbt/logs/ にあり、S3 には上げていない。2026-11-14 に、「Airflow の運用」の1と2を済ませた。運用の決め事(リトライ、通知、ログ、dbt の失敗)を決め、DAG にリトライ(2回・5分おき。dbt_test だけ 0)を入れ、dbt の失敗の要約(ingestion/dbt_failures.py)を作ってログに出した。3 つ目として、取り込みログを S3 の logs/ へ上げる(upload_logs.py と DAG のタスク。2026-11-14)。4 つ目として、ローカルログの掃除(clean_logs.py)。5 つ目として、Iceberg の整理(iceberg_maintenance.py と DAG。ADR 0013)。これで「Airflow の運用」は完成。最後に、全期間のバックフィル(2026-11-14)。`upload_raw` を期間対応にし、DAG `olist_backfill` を作って、30 日と 120 日の窓を流し、どちらも成功した(1 分 40 秒、2 分 21 秒)。全期間は流さず、Silver 7表のキーの種類の数が CSV と一致することを確かめた(ADR 0014)。これでフェーズ2は完了。2026-11-14 に、フェーズ3の「Gold の設計」を済ませた(gold-design.md、ADR 0015)。続けて Gold の5モデル(dim_date、dim_product、dim_customer、fact_orders、fact_order_items)を dbt の table で ecom_dev_gold に作った(2026-11-14)。置き場所は macros/generate_schema_name.sql と dbt_project.yml の gold の設定。売上から外す状態は canceled と unavailable(is_counted 列)、review_score は最後に答えたレビューの星。Athena で、fact_orders 99,441 行(customer_sk の空 0)、fact_order_items 112,650 行、売上の合計 15,843,553.24(数える分 15,735,527.03)が CSV と一致、dim_customer 96,352 行(本人 96,096 人)を確かめた。2026-11-15 に、Gold に meta/tags、表と列の説明、tests 31 本、鮮度チェック、PII のハッシュ化を入れた(フェーズ3のチェック欄を参照)。2026-11-22 に、dev の Gold を本物の salt で作り直し、Gold 5モデルに `contract: enforced` を入れ、用語集(glossary.md の4用語)を書いた。これでフェーズ3は完了。2026-11-25 に、フェーズ4の「pre-commit に ruff を足す」を済ませた(ruff-check のみ。違反を入れて止まることを確認)。同じ日に、ADR 0016「環境は dev と prod の2つ」を書いた(0001 を一部置き換え)。
- 次の1手: フェーズ4(CI/CD)の「prod の環境を作る」。手を動かす前に、このタスクの説明(位置づけ、なぜ必要か。AWS を変える作業なので、plan の読み方も含む)から入る。dbt は `PII_SALT` と `LAKE_BUCKET` の `export` が要る。鮮度テストの Airflow 上の確認は、Airflow を次に起動するときにまとめる(`PII_SALT` は `.env` に足し済みで、compose が渡す)。(手を動かす前に、フェーズの説明と、なぜ必要かから入る)。2026-11-14 にスコープを見直した(残作業は下の「スコープ見直しの残作業」)。バックフィルは、画面で start_date と end_date を渡して DAG `olist_backfill` を流す(1窓は数分。窓の前に一時キーを発行し直す)。新しい DAG は一時停止で作られるので、`airflow dags unpause <DAG名>` が先。ローカルログの掃除は `uv run python -m ingestion.clean_logs`(一覧)と `--delete`(実際に消す)。Airflow を使う前に、`bash airflow/refresh_credentials.sh` で一時キーを発行し直す(期限は1時間。コンテナの再起動は不要)。Airflow の起動は `docker compose -f airflow/docker-compose.yaml up -d --build`(Dockerfile と uv.lock を変えていなければ `--build` は不要)、停止は `down`(`-v` は実行の履歴が消えるので付けない)。`airflow/.env` は deny で Claude が読めないので、作り直しはユーザーが打つ。説明は、書く前に1行ずつ、「書ける / 読める / 流す」の段階を付けて示す。注意: `.venv` が古いパスを指して dbt が動かないときは、`unset VIRTUAL_ENV && rm -rf .venv && uv sync`。terraform は `AWS_PROFILE` を外した管理者の認証で打つ(transform ロールのままだと状態ファイルのロックで 403 になる)。S3 の削除は guard-bash が止めるので、ユーザーがターミナルで打つ。 simulator と ingestion は、プロジェクト直下で `uv run python -m simulator.make_source_events` / `-m ingestion.run_ingest` と実行する(`python simulator/...` は import で失敗する)。full-refresh はしない。dbt を動かすターミナルでは、先に `export LAKE_BUCKET=...` が要る。Claude が dbt や Airflow の実行をしてよいという許可は、次のセッションには引き継がない。

## 未決(着手の前に決める)

- 公開アプリのホスティング先と、export の置き場所(フェーズ5)
- prod に全期間を流す窓の大きさ(フェーズ4で実測して決める。一時キーの期限は1時間)
- 評価セットを測る場所(仮: 手元。フェーズ6の着手時に決める)
- リピート率の分母に `is_counted` を使うか(キャンセルだけの本人を除くか。フェーズ5の画面を作るときに決める。glossary.md は、いまは設計書どおり「注文のある本人」)

決めた(2026-11-14): 月額の上限は 10 ドル(Budgets は済み)。為替 API の取り込みは `[~]`、為替は Gold と画面に入れない。prod のデータは全期間。reviews と sellers は使い、geolocation は使わない(2026-11-05)。 Gold は明細と注文の2つの事実テーブル。SCD2 は購入日時から SQL で作る(ADR 0015)。

## スコープ見直しの残作業(2026-11-14)

tasks.md は更新済み。次は、差分を示して承認を得てから1つずつ直す。

- [x] CLAUDE.md(2026-11-14 に済み): 「環境は dev / test / prod」→ dev / prod、スコープの行を「必須はすべて、推奨は選んで入れる」に、`terraform/envs` の「test と prod は」→「prod は」
- [x] handoff.md(2026-11-14 に済み): §7 の方針、「3環境」と「test へ自動デプロイ」の記述(L25、31、48、64、84、118 付近)、質問ログ・為替 API・reader・Runbook を `[~]` に
- [x] docs/design/permissions.md(2026-11-14 に済み): 「dev / test / prod」、`ecom-dev-deployer` → `ecom-prod-deployer`、reader の行、apply する人の表に `terraform/envs/prod`、plan 用と CI の dbt 用ロールの行
- [x] terraform/modules/lakehouse_env/variables.tf(2026-11-14 に書き換え。validate は下で確認): `contains(["dev", "test", "prod"], …)` → `["dev", "prod"]`(plan は変更 0 件のはず)
- [x] 新しい ADR「3環境から2環境へ」(フェーズ4で書く。0001 は書き換えず置き換える)(2026-11-25: ADR 0016 に書いた)
- [ ] 統合 ADR「エージェントの構想」(フェーズ6で書く)
- [x] ADR 0001 と 0006 に3環境の前提が残っていないか確認する(2026-11-14: 0001 の状態行に「置き換え予定」を追記。0006 の本文は履歴として残し、新しい ADR で扱う)

## フェーズ1: 基盤

完了の目安: dev に空の Iceberg テーブルができ、コスト上限が効いている

- [x] S3(パブリックアクセスのブロック、暗号化、TLS の強制)、Glue の DB 3つ、Athena の workgroup(1 GiB 上限)、ingest / transform ロール
- [x] orders の縦通し(1テーブル、3日分): リプレイ → Raw → Bronze → Silver の MERGE → 再実行の検証
- [x] 権限設計表([permissions.md](design/permissions.md))
- [x] エラーの設計
  - [x] error-handling.md に方針を書く
    - 済み([error-handling.md](design/error-handling.md))。ログは `run_date=` と `batch_id=` で分ける。保存期間は logs/ が 90日、quarantine/ が 30日
  - [x] permissions.md に logs/ と quarantine/ の列を足し、状態を「ingest / transform は実装済み」に直す
  - [x] ingest ロールに logs/ と quarantine/ への書き込みを足す(Terraform)
    - 済み(iam.tf)。ListBucket の prefix に 2つ、PutObject だけのステートメントを1つ足した。plan は 0 add / 1 change / 0 destroy
  - [x] 取り込みに、ログと隔離を入れる(Python の取り込みだけ。dbt の失敗は「Airflow の運用」で扱う)
    - [x] ログの部品: ingestion/run_log.py(JSON Lines)
    - [x] 検証: ingestion/ingest_events.py(停止と隔離の判定)、ingestion/quarantine.py(停止の例外と、隔離の書き出し)
    - [x] ingestion/run_ingest.py に組み込む(実行の始めと終わりのログ、隔離の Parquet を quarantine/ の形で書く、停止は終了コード 1)
      - 済み。実データは隔離0件。隔離と停止の動きは pytest(tests/test_source_events.py)で確かめた
  - [x] ingest ロールで iceberg/ に入れないことを確かめる
    - 済み。raw/ の一覧は成功、iceberg/ への書き込みは AccessDenied(2026-11-01)
- [x] アカウント共通のリソースの置き場所を決める〔追加〕
  - 状態ファイルのキー(案: global/terraform.tfstate)。apply は portfolio-admin(permissions.md に行を足す)。bootstrap には入れない(bootstrap の状態はローカルだけにあるため)
  - 済み。terraform/global/main.tf(キーは global/terraform.tfstate)を作り、init と plan(No changes)を確認。permissions.md に apply する人の節を足した(2026-11-01)
- [x] 月額の上限を決め、AWS Budgets を共通の置き場所に作る〔必須〕
  - 通知先のメールは変数で渡す。.gitignore に `*.tfvars` を足す(`*.tfvars.example` は除く)
  - 済み。月額 10 ドル、実績 50/80/100% でメール通知。通知先は専用アドレスを tfvars に置く(`sensitive = true`)。.claude/settings.json の deny で tfvars と tfstate を読ませない(2026-11-02)
- [x] S3 のライフサイクル: athena-results/、logs/、quarantine/〔必須〕
  - 期限で消すルールは、iceberg/ に掛けない(消すのは Iceberg の expire / vacuum に任せる)
  - 済み(dev のみ)。athena-results/ 7日、logs/ 90日、quarantine/ 30日(2026-11-02)
- [x] Claude Code の構成を整える〔追加〕
  - [x] .claude/settings.json に禁止の設定(秘密のフォルダ、`git add .`、`terraform apply` / `destroy`)を置く(2026-11-02)
  - [x] CLAUDE.md の矛盾を直し、「現在の状態」を tasks.md に移す(2026-11-02)
  - [x] skills: session-start、session-end、tf-plan(2026-11-03 に tf-plan の通しを確認。fmt → validate → plan → 読み解きまで動いた)
  - [x] サブエージェント: plan-critic(2026-11-03。フェーズ2の計画で動作を確認。観点は1体のままで偏りなし。事実確認の調べ先を公式の文書に絞った)
  - [x] 監査(サブエージェント)の指摘を直す: 食い違いの修正、PreToolUse の hook(guard-bash.sh)、gitleaks の pre-commit、allow と ask(2026-11-02)
  - あとで入れる: adr-writer の skill(フェーズ1の最後)/ PostToolUse の自動整形、athena-query と dbt-run の skill、AWS の文書の MCP(フェーズ2)/ dbt-reviewer のサブエージェント(フェーズ3)/ 任意: 学習モードの出力スタイル、GitHub Actions での Claude のレビュー
  - 入れない: AWS API MCP(AWS を変えるのはユーザー)、GitHub MCP(不要)、code-reviewer と security のサブエージェント(組み込みの /code-review と /security-review で足りる)、test-writer(ユーザーが書く方針)、plugins、Sandbox(様子見)
- [x] シークレット管理の方針を、設計書に書く〔必須〕
  - 済み([secrets.md](design/secrets.md))。鍵を持たない形を第一にする。鍵が要るものは SSM SecureString に置く。管理者の鍵は今のままで、SSO は ADR に書く(2026-11-03)
- [x] GitHub の OIDC プロバイダを、共通の置き場所に作る〔必須〕(deployer ロールはフェーズ4)
  - 済み(terraform/global/github_oidc.tf)。url と client_id_list の2項目だけ。plan は 1 add、apply 後に CLI で確認(2026-11-03)
- [x] モジュール化(完了: `moved` ブロックを使い、plan の置き換えが0件、削除が0件)
  - 済み。入力は `env` と `admin_user_name`。dev の 14 件を移動し、apply 後も `No changes`。`moved.tf` は消した。状態のバックアップは terraform/backups/(Git の管理外)。prod の作成はフェーズ4(下記。test は 2026-11-14 に作らないと決めた)(2026-11-03)
- [x] ADR を書く
  - 済み。0001〜0009(環境の分け方、SSO 後回し、テーブル定義、Raw の形、ログ、S3 の構成、Airflow、データカタログ、AI 開発の構成)(2026-11-03)
  - 候補: Bronze を外部テーブルにした理由、Raw の段階で型を付けた Parquet にした簡略化、エラーのログを S3 に JSON Lines で残す理由、Silver の定義を Terraform ではなく SQL(のちに dbt)で持つ理由、Airflow を選んだ理由、S3 の構成、環境の分け方とアカウント分離、スイッチロールを後回しにした理由、管理者を IAM ユーザーのままにし SSO を後回しにした理由、専用のデータカタログを使わない理由、AI 開発の構成(禁止の設定、CLAUDE.md、skills、サブエージェントの使い分け)

## フェーズ2: 取り込み

完了の目安: 全テーブル・全期間を Airflow で流し、指定した3日を再実行して、全 Silver の差分が 0

- [x] ruff と pytest を始める〔推奨。handoff ではフェーズ4。前倒し〕(2026-11-03: `uv run ruff check` は指摘 0 件、`uv run pytest` は 2 passed)
- [x] lake バケットの S3 バージョニング〔追加〕(2026-11-03: dev に有効化。非現行バージョンは 14 日で削除。バケット全体にかかるルール `expire-noncurrent-versions` を足した。plan は 1 追加・1 変更・0 削除。prod はフェーズ4で作るときに、モジュールを通して同じ設定になる)
- [x] orders の Raw をイベント単位にする〔追加。ADR 0010。リプレイの共通化の前に行う〕
  - 計画: plan-critic の3回レビュー済み(2026-11-03)。Silver は dbt で作り直す。`ingest_date` は「届いた日」。旧版(スナップショット)の Raw / Bronze / Silver と `sql/silver/` は消した(2026-11-03。plan-critic の3回レビュー済み。比較用コピー `orders_baseline_20261103` は、2c で差分 0 を確かめて DROP した)。
  - [x] 2a 設計と Python: ADR 0010。`simulator/`(送る側。CSV → `data/source/` の JSON Lines、`arrival_date` ごと)と `ingestion/`(パイプライン。届いたファイル → 検証・隔離 → Raw)に分けた。旧版のコードとノートブックは消し、docs/design を今の形に書き直した。見直しで、検証の抜け(順位・印・空の順位)と、空の日の Raw の型のずれを直した(2026-11-03: pytest 19 passed、ruff 0 件。ソースと Raw は全期間 394,713 件・775 日。Raw は全ファイルで型が1種類)
  - [x] 2b Terraform: Bronze `orders_events`(plan を保存、追加のみ・削除 0 を確認、apply はユーザー)(2026-11-03: apply 済み。S3 に 2016-09-04〜2017-10-06 の 398 ファイル、Bronze で 110,739 行を確認。型を直した Raw で上げ直し済み。残りの日は 2d で上げる)
  - [x] 2c dbt: `sources.yml` を `orders_events` に直し、Silver `orders_from_events` を作った。incremental + merge、購入月のパーティション、`full_refresh=false`、新しい日だけ通すガード、dbt tests 7本(2026-11-03: 3日分で 1,308 行、tests PASS、baseline と業務の8列で差分 0。確認後に baseline を DROP した)
  - [x] 2d 全期間の検証: 元の CSV との突き合わせ。同じ日の再実行と、古い日の再実行で変わらない(2026-11-04: 残りの日を Raw に上げ、S3 は 775 ファイル、Bronze は 394,713 行・99,441 注文。全期間を 1 つの窓で流し、Silver は 99,441 行。CSV と注文ごとに突き合わせて、業務の 8 列すべてで差分 0。2018-10 と 2016-10 を再実行しても、Silver 全体の MD5 の指紋が同じ。窓は、Raw が 36 MB で 1 GiB の上限に収まるため、月ごとに分けず全期間 1 回で足りた)
  - [x] 3 遅延到着(simulator の `--late-share` と `--late-days`。決定的に選ぶ)、スキャン量(2026-11-04: 出来事の 5%=19,634 件を 3 日遅らせたソースを `data/source_late/` に作り、別の Raw(`raw/olist_late/`)・別の Bronze(`orders_events_late`、Terraform。plan は 1 追加)・別の Silver(`orders_from_events_late`)に流した。月ごと 26 窓を古い順に流し、`dbt test` は 7 本 PASS。遅延なしの Silver と業務の 8 列で双方向 0 件(99,441 行)。3 窓を流し直しても全列の指紋は同じ(冪等)。スキャン量は dbt のクエリが 1 つあたり最大 30.3 MiB(直近 50 件の履歴のうち 13 件。上限 1 GiB の約 3%)。確認用の Silver / Bronze / S3 / ローカルのデータは、2026-11-04 に消した。Bronze は Terraform の plan が 0 追加・0 変更・1 削除)
- [x] orders の Silver を dbt に移す〔追加。handoff ではフェーズ3。前倒し〕(上のイベント化の 2c に統合。2026-11-03: 済み。比較の SQL で差分 0)
  - 注意: 比較用のコピー(`orders_baseline_20261103`)は DROP 済み。full-refresh はしない(Athena で Iceberg のテーブルを DROP すると、データも消える)。dbt の置き場所は iceberg/ に固定する(athena-results/ はライフサイクルで消える)
  - 完了: 比較の SQL で差分が 0
- [x] リプレイを、どのテーブルにも使える形にする(Python。simulator と ingestion の両方。テーブルごとの日付の規則を持つ。イベント型にするかスナップショット型にするかを、テーブルごとに決める。pytest 付き)〔必須〕(案: 他のテーブルも `raw/olist/<テーブル>/` に置き、simulator → ingestion を通す。日付で動かないマスタは、最初の日に1回だけ届く形も選択肢)(2026-11-07: 6表の Raw を S3 の `raw/olist/<表>/` に sync。ファイル数は S3 とローカルで一致(order_items 775、reviews 786、マスタ4表は各1)。orders の S3 は 775 ファイルのまま、更新日も変わらず)
  - 計画(2026-11-05 承認。plan-critic 計6回): 実務に近い BI から逆算し、担当者を事業責任者・営業(出品者の管理)・物流 CS の3人にした。使うのは orders、order_items、reviews、customers、sellers、products、translation の7つ。payments と geolocation は使わない(要るときは registry に1行足す)。
  - 届く日: order_items は親の注文の購入日、reviews は max(客が答えた日, 購入日)(2026-11-05 に変更。reviews だけ期間の最後は 2018-10-29)、customers・sellers・products・translation は 2016-09-04 に全件1回。追記型は空の日も空ファイル。registry に expected(table, date)、型、PII の候補の印を持つ。ログは健康状態ページ用の項目を全テーブル共通で書く。元 CSV との行数照合はしない。
  - 進め方: 1a 測定 → 1b 文書の差分(handoff §9 の売上を price + freight に → tasks.md → CLAUDE.md)→ 1c ADR 0011 と設計書 → 2 registry と order_items → 3 reviews → 4 sellers → 5 customers・products・translation → 6 S3 へ sync と orders の不変の確認
  - 進み具合: 1a〜5 済み(2026-11-05)。6 済み(2026-11-07)
- [x] 監査カラム(`_ingested_at`、`_source_file`、`_batch_id`)を、Raw と Silver の全テーブルに〔推奨〕(2026-11-07: Raw は7表とも付いていた。orders の Silver に、最後に届いた出来事の値を `max_by(…, ingest_date)` で足した。silver 全体に `on_schema_change: append_new_columns`。全 99,441 行を埋め、業務の8列の指紋は前後で同じ、Bronze との突き合わせで差分 0、dbt tests 10本 PASS、再実行は OK 0。6表の Silver は、次のタスクで最初から3列を持たせる)
- [x] 全テーブルの Bronze(Terraform)と Silver(dbt)〔必須〕(2026-11-07: 7表とも Silver と Bronze のキーの種類の数が一致。dbt tests 48 本 PASS、再実行で変化 0)
  - 対象: orders、order_items、reviews、customers、sellers、products、product_category_name_translation の7つ(payments と geolocation は使わない。2026-11-05)
  - Bronze: 済み(2026-11-07。bronze.tf の一覧 + for_each で7表。Athena とローカルの Raw で、行数・キーの種類の数・列ごとの空でない行の数が一致)。Silver: 済み(2026-11-07。macros/silver_latest.sql で6表。設計は replay-tables.md の「Silver」)
  - 完了: 全テーブルが Bronze と Silver にある。件数は、キーの種類の数で照合する
- [x] Airflow の土台(ローカルの Docker Compose、1日分の DAG、冪等)〔必須〕(2026-11-13 に済み。同じ日を2回流して、Silver の指紋・行数が同じ)
  - 進め方: 1 Docker Compose で起動 → 2 一時キーのスクリプトとマウント(ADR 0012)→ 3 1日分の DAG(取り込み 7表 → その日の Raw を S3 へ → dbt run → dbt test)→ 4 冪等の確認と文書
  - 進み具合: 1 済み(2026-11-07。Airflow 3.3.2、LocalExecutor + Postgres。版は、前日に出た 3.4.0 を避けた。認証方式は ADR 0012 で決定)。2 済み(2026-11-11。`airflow/refresh_credentials.sh` が `~/.ecom-airflow/credentials` に2ロールの一時キーを書き出し、compose がフォルダごと読み取り専用でマウント。コンテナの中から ingest / transform の get-caller-identity が通ることを確認)
  - 3 済み(2026-11-11。DAG `olist_daily`(airflow/dags/olist_daily.py)。手動実行で `target_date` を渡し、取り込み 7表(同時)→ upload_raw(ingestion/upload_raw.py。boto3、ingest ロール、同じキーを上書き)→ dbt run → dbt test。2016-09-04 で全タスク成功(dbt run PASS=7、dbt test PASS=58)。compose に ingestion/・dbt/・data/ のマウントと LAKE_BUCKET を足した)
  - 4 済み(2026-11-13。同じ日(2016-09-04)を2回流して冪等を確認。1回目は画面(2026-11-11)、2回目は CLI(`airflow dags trigger olist_daily --conf '{"target_date": "2016-09-04"}'`、全10タスク success、約90秒)。2回目の前後で、orders の Silver の指紋(業務の8列を `|` でつないだ全行の checksum)`D021FB02FF4384F1`、Silver の行数 99,441、2016-09-04 の Bronze 行数 1 が同じ。1回目の実行の直後には記録を取っていない。ログは、Airflow のタスクのログが `airflow/logs/`、取り込みのログが `data/logs/`、隔離が `data/quarantine/`、dbt が `dbt/logs/`(S3 には上げていない。保持期間と dbt の失敗の残し方は「Airflow の運用」で決める))
- [x] Airflow の運用(リトライ、失敗の通知、dbt の失敗を logs/ に残す、Iceberg の OPTIMIZE / VACUUM)〔必須〕(2026-11-14 に済み)
  - 決めたこと(2026-11-14): リトライは2回・5分おき(dbt_test だけ 0。不合格はやり直しても直らない)。失敗の通知は画面とログだけ。ログは、独自の取り込みログだけ S3 の logs/ に上げ(90日)、Airflow と dbt のログはローカルで 90日。dbt の失敗は run_results.json の要約をタスクログに出す
  - 進め方: 1 リトライ → 2 dbt の失敗の要約 → 3 取り込みログを S3 へ → 4 ローカルログの掃除(90日)→ 5 Iceberg の OPTIMIZE / VACUUM
  - 進み具合: 1 済み(2026-11-14。`default_args` で retries=2・retry_delay=5分、dbt_test だけ retries=0。コンテナ内で DagBag を読み、全タスクの値を確認)。2 済み(2026-11-14。ingestion/dbt_failures.py が run_results.json から失敗だけを1行ずつ出し、DAG の `dbt_with_summary` が「dbt を流す → 終了コードを保存 → 要約 → 保存した終了コードで終了」の形でつなぐ。pytest 39 本。わざと不合格にしたテストで、ログの末尾に要約が出て、dbt_test は attempt=1 で failed を確認。一時のテストは消した)。3 済み(2026-11-14。ingestion/upload_logs.py が、run_date が UTC の今日のログを S3 の `logs/` へ上げる。DAG のタスク `upload_logs` は ingest ロール、`trigger_rule=all_done`、取り込みの後ろの別枝(dbt は止めない)。pytest 42 本。2016-09-04 を流して全 11 タスク success、S3 に 7 表ぶんの `events.jsonl`。単独で上げ直しても 7 ファイルのまま。S3 の 90 日の期限は s3.tf の `expire-logs` で、すでにある)。4 済み(2026-11-14。ingestion/clean_logs.py。最終更新から 90 日を過ぎたファイルを消す。既定は一覧だけで、`--delete` を付けたときだけ消す。対象は airflow/logs/ と data/logs/(S3 に控えがあるため)。dbt/logs/ は dbt.log が追記され続けて最終更新が毎回新しくなるので対象外。DAG には入れず、手動で打つ形。pytest 46 本。実データの一覧は 90 日超 0 件、削除は未実行)。5 済み(2026-11-14。`orders_from_events` で OPTIMIZE → VACUUM を試し、S3 の Parquet が 109 → 25 個、スナップショットが 9 → 1 個、行数 99,441 と業務の8列の指紋 `2DDE47A22018FB6F` は前後で同じ。保存期間は 7 日(`vacuum_max_snapshot_age_seconds`)。ingestion/iceberg_maintenance.py と DAG `iceberg_maintenance`(手動、リトライ 0、7表を1表ずつ。保存期間は毎回 ALTER で入れる)を作り、7表すべてで success。pytest 49 本。判断は ADR 0013、手順は docs/design/iceberg-maintenance.md。`order_items` と `reviews` の 11-07 の版は 7 日に届かず残ったので、後日の流し直しで消える見込み(未確認)。新しい DAG は一時停止で作られるので、`airflow dags unpause` が要る)
- [x] 全期間のバックフィルを、Airflow で行う〔必須〕(期間を指定して、まとめて MERGE する。完了: 全期間で、キーの種類の数が元データと一致)(2026-11-14: `upload_raw` を期間対応にし、DAG `olist_backfill`(窓ごとに 取り込み → S3 → dbt run → dbt test。リトライ 0)を作った。30 日の窓は 1 分 40 秒、120 日の窓は 2 分 21 秒で、どちらも成功。時間の大半は dbt で、窓を 4 倍にしても全体は約 1.4 倍。全期間は流さない: データは Raw / Silver に全期間入っていて、MERGE は冪等なため。Silver 7表の行数とキーの種類の数が CSV と一致(Athena で確認)。中身の指紋の比較と、データが多い時期の窓の実測はしていない。ADR 0014。pytest 55 本)
- [x] Olist のリプレイ〔必須〕(総まとめ。2026-11-07 に7表とも済み)
- [x] S3 Raw〔必須〕(総まとめ。同上)
- [x] Silver の MERGE〔必須〕(総まとめ。同上)

## フェーズ3: モデリング

完了の目安: `dbt build` がすべて通る

進め方(2026-11-14 に見直し): YAML を2回書かないため、Gold の設計 → Gold と、meta/tags・Lv1・tests を同時に書く。

- [x] Gold の設計: 最終の画面から逆算して、各データソースの出力先を決める〔追加〕(Gold のスター型より先。ダッシュボードの画面ごとに、必要な元データと列を書き出す。為替は入れない。Gold の粒度と SCD2 の作り方もここで決める。結果は docs/design に1枚、判断は ADR 1本)(2026-11-14: 事実テーブルは fact_order_items と fact_orders の2つ。dim は customer / product / date で、sellers は作らない。SCD2 は購入日時の順から SQL で作り、州と郵便番号の先頭5桁を追う(実データの変化は 39 人と 250 人)。健康状態の画面は Gold の対象外。docs/design/gold-design.md、ADR 0015)
- [x] Gold のスター型(fact_orders、dim_customer、dim_product、dim_date)〔必須〕(上の設計で決めた列で作る。2つ目以降のモデルは「すでにある形の繰り返し」)(2026-11-14: 5モデルを dbt の table で ecom_dev_gold に作った。fact_orders 99,441 行、fact_order_items 112,650 行、売上の合計は CSV と一致。画面と指標は is_counted で絞る)
- [x] dbt の meta / tags〔推奨・縮める〕(モデルは owner と update_frequency、列は pii だけ。Gold と同じ YAML に同時に書く。PII のハッシュ化と除外一覧の元になる)(2026-11-15: 5モデルに owner=data-eng・update_frequency=daily・tags を付け、pii: true を3列に付けた。YAML は表ごとの5ファイル。tags は `config:` の下に書く)
- [x] セマンティックレイヤー Lv1〔必須・縮める〕(Gold と同じ YAML に、テーブルとカラムの説明。Silver は主要列だけ)(2026-11-15: Gold 5モデルの表の説明と全 37 列の説明を、manifest で確認)
- [x] SCD Type 2〔必須〕(dim_customer。customers は1回しか届かないため、作り方は「Gold の設計」で決める。dbt-athena の snapshot が Iceberg で動くかは、着手時に公式文書で確かめる)(2026-11-14: dim_customer を、購入日時の順から SQL で作った。96,352 行、本人 96,096 人。引っ越した本人は PR → SC の2行になった。dbt snapshot は使わない。ADR 0015)
- [x] dbt tests〔必須・縮める〕(Silver に 48 本ある。Gold に unique / not_null / relationships / accepted_values と、金額の突き合わせ 1 本を足す)(2026-11-15: Gold に 31 本が PASS。単発テスト gold_amount_reconcile で、注文と明細の売上の合計が一致。「わざとずらして FAIL する」確認はしていない)
- [x] 鮮度チェック〔必須・縮める〕(dbt の `source freshness` は今の時刻と比べるため使わない。`max(_ingest_date)` と Airflow の target_date を比べる singular test)(2026-11-15: tests/silver_freshness.sql。毎日届く3表の max(_last_ingest_date) が end_date 以上かを見る。end_date なしは 0 行で PASS。2016-09-04 で PASS、2030-01-01 で FAIL 3、変数なしで PASS を確認。Airflow での確認は未実施)
- [x] PII のハッシュ化〔推奨・縮める〕(1〜2 列、マクロ1つ。Olist はもともと匿名なので、仕組みを示す程度)(2026-11-15: macros/pii_hash.sql。dim_customer と fact_orders の customer_unique_id をハッシュに、郵便番号を先頭3桁に。dev の Gold を使い捨ての salt で作り直し、tests 31 本 PASS。2026-11-22: 本物の salt に切り替えて Gold を作り直し、tests 31 本 PASS。compose が `.env` の `PII_SALT` をコンテナに渡す。限界は docs/design/pii-hashing.md)
- [x] データコントラクト〔推奨・縮める〕(Gold の型を `contract: enforced` で固定する。dbt-athena + Iceberg + incremental で使えるかは着手時に確かめ、動かなければ後ろへ)(2026-11-22: Gold 5モデルに `contract: enforced` と全列の `data_type` を付けた。dbt build 36 本 PASS。型がずれると、`dbt run` / `dbt build` の run の段階で、表を作る前に止まる(fact_orders の review_score をわざとずらして確認し、元に戻した)。`dbt test` 単独では検知しない。型は Athena が報告する型で書く(文字列は varchar、int は integer、`sequence` と `unnest` で作った date は timestamp)。契約は名前・順番・型の事前検査だけで、制約(not null など)は効かない。中身は従来どおり data_tests で守る)
- [x] 用語集〔推奨・縮める〕(GMV、リピート率など。`{% docs %}` の1ページ。dbt docs に出る)(2026-11-22: dbt/models/gold/glossary.md に4用語(gmv、repeat_rate、order_count、avg_order_amount)。fact_order_items.item_amount、fact_orders の order_id・order_amount・customer_unique_id の説明の末尾から `{{ doc() }}` でつなぎ、dbt parse と docs generate が通り、manifest で展開を確認。リピート率の分母に `is_counted` を使うかは決めていない(フェーズ5で決める))

## フェーズ4: CI/CD

完了の目安: PR で ruff・pytest・plan・`ecom_ci` での `dbt build` が動き、main へのマージのあと、手動承認を経て prod にデプロイされる(環境は dev と prod の2つ。test は作らない)

- [x] pre-commit に ruff を足す〔推奨・縮める〕(gitleaks の pre-commit だけは、フェーズ1に前倒しした。sqlfluff は v1.2 の後ろ)(2026-11-25: `.pre-commit-config.yaml` に ruff-check を `--fix` つきで足した。版は uv.lock と同じ v0.17.2。ruff-format は入れない(既存コードの一括書き換えを避ける)。全ファイルで Passed。使っていない import を入れた一時ファイルで Failed と自動修正を確認し、一時ファイルは消した)
- [x] ADR「3環境から2環境へ」〔追加〕(0001 は書き換えず、置き換える。理由: 同じアカウントでは test は名前だけの分離。代わりの検証は PR の `ecom_ci`、plan を読んでの承認、ブランチ保護。失うもの、残るリスク、将来の乗り換え(アカウント分離、staging)も書く)(2026-11-25: ADR 0016 に書いた。0001 は状態の行だけを「一部が置き換えられた」に変え、0016 へリンクした。決めたこと5つ、あきらめたこと4つ)
- [ ] prod の環境を作る(フェーズ1のモジュールを使う。`prevent_destroy` を付ける)〔必須〕 ← 今ここ
- [ ] prod に全期間のデータを入れる〔追加〕(窓を分けて流し、窓の前に一時キーを発行し直す。窓の大きさは実測で決める。prod 用のロールとプロファイルの切り替えを決める)
- [ ] GitHub Actions から OIDC で接続: ロール3つ〔必須〕(dev は手元の portfolio-admin のまま)
  - plan 用: 状態ファイルと Describe / Get の読み取りだけ(PR 用の `sub`)
  - CI の dbt 用: `ecom_ci` の Glue DB と `iceberg/ci/` だけに書ける。Bronze は dev を読むだけ(PR 用の `sub`)
  - prod の deployer: OIDC の `sub` に GitHub Environments の `prod` を入れる。IAM は `ecom-prod-*` だけ。書き込み系のロールに PR 用の `sub` は許可しない
- [ ] PR チェック(ruff、pytest、`terraform plan`、`ecom_ci` での `dbt build`)〔必須〕(`ecom_ci` は1つだけで、並行する PR は禁止。固定の小さなデータで流す。ブランチ保護で PR チェックを必須にする)
- [ ] main へのマージで、手動承認のあと prod にデプロイ(GitHub Environments。承認画面に plan の要約を出し、保存した plan だけを apply する。dev への自動デプロイはしない)〔必須〕

## フェーズ5: アプリ(v1.0)

完了の目安: 公開 URL で見られる

- [ ] 前提: Olist のライセンスを確認する〔必須〕
- [ ] Gold の Parquet export と、置き場所・アプリへの渡し方の設計〔必須。設計は ADR 1本にまとめた〕
- [~] reader ロール(アプリは Parquet を読むだけで AWS に接続しないため v1.0 では使い道がない。要るときはフェーズ9で足す。2026-11-14)
- [ ] セマンティックレイヤー Lv2(semantic/metrics.yml。指標 4〜5 個。ダッシュボードと AI が同じ読み込み関数を使う)〔必須〕
- [ ] Streamlit のダッシュボード(売上 KPI、期間比較、リピート率、商品ランキング)〔必須〕
- [ ] パイプライン健康状態ページ〔推奨・縮める〕〔後回し候補2〕(export のときに status.json を1つ出して表示するだけ)
- [ ] README の最小版〔必須〕
- [ ] v1.0 のタグを付けて公開する

## フェーズ6: AI(v1.1)

完了の目安: 評価セットの正答率(手元で測定)を README に載せられる。CI で走らせるのは、ガードレールの単体テストだけ

- [ ] 前提: 使う LLM と予算を決める(CI で評価する費用も含む)
- [ ] ガードレール(SELECT のみ、Gold のみ、LIMIT、PII カラムの除外、sqlglot)〔必須〕
- [ ] 悪用対策(閲覧者のキー入力か、回数の制限)〔必須〕
- [ ] AI アナリスト(質問 → SQL → 検証 → 実行 → 表・グラフ・要約)〔推奨〕
- [ ] エージェントの構想 ADR〔追加・推奨・縮める〕(分析エージェントと運用エージェントを1本にまとめる。役割、入力、出力、使うツール、止める条件を短く書く。運用エージェントの③自動修正を実装しない理由も、1段落で書く)
- [ ] PII の除外の一覧を、pii フラグから自動で作る〔推奨〕(manifest.json を読むだけ。手書きだと定義がずれるため残す)
- [ ] 評価セット(20 問)と、手元での測定〔推奨・縮める〕(仮。測る場所はフェーズ6の着手時に決める。実 LLM のキーを GitHub に置かない)
- [~] 質問ログ(handoff §10 の「Iceberg に貯める」は、§4 の「公開アプリに AWS の認証情報を持たせない」と両立しない。理由は README の「やらないこと」に書く。2026-11-14)
- [ ] v1.1 のタグ
- [ ] 分析エージェントの実装(複数ステップ+Streamlit 表示+pptx のダウンロード)〔追加・推奨〕〔後回し候補1〕(v1.2 の後ろ。任意)

## フェーズ7: 仕上げ(v1.2)

完了の目安: 第三者が README だけで再現できる(新しく clone した環境で確かめる)

- [x] Iceberg の運用の調整とデモ(compaction、スナップショットの削除)〔推奨〕(フェーズ2で済み。ADR 0013 と iceberg-maintenance.md に実測まである。README からリンクする。2026-11-14)
- [ ] スキーマ進化のデモ〔推奨〕(Raw に列を足し、`on_schema_change: append_new_columns` で Silver に届くのを確かめる。型の変更と列の削除は扱わないと書く)
- [ ] dbt docs の公開〔推奨〕〔後回し候補3〕(main のデプロイの workflow から GitHub Pages へ。系統図が見える)
- [~] Runbook(error-handling.md、iceberg-maintenance.md、ADR 0014 に手順がすでにある。README の「運用」節からリンクする。2026-11-14)
- [ ] 月次のコストを記載する〔推奨〕(Cost Explorer の実数を5行ほど)
- [ ] README を作り込む〔必須〕(最小版は v1.0 で出す。システム図: README の中は Mermaid か SVG、詳しい図は HTML のページにしてリンクする)
- [ ] README に「やらないこと」を、理由つきで書く〔必須に格上げ〕(今回 `[~]` や後ろへ回したもの、test 環境、質問ログ、為替 API、reader、Runbook、Snowflake も載せる)
- [ ] README に「本番ならこうする」を10行ほど書く〔推奨〕(社内展開の ADR の代わり。アカウント分離、staging、SSO)
- [ ] v1.2 のタグ

## フェーズ8: Snowflake 連携(v1.2 の後ろ。任意)

時間があれば最小版(読めた + 1クエリの結果が一致 + スクリーンショット)だけ。実行時間と課金の比較は削ってよい。

完了の目安: 同じ SQL が両方のエンジンで同じ結果になり、比較表が README にある

- [ ] フェーズ7の完了後に、トライアルを申し込む(30 日以内に終える)
- [ ] Glue カタログ連携で、Iceberg のテーブルを Snowflake から読む(読み取りだけ)
- [ ] 同じ集計 SQL を Athena と Snowflake で実行し、結果が一致することを確かめるテスト
- [ ] 実行時間・課金・使い勝手の比較を、ADR と README に書く(スクリーンショットも残す)

## フェーズ9: 運用エージェント(v1.2 の後ろ。任意)

設計は、フェーズ6の統合 ADR「エージェントの構想」に含める。下の項目は、実装するときだけ使う。

完了の目安: 失敗ログを渡すと、原因と直し方を説明できる(ローカルのみ)

- [ ] 前提: 診断するログの出どころを決める(Airflow のログを S3 に出すか)
- [ ] 運用エージェントの設計〔追加〕(フェーズ6の統合 ADR に1段落。実装するときに、docs/design に、役割、読むもの、答え方、使うツール、権限、3段階の線引きを書く)
- [ ] 読み取り専用の ops-reader ロールを permissions.md に足す
- [ ] マスク層(AWS 由来の文字列を LLM に渡す前に隠す)
- [ ] ①質問応答(リポジトリ、docs、dbt の定義、logs/)
- [ ] ②診断(失敗ログ → 原因と直し方)
- [ ] ③自動修正の PR の設計を ADR に書く(実装しない)
- [ ] v1.3 のタグ

## 着手時メモ

計画の批評で出た細かい注意。着手するときに設計書へ移し、ここから消す。

- dbt への移行: 「古い日付では上書きしない」条件の再現。`profiles.yml` は `env_var` を使い、アカウント ID を書かない。`s3_data_dir` / `s3_data_naming` / `on_schema_change` を決める。transform ロールの権限(dbt の一時テーブル)。実行はローカルの uv で `AWS_PROFILE=ecom-dev-transform`。check_orders_rerun.sql は、dbt の test か analyses へ移す。
- テーブルの型と主キー:
  - 明細の型(orders の日付に従う): order_items `(order_id, order_item_id)`、customers `customer_id`
  - 独自の日付: reviews `(review_id, order_id)`(review_id に重複があり、コメントに改行を含む)
  - マスタの型(日付なし): sellers、products、product_category_name_translation
  - customer_unique_id ごとに住所が変わったものが 252 件ある(SCD2 の材料)
- Airflow: dbt は Airflow と別の venv で動かす。`_batch_id` に Airflow の run_id を渡す。メモリは約 4GB が必要。通知先はシークレットとして扱う。dbt の失敗は、`run_results.json` の要点を logs/ に書く(そのときに、transform ロールへ logs/ の書き込みを足す)。
- CI 専用のロール: `ecom_ci` の Glue DB(1つだけ)と `iceberg/ci/` だけに書ける。Bronze は dev を読むだけ。`iceberg/ci/` のライフサイクル(例: 3日)で S3 の実データを消す。dbt の `generate_schema_name` と sources.yml の切り替えが要るかは、着手時に確かめる。
- sqlfluff: テンプレーターは jinja にして、Athena に接続しない。
- export: 公開アプリに AWS の認証情報を持たせない(案: Git の例外のパス、GitHub Releases、ビルド時に取得)。書き出すロール、permissions.md の `export/` 列、ライフサイクルも決める。健康状態ページは、export のときに状態の要約も出す。
- AI エージェント(2026-11-03、plan-critic 2回。3回目は未実施): 運用②の評価データ(合成ログかマスク済みの実ログか。保存前にマスクを通す)/ 実 LLM の評価をどこで回すか(手元か main の週次 CI。作者のキーを GitHub に置かない)/ マスクは AWS 由来の文字列だけにかけ、切り詰めの前に適用する(アナリストの数字は壊さない)/ ops-reader は読むプレフィックスを列挙し、Athena の専用 workgroup に合計スキャン上限を付ける / 出力に外部 URL を描画しない。reviews の本文は AI から見える列に入れない / 録画した応答の CI は「ハーネスの回帰テスト」と呼ぶ / 1質問あたりの最大ステップ数・トークン・1日の上限と、月の LLM 予算 / ADR 候補: 運用エージェントの③を実装しない理由
- plan-critic の指摘(フェーズ2の計画を決めるとき、正式に3回のレビューを通す):
  - 完了の基準をテーブルの型ごとに分ける(明細型は3日の再実行で差分0、マスタ型は全件を入れ直して同じ結果)
  - Silver の主キーの unique / not_null は、フェーズ2の「全テーブルの Silver」の完了に含める(relationships はフェーズ3)
  - orders の `_source_file` は、dbt への移行(別名のテーブルに作って比べる)と1回にまとめる。NULL のまま許容するかを決める
  - バックフィルは `max_active_runs=1` で、テーブルごとに直列に流す(Iceberg の同時コミットの衝突を避ける)。日次とまとめての結果の一致を確かめる
  - Airflow のリトライでは run_id が同じなので、ログの `batch_id` に試行番号を入れる
  - 「全テーブルの Bronze と Silver」は、型ごとの代表の1表(order_items、reviews、sellers)から進める
  - OPTIMIZE / VACUUM には、transform ロールに iceberg/ の削除の権限と、保持の設定が要る。VACUUM はバックフィルのあとに流す
