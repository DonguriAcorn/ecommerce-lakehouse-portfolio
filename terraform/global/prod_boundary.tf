# ============================================================
# ecom-prod-boundary: prod のロールに付ける権限の上限(権限境界。ADR 0017)
# これ自体は何も許可しない。ロールの権限は「ロールのポリシー」と「この枠」の重なりだけになる。
# IAM の権限は入れない(枠が付いたロールは、自分でロールを作ったり権限を足したりできない)
# ============================================================

locals {
  # prod の lake バケット(ci_dbt.tf の dev_lake_* と同じ形)
  prod_lake_bucket = "ecom-lakehouse-prod-${local.account_id}"
  prod_lake_arn    = "arn:aws:s3:::${local.prod_lake_bucket}"
}

data "aws_iam_policy_document" "prod_boundary" {
  # S3: バケットの一覧と場所(prod のバケットだけ。dev は入らない)
  statement {
    sid       = "ListProdLakePrefixes"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [local.prod_lake_arn]
  }

  # S3: オブジェクトの読み書き(細かい線引きは、各ロール自身のポリシーに任せる)
  statement {
    sid    = "ReadWriteProdLakeObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${local.prod_lake_arn}/*"]
  }

  # Athena: workgroup ecom-prod だけ
  statement {
    sid    = "RunProdAthena"
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:StopQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:BatchGetQueryExecution",
      "athena:ListQueryExecutions",
      "athena:GetWorkGroup",
    ]
    resources = ["arn:aws:athena:ap-northeast-1:${local.account_id}:workgroup/ecom-prod"]
  }

  # Glue: ecom_prod_* の DB とテーブルだけ(いまの transform が使う権限を網羅する)
  statement {
    sid    = "ManageProdGlue"
    effect = "Allow"
    actions = [
      "glue:Get*",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:DeleteTableVersion",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:DeletePartition",
      "glue:BatchDeletePartition",
      "glue:BatchGetPartition",
    ]
    resources = [
      "${local.glue_arn_base}:catalog",
      "${local.glue_arn_base}:database/ecom_prod_*",
      "${local.glue_arn_base}:table/ecom_prod_*/*",
    ]
  }
}

# 枠を IAM ポリシーの実体として作る(ロールには、この ARN を渡す)
resource "aws_iam_policy" "prod_boundary" {
  name        = "ecom-prod-boundary"
  description = "Permissions boundary for ecom-prod-* roles. No IAM actions. ADR 0017" # IAM の説明は英語のみ
  policy      = data.aws_iam_policy_document.prod_boundary.json
}
