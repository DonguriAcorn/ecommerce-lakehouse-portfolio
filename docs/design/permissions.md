# 権限設計表

- 作成日: 2026-10-22
- 状態: ingest と transform は実装済み(terraform/modules/lakehouse_env/iam.tf)。CI のロール3つのうち、plan 用(`ecom-ci-plan`)、CI の dbt 用(`ecom-ci-dbt`)、prod の deployer(`ecom-prod-deployer`)と権限境界(`ecom-prod-boundary`)は、terraform/global に作成済み(2026-11-26。設計は ADR 0017)。reader は作らない(2026-11-14)

## 方針

- 各ロールは、その処理に必要な権限だけを持つ(最小権限)。
- 人のスイッチロールは後回しにする。実務では、環境ごとに AWS アカウントを分けたときに使う(ADR に書く)。
- 環境(dev / prod の2つ。test は作らない)ごとに、同じ形のロールを作る。名前は `ecom-<環境>-<役割>` とする。CI のロールは環境をまたぐので、例外として `ecom-ci-<役割>` とする(2026-11-26 に確定。ADR 0017)。

## ロール一覧

| ロール | 使う処理 | 引き受けられる相手(信頼ポリシー) |
|---|---|---|
| `ecom-<環境>-ingest` | リプレイと、Raw への取り込み | `portfolio-admin`(ローカルの Airflow や手元の実行) |
| `ecom-<環境>-transform` | dbt と Athena による Silver、Gold の作成 | `portfolio-admin`。prod だけ、GitHub の OIDC(`sub` は `environment:prod`)も追加(main のあとの prod の dbt) |
| `ecom-ci-plan` | PR の `terraform plan`(dev、prod、global。`-lock=false`)。使うサービスの Describe / Get / List と、状態ファイルの読み取りだけ | GitHub の OIDC(PR 用の `sub`) |
| `ecom-ci-dbt` | PR の `dbt build`。練習用の Glue DB(`ecom_ci_silver` と `ecom_ci_gold`)と `iceberg/ci/` だけに書ける。Bronze は dev を読むだけ。workgroup は `ecom-ci` | GitHub の OIDC(PR 用の `sub`) |
| `ecom-prod-deployer` | main のあと、手動承認を経た prod への Terraform の実行(dbt は transform が流す) | GitHub の OIDC(`sub` は GitHub Environments の `prod`) |

- reader は作らない(アプリは Parquet を読むだけで AWS に接続しないため。要るときはフェーズ9で足す。2026-11-14)。
- deployer は prod 専用の1つだけにする。dev は手元の `portfolio-admin` のまま。

## Terraform を apply する人

| 場所 | apply する人 | 状態ファイルの置き場所 |
|---|---|---|
| terraform/bootstrap | `portfolio-admin`(手元で実行) | ローカルだけ |
| terraform/global(Budgets、OIDC など、アカウントに1つのもの) | `portfolio-admin`(手元で実行) | S3(`global/terraform.tfstate`) |
| terraform/envs/dev | `portfolio-admin`(手元で実行。dev は CI から apply しない) | S3(`envs/dev/terraform.tfstate`) |
| terraform/envs/prod(フェーズ4で作る) | prod の deployer(main のあと、GitHub Environments の手動承認を経て。保存した plan だけを apply する)。最初の1回は `portfolio-admin` | S3(`envs/prod/terraform.tfstate`) |

- global は、環境を作り直しても消えないよう、環境(envs/)とは別の状態ファイルに分ける。
- bootstrap に共通リソースを入れない理由: bootstrap の状態はローカルだけにあり、マシンが壊れると失われるため。

## S3 の権限

凡例: 読 = 読み取り、書 = 書き込みと削除、置 = 書き込みだけ(読み取りと削除はしない)、— = 権限なし。

| ロール | `raw/` | `iceberg/` | `athena-results/` | `logs/` | `quarantine/` |
|---|---|---|---|---|---|
| ingest | 読・書 | — | — | 置 | 置 |
| transform | 読 | 読・書 | 読・書 | —(フェーズ2で置を足す) | — |
| prod の deployer | バケット自体の設定の管理(中のデータは読み書きしない) | 同左 | 同左 | 同左 | 同左 |

prod の deployer は、状態ファイル用のバケットのうち `envs/prod/` だけ、読み書きできる(環境ごとに分ける)。CI の dbt 用ロールは、`iceberg/ci/` だけ読み書きできる。

## Athena と Glue の権限

| ロール | Athena | Glue(データベースとテーブル) |
|---|---|---|
| ingest | — | — |
| transform | `ecom-dev` の workgroup だけ実行できる | bronze、silver、gold の3つのテーブル定義を、読み書き(dbt-athena が古いテーブルの版を整理するため、`GetTableVersions` と `DeleteTableVersion` も含む。2026-11-03 追加) |
| ci-dbt | `ecom-ci` の workgroup だけ実行できる(結果は `athena-results/ci/`) | `ecom_ci_silver` と `ecom_ci_gold` のテーブルを読み書き(DB は作れない)。dev の Bronze は読むだけ(S3 の `raw/` も読むだけ) |
| prod の deployer | workgroup の管理(prod の分だけ) | データベースの管理(prod の分だけ) |

## 設計の考え方

- `primary` の workgroup は使わせない。Athena の権限は、環境ごとの workgroup だけに限定する。
- Athena は、実行した人(ロール)の権限で S3 を読み書きする。そのため、transform には、Athena の権限に加えて、S3 の権限も必要である。
- IAM を操作する権限は、prod の deployer だけに限定し、対象を `ecom-prod-` で始まる名前に絞る(`ecom-dev-*` は触れない。`ecom-` だけの絞り方では、同じアカウントの dev も触れてしまうため)。さらに権限境界 `ecom-prod-boundary` を使い、deployer は枠の付いたロールしか作れず、枠と自分自身は変えられない(ADR 0017)。
- CI のロールと権限境界は terraform/global に置き、CI が自分の権限を書き換えられないようにする(ADR 0017)。
- OIDC の `sub` で、PR 用と prod 用を分ける。`ecom-ci-plan` と `ecom-ci-dbt` は PR 用の `sub` だけを許可し、prod の deployer は GitHub Environments の `prod` の `sub` だけを許可する(PR 用の `sub` は許可しない)。これで、承認を通らないジョブは prod のロールを借りられない。
- logs/ と quarantine/ は「置」にする。記録は、あとから書き換えたり消したりできないほうが、調査の証拠として信用できる。消すのは、S3 のライフサイクル(logs/ は 90日、quarantine/ は 30日)に任せる([error-handling.md](error-handling.md))。
- アップロードは `aws s3 sync` で行う。sync は、送る先にすでにあるファイルの一覧を見るので、ingest には logs/ と quarantine/ の一覧の権限(`s3:ListBucket`)も要る。`--delete` は使わない(削除の権限がないため)。

## 実装の順番

1. 取り込みと変換に必要な `ingest` と `transform` を、最初に作る(実装済み)。
2. `reader` は作らない(2026-11-14)。
3. CI のロール3つ(plan 用、CI の dbt 用、prod の deployer)は、CI/CD(OIDC)の段階で作る。
