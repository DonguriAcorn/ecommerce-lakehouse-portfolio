data "aws_region" "current" {}

locals {
  account_id     = data.aws_caller_identity.current.account_id
  region         = data.aws_region.current.region
  admin_user_arn = "arn:aws:iam::${local.account_id}:user/portfolio-admin"
  glue_arn_base  = "arn:aws:glue:${local.region}:${local.account_id}"
  glue_db_arn    = "${local.glue_arn_base}:database/ecom_${local.env}_*"
  glue_table_arn = "${local.glue_arn_base}:table/ecom_${local.env}_*/*"
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
  name               = "ecom-${local.env}-ingest"
  assume_role_policy = data.aws_iam_policy_document.assume_by_admin.json
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
  name               = "ecom-${local.env}-transform"
  assume_role_policy = data.aws_iam_policy_document.assume_by_admin.json
}

resource "aws_iam_role_policy" "transform" {
  name   = "transform-access"
  role   = aws_iam_role.transform.id
  policy = data.aws_iam_policy_document.transform.json
}
