variable "env" {
  description = "環境の名前(dev / prod。test は作らない)"
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env は dev / prod のどちらかにしてください。"
  }
}

variable "permissions_boundary" {
  description = "ingest と transform のロールに付ける権限境界の ARN。dev は null(枠なし)、prod は ecom-prod-boundary(ADR 0017)"
  type        = string
  default     = null
}

variable "transform_oidc_provider_arn" {
  description = "transform ロールを OIDC で借りてよい GitHub の OIDC プロバイダの ARN。null なら OIDC は許可しない(dev は null。ADR 0017)"
  type        = string
  default     = null
}

variable "transform_oidc_sub" {
  description = "transform ロールを OIDC で借りてよい sub(完全一致。例: repo:<owner>@<id>/<repo>@<id>:environment:prod)。transform_oidc_provider_arn とセットで渡す"
  type        = string
  default     = null
}

variable "admin_user_name" {
  description = "ロールを借りてよい管理者の IAM ユーザー名"
  type        = string
}
