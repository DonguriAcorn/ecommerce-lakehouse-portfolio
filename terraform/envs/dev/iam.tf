locals {
  account_id     = data.aws_caller_identity.current.account_id
  admin_user_arn = "arn:aws:iam::${local.account_id}:user/portfolio-admin"
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

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "ListRawPrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*"]
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
