variable "env" {
  description = "環境の名前(dev / test / prod)"
  type        = string

  validation {
    condition     = contains(["dev", "test", "prod"], var.env)
    error_message = "env は dev / test / prod のどれかにしてください。"
  }
}

variable "admin_user_name" {
  description = "ロールを借りてよい管理者の IAM ユーザー名"
  type        = string
}
