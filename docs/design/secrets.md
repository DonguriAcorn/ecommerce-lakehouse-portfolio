# シークレット管理の方針

- 作成日: 2026-11-03
- 状態: 方針のみ。SSM のパラメータは、使う段階(フェーズ2以降)で作る

## 方針

- 鍵を持たない形を、第一に選ぶ。AWS の中の処理は IAM ロールを借り(AssumeRole)、外からの接続は OIDC や信頼ポリシーで一時的な権限を受け取る。
- 鍵がどうしても要るものは、SSM Parameter Store の SecureString に置く。名前は `/ecom/<環境>/<用途>` とする。
- リポジトリ(Public)には、本物の値を1つも置かない。見本は `*.example` にする。
- 隠しきれない値(state に入る値など)は、「見えても困らない値」にしておく。

## 秘密の一覧

| 秘密 | 使う段階 | 置き場所 | 鍵の有無 |
|---|---|---|---|
| portfolio-admin の鍵 | 今 | 手元の `~/.aws` | 長期の鍵(下の「管理者の鍵」を参照) |
| ingest / transform ロール | 今 | portfolio-admin から借りる | なし |
| AWS のアカウント ID | 今 | ファイルに書かない。Terraform は `aws_caller_identity` で取得する | ― |
| Budgets の通知先のメール | 今 | `terraform.tfvars`(Git の外)、変数は `sensitive = true` | ― |
| GitHub Actions から AWS へ | フェーズ4 | OIDC。ロールの ARN は GitHub の Variables に置く | なし |
| Airflow から AWS へ | フェーズ2 | 未決(管理者の長期の鍵は、コンテナに入れない) | ― |
| Streamlit のアプリの設定、LLM の API キー | フェーズ5〜6 | Streamlit Secrets。作者のキーは回数制限と一緒に使うか、閲覧者が自分のキーを入れる | あり |
| Snowflake から S3 へ | フェーズ8 | Snowflake 用の IAM ロールの信頼ポリシー(外部 ID 付き) | なし |

## SSM SecureString を選んだ理由

- 標準のパラメータは無料で、月額の上限(10 ドル)に合う。Secrets Manager は、1つにつき月 0.40 ドルかかる。
- Secrets Manager の強みは、鍵の自動交換(ローテーション)である。このプロジェクトには、自動交換が要る秘密(データベースのパスワードなど)がない。
- 自動交換が要る秘密が出てきたら、その秘密だけを Secrets Manager に置く。

## メールと state

- `sensitive = true` は、plan や apply の画面に値を出さないだけである。state ファイルには平文で入る。
- state のバケットは、暗号化、バージョニング、パブリックアクセスのブロックを済ませている(terraform/bootstrap)。
- そのうえで、通知先は専用のアドレスにする。漏れても、受信箱を止めれば済む。

## 管理者の鍵

- portfolio-admin は IAM ユーザーで、長期の鍵を `~/.aws` に置いている。個人の学習用で、AWS アカウントが1つのため、この形にした。
- 守り方: ルートユーザーと portfolio-admin に MFA を付ける。鍵は 90日を目安に交換する。鍵はリポジトリと Docker のイメージに入れない。
- 実務では、IAM Identity Center(SSO)で一時的な鍵を使う。後回しにした理由は、ADR に書く。

## 守りの層

1. `.gitignore`: tfvars、tfstate、`.env`、`secrets.toml`、鍵のファイルを Git に入れない。
2. Claude Code の deny(.claude/settings.json): 秘密のファイルと、ホームの秘密のフォルダ(`~/.aws`、`~/.ssh` など)を読ませない。
3. PreToolUse の hook(.claude/hooks/guard-bash.sh): まとめての `git add` や、.gitignore を無視する追加を止める。
4. pre-commit の gitleaks: コミットの前に、鍵の形をした文字列を探して止める。
5. GitHub の push protection: push の時点で、既知の形式の鍵を止める。

- deny と hook は文字列の照合なので、完全ではない。最後の守りは gitleaks と push protection である。
- アカウント ID とメールは、gitleaks では見つけにくい。コミットの前の session-end の確認で見る。

## 漏れたときの手順

1. まず、鍵を無効にする(IAM の鍵の削除、API キーの失効)。履歴から消すより先に行う。Public のリポジトリでは、push した時点で、もう見られていると考える。
2. CloudTrail で、漏れた鍵が使われていないかを確かめる。
3. 新しい鍵を作り、置き場所(`~/.aws`、SSM、Streamlit Secrets)を更新する。
4. 原因(どの層をすり抜けたか)を調べ、守りの層を直す。
