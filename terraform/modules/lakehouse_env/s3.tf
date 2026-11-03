data "aws_caller_identity" "current" {}

locals {
  lake_bucket = "ecom-lakehouse-${var.env}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "lake" {
  bucket = local.lake_bucket
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket = aws_s3_bucket.lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "lake_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.lake.arn,
      "${aws_s3_bucket.lake.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "lake_tls_only" {
  bucket     = aws_s3_bucket.lake.id
  policy     = data.aws_iam_policy_document.lake_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.lake]
}

# バージョニングを有効にする(上書きや削除のたびに、古い版を残す。誤操作から戻すため)
resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  # バージョニングを先に有効にしてから、ルールを入れる(順番を保証する)
  depends_on = [aws_s3_bucket_versioning.lake]

  rule {
    id     = "expire-athena-results"
    status = "Enabled"

    filter {
      prefix = "athena-results/"
    }

    expiration {
      days = 7
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  rule {
    id     = "expire-logs"
    status = "Enabled"

    filter {
      prefix = "logs/"
    }

    expiration {
      days = 90
    }
  }

  rule {
    id     = "expire-quarantine"
    status = "Enabled"

    filter {
      prefix = "quarantine/"
    }

    expiration {
      days = 30
    }
  }

  # 追加: バケット全体で、古い版を 14 日で消す(残し続けると料金が増えるため)
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    # 空の filter は「バケット全体」の意味(raw/ も iceberg/ も含む)
    filter {}

    # 上書きや削除で「古い版」になってから 14 日たったら、実体を削除する
    noncurrent_version_expiration {
      noncurrent_days = 14
    }

    # 実体がすべて消えて、削除マーカーだけが残ったものも掃除する
    expiration {
      expired_object_delete_marker = true
    }
  }
}
