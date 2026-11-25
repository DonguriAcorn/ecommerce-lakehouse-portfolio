variable "budget_alert_email" {
  description = "Budgets の通知を受け取るメールアドレス"
  type        = string
  sensitive   = true
}

# GitHub のリポジトリ名(<owner>/<repo>)。OIDC の sub の照合に使う(ADR 0017)
variable "github_repo" {
  description = "GitHub のリポジトリ名(<owner>/<repo>)"
  type        = string
  default     = "DonguriAcorn/ecommerce-lakehouse-portfolio"
}
