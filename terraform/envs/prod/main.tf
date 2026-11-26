terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # 状態ファイルの置き場所。dev とは key を変えて、prod 専用のファイルにする
  backend "s3" {
    bucket       = "tfstate-ecom-lakehouse-709a10"
    key          = "envs/prod/terraform.tfstate"
    region       = "ap-northeast-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "ap-northeast-1"

  # 作るリソースすべてに付くタグ(コンソールで、どの環境のものか見分けるため)
  default_tags {
    tags = {
      Project     = "ecommerce-lakehouse-portfolio"
      Environment = "prod"
      ManagedBy   = "terraform"
      DeployCheck = "2026-11-27" # deploy-prod の承認経路を確かめるための印(確認後も残してよい)
    }
  }
}

# global で作った権限境界を、名前で引く(ARN にアカウント ID が入るので、ファイルには書かない)
data "aws_iam_policy" "prod_boundary" {
  name = "ecom-prod-boundary"
}

# global で作った GitHub の OIDC プロバイダを、url で引く
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# 環境の定義(S3、Glue、Athena、IAM)は、dev と同じモジュールを使い、env だけを変える
module "env" {
  source               = "../../modules/lakehouse_env"
  env                  = "prod"
  admin_user_name      = "portfolio-admin"
  permissions_boundary = data.aws_iam_policy.prod_boundary.arn # prod のロールだけに枠を付ける

  # prod の dbt は、承認を通った GitHub Actions(environment:prod)が transform を借りて流す(ADR 0017)
  # sub の番号は global/variables.tf の github_repo と同じ値(変わらない ID。秘密ではない)
  transform_oidc_provider_arn = data.aws_iam_openid_connect_provider.github.arn
  transform_oidc_sub          = "repo:DonguriAcorn@72342300/ecommerce-lakehouse-portfolio@1426844930:environment:prod"
}
