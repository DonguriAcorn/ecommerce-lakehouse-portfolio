variable "budget_alert_email" {
  description = "Budgets の通知を受け取るメールアドレス"
  type        = string
  sensitive   = true
}

# OIDC の sub に入るリポジトリの表記(<owner>@<owner_id>/<repo>@<repo_id>)(ADR 0017)
# 番号は変わらない ID。同じ名前で作り直されたリポジトリに、なりすまされないようにする
variable "github_repo" {
  description = "OIDC の sub に入るリポジトリの表記(<owner>@<owner_id>/<repo>@<repo_id>)"
  type        = string
  default     = "DonguriAcorn@72342300/ecommerce-lakehouse-portfolio@1426844930"
}
