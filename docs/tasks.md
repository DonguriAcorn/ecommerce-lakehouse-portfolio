# タスクと進捗

全体の流れと、どこまで済んだかを一覧にする。要件とスコープの原本は [handoff.md](handoff.md)、設計の理由と検証結果は [design/](design/) を見る。

## 使い方

- `[x]` 済み / `[ ]` まだ / `[~]` やらないと決めた(理由を書く)
- 済みの基準: 動作を確認し、コミットと push まで済んだもの。
- 「← 今ここ」は、常に1か所だけ付ける。
- 印: 〔必須〕〔推奨〕は handoff §7 の区分。〔追加〕は handoff §8 に無く、あとから足したもの。
- 遅れたときに後ろへ回す順: 〔後回し候補1〕質問ログ → 〔後回し候補2〕パイプライン健康状態ページ → 〔後回し候補3〕Runbook。必須は落とさない。
- README と ADR は、全フェーズで随時書き足す。
- 対象外(バックログ)と、入れないと決めたものは、handoff §7 を参照。
- 更新するのは、セッションの終わり(「ここまでにする」)。下の「現在の状態」と一緒に更新案を示し、承認を得てからコミットする。

## 現在の状態

- 途中経過: フェーズ1が終わった。OIDC プロバイダを global に作り、dev を terraform/modules/lakehouse_env にモジュール化し(14 件を `moved` で移動。置き換え 0、削除 0。`moved.tf` は apply 後に消した)、ADR を 0001〜0009 の 9 件書いた。tf-plan の通しも確認できた。plan-critic の3回レビューが、モジュール化の穴(手順 0、`moved` の置き場所、`tfplan` の除外)を事前に見つけた。
- 次の1手: フェーズ2の最初のタスク「ruff と pytest を始める」。初めての内容なので、まず `pyproject.toml` の今の設定を読み、pytest と ruff の考え方の説明から始める。

## 未決(着手の前に決める)

- 月額の上限額(Budgets の前)
- Airflow から AWS への認証方式(Airflow の土台の前。管理者の長期キーをコンテナに入れない)
- dbt に移したあと、sql/silver/ を消すか残すか(dbt への移行のとき)
- test / prod に流すデータの日数(フェーズ4)
- 公開アプリのホスティング先と、export の置き場所(フェーズ5)
- handoff §5 の API 取り込み(為替)を入れるか、`[~]` にするか

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
  - [x] run_replay.py に、ログと隔離を入れる(Python の取り込みだけ。dbt の失敗は「Airflow の運用」で扱う)
    - [x] ログの部品: ingestion/run_log.py(JSON Lines)
    - [x] 検証: ingestion/validate_orders.py(停止と隔離の判定。実データは隔離0件で確認)
    - [x] run_replay.py に組み込む(実行の始めと終わりのログ、隔離の Parquet を quarantine/ の形で書く、停止は終了コード 1)
      - 済み。実データは隔離0件。停止(CSV なし)は終了コード 1 で確認。隔離ありの動きは、フェーズ2の pytest で確かめる
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
  - 済み。入力は `env` と `admin_user_name`。dev の 14 件を移動し、apply 後も `No changes`。`moved.tf` は消した。状態のバックアップは terraform/backups/(Git の管理外)。test / prod の作成はフェーズ4(下記)(2026-11-03)
- [x] ADR を書く
  - 済み。0001〜0009(環境の分け方、SSO 後回し、テーブル定義、Raw の形、ログ、S3 の構成、Airflow、データカタログ、AI 開発の構成)(2026-11-03)
  - 候補: Bronze を外部テーブルにした理由、Raw をスナップショットの形にした理由、Raw の段階で型を付けた Parquet にした簡略化、エラーのログを S3 に JSON Lines で残す理由、Silver の定義を Terraform ではなく SQL(のちに dbt)で持つ理由、Airflow を選んだ理由、S3 の構成、環境の分け方とアカウント分離、スイッチロールを後回しにした理由、管理者を IAM ユーザーのままにし SSO を後回しにした理由、専用のデータカタログを使わない理由、AI 開発の構成(禁止の設定、CLAUDE.md、skills、サブエージェントの使い分け)

## フェーズ2: 取り込み

完了の目安: 全テーブル・全期間を Airflow で流し、指定した3日を再実行して、全 Silver の差分が 0

- [ ] Olist のリプレイ〔必須〕(orders だけ済み。全テーブルが済んだら `[x]`)
- [ ] S3 Raw〔必須〕(同上)
- [ ] Silver の MERGE〔必須〕(同上)
- [ ] 監査カラム(`_ingested_at`、`_source_file`、`_batch_id`)を、Raw と Silver の全テーブルに〔推奨〕(orders の Silver には `_source_file` が足りない)
- [ ] ruff と pytest を始める〔推奨。handoff ではフェーズ4。前倒し〕(完了: `uv run pytest` と `uv run ruff check` が通る) ← 今ここ
- [ ] lake バケットの S3 バージョニング〔追加〕(2026-11-03 に、dev の lake バケットが未設定と確認。誤って消した実データを戻すため。足すときは、非現行バージョンの期限を決める)
- [ ] orders の Silver を dbt に移す〔追加。handoff ではフェーズ3。前倒し〕
  - 注意: 先に CTAS で比較用のコピーを取る。full-refresh はしない(Athena で Iceberg のテーブルを DROP すると、データも消える)。dbt の置き場所は iceberg/ に固定する(athena-results/ はライフサイクルで消える)
  - 完了: 比較の SQL で差分が 0
- [ ] リプレイを、どのテーブルにも使える形にする(Python。テーブルごとの日付の規則を持つ。pytest 付き)〔必須〕
- [ ] 全テーブルの Bronze(Terraform)と Silver(dbt)〔必須〕
  - 対象: orders、order_items、payments、reviews、customers、sellers、products、product_category_name_translation、geolocation
  - 完了: 全テーブルが Bronze と Silver にある。件数は、キーの種類の数で照合する
- [ ] Airflow の土台(ローカルの Docker Compose、1日分の DAG、冪等)〔必須〕
- [ ] Airflow の運用(リトライ、失敗の通知、dbt の失敗を logs/ に残す、Iceberg の OPTIMIZE / VACUUM)〔必須〕
- [ ] 全期間のバックフィルを、Airflow で行う〔必須〕(期間を指定して、まとめて MERGE する。完了: 全期間で、キーの種類の数が元データと一致)

## フェーズ3: モデリング

完了の目安: `dbt build` がすべて通る

- [ ] dbt の meta / tags(owner、pii、update_frequency)〔推奨〕(PII のハッシュ化より先に。どの列が PII かを決めるため)
- [ ] セマンティックレイヤー Lv1(dbt の YAML に、テーブルとカラムの説明)〔必須〕
- [ ] Gold のスター型(fact_orders、dim_customer、dim_product、dim_date)〔必須〕
- [ ] SCD Type 2〔必須〕(dim_customer。材料は customers のリプレイ)
- [ ] dbt tests〔必須〕
- [ ] 鮮度チェック〔必須〕(基準は今の時刻ではなく `_ingest_date`。データが 2018 年のため)
- [ ] PII のハッシュ化〔推奨〕
- [ ] データコントラクト〔推奨〕
- [ ] 用語集(GMV、リピート率など)〔推奨〕

## フェーズ4: CI/CD

完了の目安: PR で lint・テスト・plan・`dbt build` が動き、main へのマージで、test に Terraform と dbt が自動で反映される

- [ ] sqlfluff と pre-commit〔推奨〕(gitleaks の pre-commit だけは、フェーズ1に前倒しした)
- [ ] test / prod の環境を作る(フェーズ1のモジュールを使う)〔必須〕
- [ ] test / prod のデータを用意する〔追加〕
- [ ] GitHub Actions から OIDC で接続: deployer ロール、PR 用の plan ロール、CI 専用のロール〔必須〕(CI から dev の本物のテーブルに書けないようにする)
- [ ] PR チェック(ruff、pytest、sqlfluff、`terraform plan`、一時スキーマでの `dbt build`。PR を閉じたら片付ける)〔必須〕
- [ ] main へのマージで test に自動デプロイ、prod は手動の承認(GitHub Environments)〔必須〕
- [ ] Slim CI(`state:modified+`)〔推奨〕

## フェーズ5: アプリ(v1.0)

完了の目安: 公開 URL で見られる

- [ ] 前提: Olist のライセンスを確認する〔必須〕
- [ ] export の置き場所と、アプリへの渡し方を設計する〔追加〕
- [ ] reader ロール〔追加〕
- [ ] Gold の Parquet export〔必須〕
- [ ] セマンティックレイヤー Lv2(semantic/metrics.yml)〔必須〕
- [ ] Streamlit のダッシュボード(売上 KPI、期間比較、リピート率、商品ランキング)〔必須〕
- [ ] パイプライン健康状態ページ〔推奨〕〔後回し候補2〕
- [ ] v1.0 のタグを付けて公開する

## フェーズ6: AI(v1.1)

完了の目安: 評価セットの正答率を README に載せられる

- [ ] 前提: 使う LLM と予算を決める(CI で評価する費用も含む)
- [ ] ガードレール(SELECT のみ、Gold のみ、LIMIT、PII カラムの除外、sqlglot)〔必須〕
- [ ] 悪用対策(閲覧者のキー入力か、回数の制限)〔必須〕
- [ ] AI アナリスト(質問 → SQL → 検証 → 実行 → 表・グラフ・要約)〔推奨〕
- [ ] PII の除外の一覧を、pii フラグから自動で作る〔推奨〕
- [ ] 評価セット(20〜30 問)と、CI での測定〔推奨〕
- [ ] 質問ログ〔推奨〕〔後回し候補1〕(書き先を決めて、handoff §10 を直す)
- [ ] v1.1 のタグ

## フェーズ7: 仕上げ(v1.2)

完了の目安: 第三者が README だけで再現できる(新しく clone した環境で確かめる)

- [ ] Iceberg の運用の調整とデモ(compaction、スナップショットの削除)〔推奨〕
- [ ] スキーマ進化のデモ〔推奨〕
- [ ] dbt docs の公開〔推奨〕
- [ ] Runbook〔推奨〕〔後回し候補3〕
- [ ] 月次のコストを記載する〔推奨〕
- [ ] README に「やらないこと」を、理由つきで書く〔推奨〕
- [ ] 社内展開時の構成の ADR(実施するかは未定)
- [ ] v1.2 のタグ

## フェーズ8: Snowflake 連携(v1.0 以降の拡張)

完了の目安: 同じ SQL が両方のエンジンで同じ結果になり、比較表が README にある

- [ ] フェーズ7の完了後に、トライアルを申し込む(30 日以内に終える)
- [ ] Glue カタログ連携で、Iceberg のテーブルを Snowflake から読む(読み取りだけ)
- [ ] 同じ集計 SQL を Athena と Snowflake で実行し、結果が一致することを確かめるテスト
- [ ] 実行時間・課金・使い勝手の比較を、ADR と README に書く(スクリーンショットも残す)

## 着手時メモ

計画の批評で出た細かい注意。着手するときに設計書へ移し、ここから消す。

- dbt への移行: 「古い日付では上書きしない」条件の再現。`profiles.yml` は `env_var` を使い、アカウント ID を書かない。`s3_data_dir` / `s3_data_naming` / `on_schema_change` を決める。transform ロールの権限(dbt の一時テーブル)。実行はローカルの uv で `AWS_PROFILE=ecom-dev-transform`。check_orders_rerun.sql は、dbt の test か analyses へ移す。
- テーブルの型と主キー:
  - 明細の型(orders の日付に従う): order_items `(order_id, order_item_id)`、payments `(order_id, payment_sequential)`、customers `customer_id`
  - 独自の日付: reviews `(review_id, order_id)`(review_id に重複があり、コメントに改行を含む)
  - マスタの型(日付なし): sellers、products、product_category_name_translation、geolocation(約 100 万行で主キーなし。郵便番号ごとに1行へまとめるかなど、重複の扱いを設計する)
  - customer_unique_id ごとに住所が変わったものが 252 件ある(SCD2 の材料)
- Airflow: dbt は Airflow と別の venv で動かす。`_batch_id` に Airflow の run_id を渡す。メモリは約 4GB が必要。通知先はシークレットとして扱う。dbt の失敗は、`run_results.json` の要点を logs/ に書く(そのときに、transform ロールへ logs/ の書き込みを足す)。
- CI 専用のロール: `ecom_ci_*` の Glue DB と `iceberg/ci/` だけに書ける。Bronze は読むだけ。
- sqlfluff: テンプレーターは jinja にして、Athena に接続しない。
- export: 公開アプリに AWS の認証情報を持たせない(案: Git の例外のパス、GitHub Releases、ビルド時に取得)。書き出すロール、permissions.md の `export/` 列、ライフサイクルも決める。健康状態ページは、export のときに状態の要約も出す。
- 質問ログ: handoff §10 の「Iceberg に貯める」は、§4 の「公開アプリに AWS の認証情報を持たせない」と両立しない。
- plan-critic の指摘(フェーズ2の計画を決めるとき、正式に3回のレビューを通す):
  - 完了の基準をテーブルの型ごとに分ける(明細型は3日の再実行で差分0、マスタ型は全件を入れ直して同じ結果、geolocation は重複の方針を先に決める)
  - Silver の主キーの unique / not_null は、フェーズ2の「全テーブルの Silver」の完了に含める(relationships はフェーズ3)
  - orders の `_source_file` は、dbt への移行(別名のテーブルに作って比べる)と1回にまとめる。NULL のまま許容するかを決める
  - バックフィルは `max_active_runs=1` で、テーブルごとに直列に流す(Iceberg の同時コミットの衝突を避ける)。日次とまとめての結果の一致を確かめる
  - Airflow のリトライでは run_id が同じなので、ログの `batch_id` に試行番号を入れる
  - 「全テーブルの Bronze と Silver」は、型ごとの代表の1表(order_items、reviews、sellers)から進める
  - OPTIMIZE / VACUUM には、transform ロールに iceberg/ の削除の権限と、保持の設定が要る。VACUUM はバックフィルのあとに流す
