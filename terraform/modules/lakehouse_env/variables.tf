variable "env" {
  description = "環境の名前(dev / prod。test は作らない)"
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env は dev / prod のどちらかにしてください。"
  }
}

variable "admin_user_name" {
  description = "ロールを借りてよい管理者の IAM ユーザー名"
  type        = string
}
