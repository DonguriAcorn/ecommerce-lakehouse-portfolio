# ============================================================
# ecom-ci-plan: GitHub Actions の PR で terraform plan を打つロール(ADR 0017)
# 読むだけ。作る・変える・消す権限は1つも持たせない
# ============================================================

# いま Terraform を動かしているアカウントの情報(アカウント ID をコードに書かずに取るため)
data "aws_caller_identity" "current" {}

locals {
  # アカウント ID(ARN を組み立てるのに使う)
  account_id = data.aws_caller_identity.current.account_id

  # 状態ファイルのバケット名(main.tf の backend と同じ値。backend は変数を参照できないため、ここにも書く)
  tfstate_bucket = "tfstate-ecom-lakehouse-709a10"

  # plan で読む、環境ごとの lake バケット(dev と prod)
  lake_bucket_arns = [
    for env in ["dev", "prod"] : "arn:aws:s3:::ecom-lakehouse-${env}-${local.account_id}"
  ]

  # Glue の ARN の共通部分(東京リージョン)
  glue_arn_base = "arn:aws:glue:ap-northeast-1:${local.account_id}"
}

# ---------- 信頼ポリシー: 誰がこのロールを借りられるか ----------
data "aws_iam_policy_document" "ci_plan_trust" {
  statement {
    effect = "Allow"
    # OIDC の証明書(Web ID トークン)と引き換えに、ロールを借りる操作
    actions = ["sts:AssumeRoleWithWebIdentity"]

    # 証明書を出す相手: フェーズ1で作った GitHub の OIDC プロバイダ
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    # 証明書の宛先が AWS の STS であること(ほかのサービス宛ての証明書を使い回させない)
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # このリポジトリの PR のジョブだけ(完全一致。ワイルドカードは使わない)
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:pull_request"]
    }
  }
}

# ---------- ロール本体 ----------
resource "aws_iam_role" "ci_plan" {
  name = "ecom-ci-plan"
  # IAM の説明欄は日本語を受け付けないので英語で書く
  description          = "GitHub Actions PR: terraform plan (read only). ADR 0017"
  assume_role_policy   = data.aws_iam_policy_document.ci_plan_trust.json
  max_session_duration = 3600 # 一時キーの期限は1時間(最短の既定値)
}

# ---------- 権限: 読むだけの一覧 ----------
data "aws_iam_policy_document" "ci_plan" {
  # 状態ファイルの一覧を見る(どの状態ファイルがあるか)
  statement {
    sid       = "ListStateBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${local.tfstate_bucket}"]
  }

  # 状態ファイル3つの中身を読む(global、dev、prod)。ロックは取らない(-lock=false)
  statement {
    sid     = "ReadStateFiles"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "arn:aws:s3:::${local.tfstate_bucket}/global/terraform.tfstate",
      "arn:aws:s3:::${local.tfstate_bucket}/envs/dev/terraform.tfstate",
      "arn:aws:s3:::${local.tfstate_bucket}/envs/prod/terraform.tfstate",
    ]
  }

  # lake バケットの「設定」を読む(バージョニング、暗号化、ライフサイクルなど)
  # 対象はバケットそのものの ARN だけで、/* を付けないので中のデータは読めない
  statement {
    sid    = "ReadLakeBucketSettings"
    effect = "Allow"
    actions = [
      "s3:GetBucket*",                  # ACL、ポリシー、バージョニング、公開ブロックなど
      "s3:GetAccelerateConfiguration",  # 転送の高速化の設定
      "s3:GetEncryptionConfiguration",  # 暗号化の設定
      "s3:GetLifecycleConfiguration",   # ライフサイクルのルール
      "s3:GetReplicationConfiguration", # 複製の設定
    ]
    resources = local.lake_bucket_arns
  }

  # Glue のデータベースとテーブルの「定義」を読む(行のデータは Athena を通さないと読めない)
  statement {
    sid    = "ReadGlueDefinitions"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetTags",
      "glue:GetPartitionIndexes",
    ]
    resources = [
      "${local.glue_arn_base}:catalog",
      "${local.glue_arn_base}:database/ecom_*",
      "${local.glue_arn_base}:table/ecom_*/*",
    ]
  }

  # Athena の workgroup の設定を読む(クエリは実行できない)
  statement {
    sid       = "ReadAthenaWorkgroups"
    effect    = "Allow"
    actions   = ["athena:GetWorkGroup", "athena:ListTagsForResource"]
    resources = ["arn:aws:athena:ap-northeast-1:${local.account_id}:workgroup/ecom-*"]
  }

  # IAM のロールとポリシーの定義を読む(ecom- で始まるものだけ)
  statement {
    sid    = "ReadIamDefinitions"
    effect = "Allow"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyVersions",
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/ecom-*",
      "arn:aws:iam::${local.account_id}:policy/ecom-*",
    ]
  }

  # GitHub の OIDC プロバイダの定義を読む(global の plan で使う)
  statement {
    sid       = "ReadOidcProvider"
    effect    = "Allow"
    actions   = ["iam:GetOpenIDConnectProvider"]
    resources = [aws_iam_openid_connect_provider.github.arn]
  }

  # Budgets の予算の設定を読む(global の plan で使う)
  statement {
    sid       = "ReadBudgets"
    effect    = "Allow"
    actions   = ["budgets:ViewBudget", "budgets:ListTagsForResource"]
    resources = ["arn:aws:budgets::${local.account_id}:budget/*"]
  }
}

# 上の一覧を、ロールに埋め込みのポリシーとして付ける(ingest / transform と同じ形)
resource "aws_iam_role_policy" "ci_plan" {
  name   = "ecom-ci-plan"
  role   = aws_iam_role.ci_plan.id
  policy = data.aws_iam_policy_document.ci_plan.json
}
