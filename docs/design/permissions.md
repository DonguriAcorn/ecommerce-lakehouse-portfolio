# 権限設計表

- 作成日: 2026-10-22
- 状態: ingest と transform は実装済み(terraform/envs/dev/iam.tf)。reader と deployer は実装前

## 方針

- 各ロールは、その処理に必要な権限だけを持つ(最小権限)。
- 人のスイッチロールは後回しにする。実務では、環境ごとに AWS アカウントを分けたときに使う(ADR に書く)。
- 環境(dev / test / prod)ごとに、同じ形のロールを作る。名前は `ecom-<環境>-<役割>` とする。

## ロール一覧

| ロール | 使う処理 | 引き受けられる相手(信頼ポリシー) |
|---|---|---|
| `ecom-dev-ingest` | リプレイと、Raw への取り込み | `portfolio-admin`(ローカルの Airflow や手元の実行) |
| `ecom-dev-transform` | dbt と Athena による Silver、Gold の作成 | `portfolio-admin`(のちに GitHub Actions も追加) |
| `ecom-dev-reader` | 集計結果の読み取り(アプリ、分析) | `portfolio-admin` |
| `ecom-dev-deployer` | GitHub Actions からの Terraform の実行 | GitHub の OIDC(このリポジトリの `main` だけ) |

## S3 の権限

凡例: 読 = 読み取り、書 = 書き込みと削除、置 = 書き込みだけ(読み取りと削除はしない)、— = 権限なし。

| ロール | `raw/` | `iceberg/` | `athena-results/` | `logs/` | `quarantine/` |
|---|---|---|---|---|---|
| ingest | 読・書 | — | — | 置 | 置 |
| transform | 読 | 読・書 | 読・書 | —(フェーズ2で置を足す) | — |
| reader | — | gold だけ読 | 読・書 | — | — |
| deployer | バケット自体の設定の管理(中のデータは読み書きしない) | 同左 | 同左 | 同左 | 同左 |

deployer は、状態ファイル用のバケットだけ、読み書きできる。

## Athena と Glue の権限

| ロール | Athena | Glue(データベースとテーブル) |
|---|---|---|
| ingest | — | — |
| transform | `ecom-dev` の workgroup だけ実行できる | bronze、silver、gold の3つのテーブル定義を、読み書き |
| reader | `ecom-dev` の workgroup だけ実行できる | gold の読み取りだけ |
| deployer | workgroup の管理 | データベースの管理 |

## 設計の考え方

- `primary` の workgroup は使わせない。Athena の権限は、環境ごとの workgroup だけに限定する。
- Athena は、実行した人(ロール)の権限で S3 を読み書きする。そのため、transform と reader には、Athena の権限に加えて、S3 の権限も必要である。
- IAM を操作する権限は、deployer だけに限定し、対象を `ecom-` で始まる名前のロールに絞る。
- logs/ と quarantine/ は「置」にする。記録は、あとから書き換えたり消したりできないほうが、調査の証拠として信用できる。消すのは、S3 のライフサイクル(logs/ は 90日、quarantine/ は 30日)に任せる([error-handling.md](error-handling.md))。
- アップロードは `aws s3 sync` で行う。sync は、送る先にすでにあるファイルの一覧を見るので、ingest には logs/ と quarantine/ の一覧の権限(`s3:ListBucket`)も要る。`--delete` は使わない(削除の権限がないため)。

## 実装の順番

1. 縦通しに必要な `ingest` と `transform` を、最初に作る。
2. `reader` は、Gold とアプリの段階で作る。
3. `deployer` は、CI/CD(OIDC)の段階で作る。
