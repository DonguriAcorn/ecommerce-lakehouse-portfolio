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
    }
  }
}

# 環境の定義(S3、Glue、Athena、IAM)は、dev と同じモジュールを使い、env だけを変える
module "env" {
  source          = "../../modules/lakehouse_env"
  env             = "prod"
  admin_user_name = "portfolio-admin"
}
