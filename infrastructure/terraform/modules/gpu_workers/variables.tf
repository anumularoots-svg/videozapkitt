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

variable "private_subnet_ids" {
  description = "Workers need NAT egress for ECR and (if unbaked) model weights."
  type        = list(string)
}

# ── Instance tier ──────────────────────────────────────

variable "instance_types" {
  description = <<-EOT
    Ordered by preference; the ASG picks whichever spot capacity is cheapest.
    All must satisfy the model tier's VRAM.

    Phase 0 = Wan 1.3B (~8.2GB) -> any 24GB A10G g5 fits.
    Phase 6 = Wan 14B (40-48GB @480p) -> needs g5.12xlarge or A100. Changing
    this list IS the tier change; nothing else moves.
  EOT
  type        = list(string)
  default     = ["g5.xlarge", "g5.2xlarge", "g4dn.xlarge"]
}

variable "ami_id" {
  description = <<-EOT
    Baked AMI from infrastructure/packer/ with model weights preloaded.
    null falls back to the AWS Deep Learning AMI, which has drivers but no
    weights -- first job then downloads ~35GB, making every scale-up 15+ min.
    Fine for a first apply; bake before relying on scale-to-zero.
  EOT
  type        = string
  default     = null
}

variable "root_volume_gb" {
  description = "FLUX ~24GB + Wan ~6GB + Stable Audio ~5GB + render scratch. 40 will not fit."
  type        = number
  default     = 120
}

variable "model_cache_path" {
  description = "HF_HOME inside the worker. Must match the Packer bake path."
  type        = string
  default     = "/opt/models"
}

# ── Scaling ────────────────────────────────────────────

variable "max_workers" {
  description = "Ceiling on concurrent GPUs. The backstop against a runaway queue draining the budget."
  type        = number
  default     = 4
}

variable "messages_per_worker" {
  description = "Target backlog per worker. 1 = one GPU per queued video."
  type        = number
  default     = 1
}

variable "on_demand_percentage" {
  description = <<-EOT
    Percent of capacity above base on on-demand. 0 = all spot (~70% cheaper,
    can be interrupted with 2 min notice; SQS redelivers, so a video is delayed
    rather than lost). Raise for prod if interruptions hurt.
  EOT
  type        = number
  default     = 0
}

variable "health_check_grace_period" {
  description = "Boot + model load time before health checks count. Too low and the ASG kills workers mid-warmup."
  type        = number
  default     = 600
}

# ── Wiring ─────────────────────────────────────────────

variable "video_queue_url" {
  type = string
}

variable "video_queue_arn" {
  type = string
}

variable "video_queue_name" {
  description = "CloudWatch dimension for the scaling metric."
  type        = string
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

variable "worker_image" {
  description = "ECR image URI. Must be a CUDA-based image -- python:slim has no GPU runtime."
  type        = string
}
