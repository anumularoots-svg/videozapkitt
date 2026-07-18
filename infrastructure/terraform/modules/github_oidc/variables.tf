variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "github_repo" {
  description = "owner/repo, e.g. anumularoots-svg/dev-video.zapkitt.com"
  type        = string
}

variable "allowed_subjects" {
  description = <<-EOT
    Which refs of the repo may assume this role. Least privilege for CI.

    Examples:
      "ref:refs/heads/main"        only the main branch
      "environment:dev"            only jobs bound to the dev GH environment
      "pull_request"               PR jobs (plan only -- never grant apply here)

    Never "*": that lets any branch or fork PR assume the role.
  EOT
  type        = list(string)
  default     = ["ref:refs/heads/main"]

  validation {
    condition     = !contains(var.allowed_subjects, "*")
    error_message = "Refusing '*': it lets any ref, including fork PRs, assume the deploy role."
  }
}

variable "create_oidc_provider" {
  description = "True to create the account-wide GitHub OIDC provider; false to reuse an existing one."
  type        = bool
  default     = true
}

variable "ecr_repository_arns" {
  description = "ECR repos this role may push to."
  type        = list(string)
}

variable "passable_role_arns" {
  description = "Exactly the ECS task + execution roles. Scoping iam:PassRole here prevents privilege escalation."
  type        = list(string)
}

variable "grant_terraform_admin" {
  description = "Attach PowerUserAccess so this role can run terraform apply. Only for a role locked to protected refs."
  type        = bool
  default     = false
}
