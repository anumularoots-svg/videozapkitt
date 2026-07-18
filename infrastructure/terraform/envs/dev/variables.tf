variable "project" {
  type    = string
  default = "video-compiler"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  description = "ap-south-1 (Mumbai) is closest to an India-first audience."
  type        = string
  default     = "ap-south-1"
}

variable "github_repo" {
  description = "owner/repo for OIDC trust. No default -- must be set correctly or the deploy role trusts the wrong repo."
  type        = string
}

# ── Sizing (dev defaults are the cheap tier) ───────────

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "gpu_instance_types" {
  description = "24GB A10G g5s for Phase 0 (Wan 1.3B). Phase 6 swaps in g5.12xlarge for 14B."
  type        = list(string)
  default     = ["g5.xlarge", "g5.2xlarge", "g4dn.xlarge"]
}

variable "gpu_ami_id" {
  description = "Baked AMI from Packer. null = Deep Learning AMI + ~35GB first-boot download."
  type        = string
  default     = null
}

variable "max_gpu_workers" {
  description = "Ceiling on concurrent GPUs. The runaway-cost backstop."
  type        = number
  default     = 2 # dev: keep it low
}

# ── Images (CI overrides these per deploy) ─────────────

variable "api_image" {
  description = "ECR image URI for the API. Placeholder ok on first apply."
  type        = string
  default     = "public.ecr.aws/docker/library/busybox:latest"
}

variable "worker_image" {
  description = "ECR image URI for the GPU worker. Must be CUDA-based once real."
  type        = string
  default     = "public.ecr.aws/docker/library/busybox:latest"
}

# ── Secrets & TLS ──────────────────────────────────────

variable "llm_api_key" {
  description = "Groq API key. From a CI secret / local tfvars, never committed."
  type        = string
  sensitive   = true
  default     = ""
}

variable "certificate_arn" {
  description = "ACM cert for HTTPS. null = plain HTTP on the ALB (dev, no domain)."
  type        = string
  default     = null
}

# ── Ops ────────────────────────────────────────────────

variable "alarm_emails" {
  description = "Budget + alarm recipients. Each confirms an SNS email once."
  type        = list(string)
  default     = []
}

variable "monthly_budget_usd" {
  description = "Spend ceiling; forecast alert at 80%. The GPU-cost backstop."
  type        = string
  default     = "75"
}
