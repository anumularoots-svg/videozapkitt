variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "alarm_emails" {
  description = "Addresses for budget + alarm notifications. Each must confirm the SNS subscription email."
  type        = list(string)
  default     = []
}

variable "monthly_budget_usd" {
  description = "Monthly spend ceiling. The forecast alert fires at 80%. Set it to a number that would genuinely alarm you."
  type        = string
  default     = "100"
}

# ── Dashboard wiring ───────────────────────────────────

variable "gpu_asg_name" {
  type = string
}

variable "video_queue_name" {
  type = string
}

variable "video_dlq_name" {
  type = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "ecs_service_name" {
  type = string
}
