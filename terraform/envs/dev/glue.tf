locals {
  glue_databases = {
    bronze = "s3://${aws_s3_bucket.lake.bucket}/raw/"
    silver = "s3://${aws_s3_bucket.lake.bucket}/iceberg/silver/"
    gold   = "s3://${aws_s3_bucket.lake.bucket}/iceberg/gold/"
  }
}

resource "aws_glue_catalog_database" "layers" {
  for_each     = local.glue_databases
  name         = "ecom_${local.env}_${each.key}"
  location_uri = each.value
}
