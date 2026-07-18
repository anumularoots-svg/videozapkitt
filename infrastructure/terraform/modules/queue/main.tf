# SQS work queues.
#
# The queue is not just plumbing here -- its depth is the autoscaling signal for
# the GPU fleet (see modules/gpu_workers). Messages visible means work waiting
# means bring up a GPU; empty means scale to zero.
#
# Every queue has a dead-letter queue. Without one, a message that crashes its
# consumer is redelivered until it expires, and a single poison job can hold a
# GPU busy for its entire retention window. That is a real bill.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  name = "${var.project}-${var.environment}"
}

# ── Dead-letter queue ──────────────────────────────────

resource "aws_sqs_queue" "video_dlq" {
  name = "${local.name}-video-dlq"

  # Keep failures long enough to actually investigate them.
  message_retention_seconds = 1209600 # 14 days

  tags = { Name = "${local.name}-video-dlq" }
}

# ── Main queue ─────────────────────────────────────────

resource "aws_sqs_queue" "video" {
  name = "${local.name}-video"

  # A 60s video is 12+ clips of GPU work. The timeout must exceed the slowest
  # realistic job or SQS redelivers it to a second worker while the first is
  # still rendering -- paying twice for one video.
  visibility_timeout_seconds = var.visibility_timeout_seconds

  message_retention_seconds = 86400 # 1 day
  receive_wait_time_seconds = 20    # long polling: fewer empty receives, lower cost

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.video_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = { Name = "${local.name}-video" }
}

resource "aws_sqs_queue_redrive_allow_policy" "video_dlq" {
  queue_url = aws_sqs_queue.video_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.video.arn]
  })
}

# ── Alarms ─────────────────────────────────────────────

# Anything in the DLQ means a job failed every retry. At Phase 4 volumes that
# should be rare enough to page on.
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${local.name}-video-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "A video job exhausted its retries. Inspect the DLQ."
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.video_dlq.name
  }

  alarm_actions = var.alarm_topic_arns
}

# Work waiting with no GPU running for 30+ minutes means the scaling policy or
# the ASG is broken -- the failure mode where jobs silently never run.
resource "aws_cloudwatch_metric_alarm" "backlog_stuck" {
  alarm_name          = "${local.name}-video-backlog-stuck"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 6
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = var.stuck_backlog_seconds
  alarm_description   = "Oldest queued job is aging. GPU workers may not be scaling up."
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.video.name
  }

  alarm_actions = var.alarm_topic_arns
}
