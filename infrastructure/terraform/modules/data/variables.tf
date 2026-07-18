variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "account_id" {
  description = "AWS account id, used to make the S3 bucket name globally unique."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  description = "RDS and ElastiCache live here. Never public."
  type        = list(string)
}

variable "client_security_group_ids" {
  description = "SGs allowed to reach Postgres/Redis (API tasks, GPU workers)."
  type        = list(string)
  default     = []
}

# ── Postgres ───────────────────────────────────────────

variable "postgres_version" {
  type    = string
  default = "16.4"
}

variable "db_instance_class" {
  description = "db.t4g.micro is free-tier eligible and fine for dev."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_name" {
  type    = string
  default = "video_compiler"
}

variable "db_username" {
  type    = string
  default = "postgres"
}

variable "snapshot_suffix" {
  description = "Suffix for the prod final snapshot. Must change between destroys."
  type        = string
  default     = "v1"
}

# ── Redis ──────────────────────────────────────────────

variable "redis_version" {
  type    = string
  default = "7.1"
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

# ── S3 ─────────────────────────────────────────────────

variable "scratch_retention_days" {
  description = "How long per-scene intermediates survive. Long enough to debug a render, short enough not to accumulate."
  type        = number
  default     = 7
}
