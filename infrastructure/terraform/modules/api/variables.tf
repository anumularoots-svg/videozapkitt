variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  description = "ALB only."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Tasks. No public IPs."
  type        = list(string)
}

# ── Task sizing ────────────────────────────────────────

variable "api_image" {
  description = "ECR image URI. CI replaces this per deploy; the service ignores drift."
  type        = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "task_cpu" {
  description = "The API only validates, writes a row and enqueues. It never renders."
  type        = number
  default     = 512
}

variable "task_memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  description = "1 for dev. 2+ for prod so a deploy has no gap."
  type        = number
  default     = 1
}

# ── TLS ────────────────────────────────────────────────

variable "certificate_arn" {
  description = <<-EOT
    ACM cert for HTTPS. null means the ALB serves plain HTTP on :80 -- acceptable
    for a dev box with no domain, never for anything holding a real JWT.
  EOT
  type        = string
  default     = null
}

# ── Wiring ─────────────────────────────────────────────

variable "video_queue_url" {
  type = string
}

variable "video_queue_arn" {
  type = string
}

variable "assets_bucket" {
  type = string
}

variable "assets_bucket_arn" {
  type = string
}

variable "db_secret_arn" {
  type = string
}

variable "app_secret_arn" {
  type = string
}

variable "redis_url" {
  type = string
}
