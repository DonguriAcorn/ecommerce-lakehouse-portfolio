# ADR 0017: GitHub Actions は OIDC で AWS のロールを借りる(ロール3つと権限境界)

- 日付: 2026-11-26
- 状態: 採用
- 関係: [ADR 0016](0016-two-environments.md)(dev と prod の2環境、PR の `ecom_ci`、prod への手動承認)、[permissions.md](../design/permissions.md)、[secrets.md](../design/secrets.md)、tasks.md のフェーズ4

## 状況

フェーズ4では、PR のチェック(`terraform plan`、`ecom_ci` での `dbt build`)と、main へのマージ後の prod へのデプロイを、GitHub Actions で動かす。GitHub のサーバーから AWS に入る手段が要る。

アクセスキーを GitHub の Secrets に置く方法は、期限のない鍵を外に置くことになる。このリポジトリは Public で、漏れたときの被害が大きい。secrets.md の「鍵を持たない形を第一にする」にも反する。OIDC プロバイダは、フェーズ1で terraform/global に作り済みで、それを使うロールがまだない。

## 決めたこと

1. GitHub Actions は、OIDC で一時キー(1時間)を受け取ってロールを借りる。アクセスキーは GitHub に置かない。
2. ロールは次の3つを新しく作る。名前は permissions.md の決まりに合わせる。

   | ロール | 使うジョブ | 借りられる `sub` |
   |---|---|---|
   | `ecom-ci-plan` | PR の `terraform plan`(dev、prod、global) | `repo:<owner>@<owner_id>/<repo>@<repo_id>:pull_request` |
   | `ecom-ci-dbt` | PR の `ecom_ci` での `dbt build` | `repo:<owner>@<owner_id>/<repo>@<repo_id>:pull_request` |
   | `ecom-prod-deployer` | 承認を経た prod の `terraform apply` | `repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:prod` |

3. prod の dbt は、deployer でなく、いまの `ecom-prod-transform` を OIDC で借りて流す。transform の信頼ポリシーに、`environment:prod` の `sub` を prod だけ足す。deployer は設定を変える役、transform はデータを書く役として分ける。
4. 信頼ポリシーでは、`aud` が `sts.amazonaws.com` であることと、`sub` が上の値と完全に一致することを条件にする。ワイルドカード(`repo:<owner>/*` など)は使わない。書き込みのできるロール(`ecom-prod-deployer`、`ecom-prod-transform`)に、PR 用の `sub` は許可しない。`sub` のリポジトリは、名前に加えて変わらない番号(ID)で照合する(GitHub の証明書の形。同じ名前で作り直されたリポジトリに借りられないため)。
5. 3つのロールは、すべて terraform/global に置く。global を apply するのは、手元の portfolio-admin だけである。
6. `ecom-ci-plan` には、使っているサービス(S3、IAM、Glue、Athena、Budgets など)の Describe / Get / List だけを、自分で一覧にして許す。S3 の `GetObject` は、状態ファイルのバケットだけに許す。PR の plan は `-lock=false` で打ち、状態ファイルに書く権限を持たせない。
7. `ecom-prod-deployer` には、権限境界(permissions boundary)を使う。
   - prod のロールに付ける上限の枠として、`ecom-prod-boundary` を global に作る。枠の中身は、prod の ingest と transform が使う範囲(prod のバケット、`ecom-prod` の workgroup、`ecom_prod_*` の Glue)だけにし、IAM の権限は入れない。
   - deployer が IAM のロールを作る・ポリシーを付けるときは、この枠が付いていることを条件にする。対象は `ecom-prod-*` の名前のロールだけにする。
   - deployer は、枠のポリシー自身、枠を外す操作、deployer 自身のロールを変えられない(明示の Deny)。
   - モジュール(lakehouse_env)に、権限境界の変数を1つ足す。dev は null(枠なし)のままにする。

## 理由

- OIDC の一時キーは、ジョブごとに発行され1時間で切れる。保存した鍵がないので、漏れる物がない。
- `sub` を完全一致にするのは、OIDC でいちばん多い事故(ワイルドカードで、ほかのリポジトリや承認を通らないジョブまで借りられる)を防ぐためである。承認を通らない PR のジョブは、prod に書けるロールを借りられない。
- global に置くのは、CI が自分の権限を書き換えられないようにするためである。deployer を envs/prod に置くと、PR で deployer の定義に権限を足してマージすれば、deployer が自分で自分を強くできる。global は手元でしか apply しないので、CI のロールの権限は、人が打たない限り変わらない。
- plan 用ロールを自分で一覧にするのは、permissions.md の最小権限の方針に合わせるためである。PR のジョブは承認なしで動くので、データや秘密を読めないようにする。AWS 管理の ReadOnlyAccess は、全バケットの `GetObject` まで含み、広すぎる。
- `-lock=false` にするのは、plan は何も変えないので、ロックがなくても壊れないためである。ロックを取らなければ、plan 用ロールを完全に読むだけにできる。
- 権限境界を使うのは、IAM を書けるロールは、自分より強いロールを作れてしまうためである(例: `ecom-prod-transform` に管理者権限を付け、信頼ポリシーを書き換えて自分で借りる)。名前を `ecom-prod-*` に絞るだけでは、この抜け道は塞げない。枠があれば、作り直したロールも枠の外の権限を持てない。
- prod の dbt を transform で流すのは、deployer がデータの読み書きを持たないようにするためである。deployer が漏れても、データは読まれない。transform が漏れても、設定は変えられない。

## あきらめたこと(弱い点)

- plan 用ロールの一覧は、使うサービスやリソースを足すたびに、足りない権限が AccessDenied で見つかる。見つけるたびに、global で足す手間がかかる。
- 権限境界の分だけ、モジュールと global のコードが増え、読み手が追う箇所が増える。
- deployer は、枠の中であれば、prod の ingest と transform の権限を変えられる。prod の中での誤りは、承認画面で plan を読んで防ぐしかない(ADR 0016 と同じ弱点)。
- PR のジョブは、承認なしで `ecom-ci-plan` と `ecom-ci-dbt` を借りられる。悪意のある PR に備え、フォークからの PR に OIDC トークンを渡さない既定の動きを崩さない(`pull_request_target` は使わない)。
- Public のリポジトリでは、Actions のログを誰でも見られる。plan の出力には ARN が出て、そこにアカウント ID が入る。この対策は、PR チェックのワークフローを書くときに決める。

## 将来の乗り換え

アカウントを環境ごとに分けたら(ADR 0016 の将来の乗り換え)、ロールと OIDC プロバイダはアカウントごとに作る。権限境界の代わりに、組織の SCP(サービスコントロールポリシー)で上限を決める形にも移れる。
