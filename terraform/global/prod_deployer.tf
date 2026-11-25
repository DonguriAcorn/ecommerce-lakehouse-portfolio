# ============================================================
# ecom-prod-deployer: 承認を通った prod の terraform apply を打つロール(ADR 0017)
# 触れるのは prod の設定だけ。lake バケットの中のデータは読み書きできない。
# IAM のロールは、権限境界(ecom-prod-boundary)が付くときだけ作る・変えることができる
# ============================================================

locals {
  # ecom-prod-* の名前に当たるロールの ARN(アカウント ID は account_id から作る)
  prod_role_arns    = "arn:aws:iam::${local.account_id}:role/ecom-prod-*"
  prod_deployer_arn = "arn:aws:iam::${local.account_id}:role/ecom-prod-deployer"
}

# ---------- 信頼ポリシー: environment:prod の判子があるジョブだけ ----------
data "aws_iam_policy_document" "prod_deployer_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    # 証明書の宛先が AWS の STS であること
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # GitHub Environments の prod(承認を通ったジョブ)だけ。完全一致。PR 用の sub は入れない
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:environment:prod"]
    }
  }
}

# ---------- ロール本体 ----------
resource "aws_iam_role" "prod_deployer" {
  name                 = "ecom-prod-deployer"
  description          = "GitHub Actions prod deploy: terraform apply for envs/prod only. ADR 0017" # IAM の説明は英語のみ
  assume_role_policy   = data.aws_iam_policy_document.prod_deployer_trust.json
  max_session_duration = 3600
}

# ---------- 権限 ----------
data "aws_iam_policy_document" "prod_deployer" {
  # 状態ファイル: prod 用の1つと、ロックファイル(use_lockfile)だけ読み書きする
  statement {
    sid     = "ProdStateReadWrite"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${local.tfstate_bucket}/envs/prod/terraform.tfstate",
      "arn:aws:s3:::${local.tfstate_bucket}/envs/prod/terraform.tfstate.tflock",
    ]
  }

  statement {
    sid       = "ListStateBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${local.tfstate_bucket}"]
  }

  # lake バケットの「設定」だけ。/* を付けないので、中のデータは読み書きできない
  statement {
    sid    = "ManageProdBucketSettings"
    effect = "Allow"
    actions = [
      "s3:GetBucket*",
      "s3:PutBucket*",
      "s3:GetLifecycleConfiguration",
      "s3:PutLifecycleConfiguration",
      "s3:GetEncryptionConfiguration",
      "s3:PutEncryptionConfiguration",
    ]
    resources = [local.prod_lake_arn]
  }

  # Glue: prod の DB とテーブルだけ
  statement {
    sid    = "ManageProdGlue"
    effect = "Allow"
    actions = [
      "glue:Get*",
      "glue:CreateDatabase",
      "glue:UpdateDatabase",
      "glue:DeleteDatabase",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:TagResource",
    ]
    resources = [
      "${local.glue_arn_base}:catalog",
      "${local.glue_arn_base}:database/ecom_prod_*",
      "${local.glue_arn_base}:table/ecom_prod_*/*",
    ]
  }

  # Athena: workgroup ecom-prod だけ
  statement {
    sid    = "ManageProdAthena"
    effect = "Allow"
    actions = [
      "athena:GetWorkGroup",
      "athena:CreateWorkGroup",
      "athena:UpdateWorkGroup",
      "athena:DeleteWorkGroup",
      "athena:TagResource",
      "athena:ListTagsForResource",
    ]
    resources = ["arn:aws:athena:ap-northeast-1:${local.account_id}:workgroup/ecom-prod"]
  }

  # IAM の書き込み: 対象は ecom-prod-* だけ。枠(ecom-prod-boundary)が付くときだけ許す
  statement {
    sid    = "WriteProdRolesOnlyWithBoundary"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePermissionsBoundary",
      "iam:TagRole",
      "iam:UntagRole",
    ]
    resources = [local.prod_role_arns]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.prod_boundary.arn]
    }
  }

  # IAM の読み取り: plan と refresh が、既存のロールと枠のポリシーを読むため
  statement {
    sid    = "ReadProdRoles"
    effect = "Allow"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListRoleTags",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = [local.prod_role_arns]
  }

  statement {
    sid       = "ReadBoundaryPolicy"
    effect    = "Allow"
    actions   = ["iam:GetPolicy", "iam:GetPolicyVersion"]
    resources = [aws_iam_policy.prod_boundary.arn]
  }

  # 明示の Deny(Allow より必ず勝つ): 枠そのもの、枠を外す操作、deployer 自身は変えさせない
  statement {
    sid    = "DenyChangingBoundary"
    effect = "Deny"
    actions = [
      "iam:CreatePolicyVersion",
      "iam:DeletePolicy",
      "iam:DeletePolicyVersion",
      "iam:SetDefaultPolicyVersion",
    ]
    resources = [aws_iam_policy.prod_boundary.arn]
  }

  statement {
    sid       = "DenyRemovingBoundary"
    effect    = "Deny"
    actions   = ["iam:DeleteRolePermissionsBoundary"]
    resources = [local.prod_role_arns]
  }

  statement {
    sid    = "DenyEditingDeployerItself"
    effect = "Deny"
    actions = [
      "iam:DeleteRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePermissionsBoundary",
    ]
    resources = [local.prod_deployer_arn]
  }
}

resource "aws_iam_role_policy" "prod_deployer" {
  name   = "prod-deployer-access"
  role   = aws_iam_role.prod_deployer.id
  policy = data.aws_iam_policy_document.prod_deployer.json
}
