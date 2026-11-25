# ============================================================
# ecom-ci-dbt: GitHub Actions の PR で dbt build を打つロール(ADR 0017)
# 書けるのは、練習用の Glue DB(ecom_ci_silver / ecom_ci_gold)と、S3 の iceberg/ci/ だけ
# ============================================================

locals {
  # CI が使う lake バケットは dev のもの(Bronze を読むため)。prod のバケットは、このファイルに出てこない
  dev_lake_bucket = "ecom-lakehouse-dev-${local.account_id}"
  dev_lake_arn    = "arn:aws:s3:::${local.dev_lake_bucket}"

  # 練習用の Glue DB の ARN と、その中のテーブルの ARN(下の for_each の DB から作る)
  ci_glue_db_arns    = [for d in aws_glue_catalog_database.ci : d.arn]
  ci_glue_table_arns = [for d in aws_glue_catalog_database.ci : "${local.glue_arn_base}:table/${d.name}/*"]
}

# ---------- 練習用の Glue DB(Silver と Gold) ----------
# Terraform が作る。ロールには DB を作る権限を持たせない(ADR 0017)
resource "aws_glue_catalog_database" "ci" {
  for_each    = toset(["silver", "gold"])
  name        = "ecom_ci_${each.key}"
  description = "PR の dbt build 用の練習場所(${each.key})。毎回作り直してよい"
}

# ---------- CI 専用の Athena workgroup ----------
resource "aws_athena_workgroup" "ci" {
  name = "ecom-ci"

  configuration {
    enforce_workgroup_configuration    = true # dbt 側の設定より workgroup の設定を優先させる
    publish_cloudwatch_metrics_enabled = false
    bytes_scanned_cutoff_per_query     = 1073741824 # 1 回のクエリで読める量の上限(1 GiB)

    result_configuration {
      # クエリ結果の置き場は athena-results/ci/ に固定する(dev の結果と混ぜない)
      output_location = "s3://${local.dev_lake_bucket}/athena-results/ci/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# ---------- ロール本体 ----------
resource "aws_iam_role" "ci_dbt" {
  name                 = "ecom-ci-dbt"
  description          = "GitHub Actions PR: dbt build on ecom_ci_* only. ADR 0017" # IAM の説明は英語のみ
  assume_role_policy   = data.aws_iam_policy_document.ci_pr_trust.json              # 信頼ポリシーは plan 用と共通(PR のジョブだけ)
  max_session_duration = 3600
}

# ---------- 権限 ----------
data "aws_iam_policy_document" "ci_dbt" {
  # lake バケットの、見てよい場所だけを一覧できる(raw/ は読む用、ci/ は書く用)
  statement {
    sid       = "ListLakePrefixes"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [local.dev_lake_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "iceberg/ci/*", "athena-results/ci/*"]
    }
  }

  statement {
    sid       = "GetBucketLocation"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation"]
    resources = [local.dev_lake_arn]
  }

  # Bronze は S3 の raw/ を直接読む外部テーブルなので、raw/ の中身を読む(読むだけ)
  statement {
    sid       = "ReadRawObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${local.dev_lake_arn}/raw/*"]
  }

  # 書けるのは iceberg/ci/ と athena-results/ci/ だけ(iceberg/ecom_dev_* などは書けない)
  statement {
    sid    = "ReadWriteCiIcebergAndResults"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "${local.dev_lake_arn}/iceberg/ci/*",
      "${local.dev_lake_arn}/athena-results/ci/*",
    ]
  }

  # クエリを打てるのは ecom-ci の workgroup だけ
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
    resources = [aws_athena_workgroup.ci.arn]
  }

  # dev の Bronze の「定義」を読むだけ(作る・消すは入れない)
  statement {
    sid    = "ReadDevBronzeDefinitions"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "${local.glue_arn_base}:catalog",
      "${local.glue_arn_base}:database/ecom_dev_bronze",
      "${local.glue_arn_base}:table/ecom_dev_bronze/*",
    ]
  }

  # 練習用の2つの DB の中でだけ、テーブルを作る・変える・消す(DB 自体は作れない)
  statement {
    sid    = "ManageCiGlueTables"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:GetTableVersions",   # dbt-athena が、作成後に古いテーブルの版を整理するため(transform と同じ)
      "glue:DeleteTableVersion", # 同じく、古い版を消す(Glue のメタデータだけ)
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:DeletePartition",
      "glue:BatchDeletePartition",
    ]
    resources = concat(
      ["${local.glue_arn_base}:catalog"],
      local.ci_glue_db_arns,
      local.ci_glue_table_arns,
    )
  }
}

# 上の一覧を、ロールに埋め込みのポリシーとして付ける
resource "aws_iam_role_policy" "ci_dbt" {
  name   = "ecom-ci-dbt"
  role   = aws_iam_role.ci_dbt.id
  policy = data.aws_iam_policy_document.ci_dbt.json
}
