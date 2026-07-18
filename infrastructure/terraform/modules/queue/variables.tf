variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "visibility_timeout_seconds" {
  description = <<-EOT
    Must exceed the slowest realistic video job, or SQS hands the same job to a
    second worker while the first is still rendering -- paying twice.

    Phase 0 (15s video, Wan 1.3B) runs ~8-10 min. 3600 leaves room for the 60s
    videos of Phase 1 without re-tuning. Revisit if job shape changes.
  EOT
  type        = number
  default     = 3600

  validation {
    condition     = var.visibility_timeout_seconds >= 900
    error_message = "Below 15 minutes a normal video job will be redelivered mid-render."
  }
}

variable "max_receive_count" {
  description = "Deliveries before a message goes to the DLQ. GPU retries are expensive; keep it low."
  type        = number
  default     = 3
}

variable "stuck_backlog_seconds" {
  description = "Oldest-message age that means scaling is broken, not just busy."
  type        = number
  default     = 1800
}

variable "alarm_topic_arns" {
  description = "SNS topics to notify. Empty means alarms exist but page nobody."
  type        = list(string)
  default     = []
}
