data "aws_region" "current" {}

locals {
  account_id     = data.aws_caller_identity.current.account_id
  region         = data.aws_region.current.region
  admin_user_arn = "arn:aws:iam::${local.account_id}:user/${var.admin_user_name}"
  glue_arn_base  = "arn:aws:glue:${local.region}:${local.account_id}"
  glue_db_arn    = "${local.glue_arn_base}:database/ecom_${var.env}_*"
  glue_table_arn = "${local.glue_arn_base}:table/ecom_${var.env}_*/*"
}

data "aws_iam_policy_document" "assume_by_admin" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [local.admin_user_arn]
    }
  }
}

# transform 用の信頼ポリシー: 管理者に加えて、OIDC の変数が渡されたときだけ GitHub Actions も借りられる
data "aws_iam_policy_document" "assume_transform" {
  # 管理者(手元の portfolio-admin)。ingest と同じ
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [local.admin_user_arn]
    }
  }

  # GitHub Actions(prod だけ。dev は変数が null なので、この statement は作られない)
  dynamic "statement" {
    for_each = var.transform_oidc_provider_arn == null ? [] : [1]

    content {
      effect  = "Allow"
      actions = ["sts:AssumeRoleWithWebIdentity"]

      principals {
        type        = "Federated"
        identifiers = [var.transform_oidc_provider_arn]
      }

      # 証明書の宛先が AWS の STS であること
      condition {
        test     = "StringEquals"
        variable = "token.actions.githubusercontent.com:aud"
        values   = ["sts.amazonaws.com"]
      }

      # 承認を通った環境のジョブだけ(完全一致。ワイルドカードは使わない)
      condition {
        test     = "StringEquals"
        variable = "token.actions.githubusercontent.com:sub"
        values   = [var.transform_oidc_sub]
      }
    }
  }
}

# ---------- ingest ----------

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "ListRawPrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "logs/*", "quarantine/*"]
    }
  }

  statement {
    sid    = "ReadWriteRawObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*"]
  }

  statement {
    sid     = "PutLogsAndQuarantineObjects"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.lake.arn}/logs/*",
      "${aws_s3_bucket.lake.arn}/quarantine/*",
    ]
  }
}

resource "aws_iam_role" "ingest" {
  name                 = "ecom-${var.env}-ingest"
  assume_role_policy   = data.aws_iam_policy_document.assume_by_admin.json
  permissions_boundary = var.permissions_boundary # 権限の上限の枠(dev は null で枠なし)
}

resource "aws_iam_role_policy" "ingest" {
  name   = "ingest-raw-access"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

# ---------- transform ----------

data "aws_iam_policy_document" "transform" {
  statement {
    sid       = "ListLakePrefixes"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "iceberg/*", "athena-results/*"]
    }
  }

  statement {
    sid       = "GetBucketLocation"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.lake.arn]
  }

  statement {
    sid       = "ReadRawObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*"]
  }

  statement {
    sid    = "ReadWriteIcebergAndResults"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "${aws_s3_bucket.lake.arn}/iceberg/*",
      "${aws_s3_bucket.lake.arn}/athena-results/*",
    ]
  }

  statement {
    sid    = "RunAthenaQueries"
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
    resources = [aws_athena_workgroup.main.arn]
  }

  statement {
    sid    = "ManageGlueTables"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:GetTableVersions",   # dbt-athena が、作成後に古いテーブルの版を整理するため(版の一覧を読む)
      "glue:DeleteTableVersion", # 同じく、古い版を消す(Glue のメタデータだけ。S3 のデータは消さない)
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:DeletePartition",
      "glue:BatchDeletePartition",
    ]
    resources = [
      "${local.glue_arn_base}:catalog",
      local.glue_db_arn,
      local.glue_table_arn,
    ]
  }
}

resource "aws_iam_role" "transform" {
  name                 = "ecom-${var.env}-transform"
  assume_role_policy   = data.aws_iam_policy_document.assume_transform.json
  permissions_boundary = var.permissions_boundary # 権限の上限の枠(dev は null で枠なし)
}

resource "aws_iam_role_policy" "transform" {
  name   = "transform-access"
  role   = aws_iam_role.transform.id
  policy = data.aws_iam_policy_document.transform.json
}
