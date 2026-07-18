# Observability: alarm topic, budget guard, dashboard.
#
# The budget alarm is not optional decoration. This stack can autoscale GPUs, so
# a stuck queue or a runaway retry loop can spend real money while nobody is
# looking. The budget is the backstop that emails you before the bill does.

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

# ── Alarm topic ────────────────────────────────────────

resource "aws_sns_topic" "alarms" {
  name = "${local.name}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.alarm_emails)

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = each.value
  # Each address gets a confirmation email that must be clicked, or it receives
  # nothing. Expected on first apply.
}

# ── Budget ─────────────────────────────────────────────

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Warn at 80% of forecast, page at 100% of actual. The forecast alert is the
  # useful one -- it fires while there is still time to intervene.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alarm_emails
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alarm_emails
  }
}

# ── Dashboard ──────────────────────────────────────────
#
# The operational picture on one screen: how many GPUs are up, how deep the
# queue is, how old the oldest job is. This is the "why is the bill high / why
# is my video stuck" view before the full admin dashboard exists (ARCH §9).

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = local.name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "GPU workers running (should be 0 when idle)"
          region = var.aws_region
          metrics = [
            ["AWS/AutoScaling", "GroupInServiceInstances", "AutoScalingGroupName", var.gpu_asg_name]
          ]
          period = 60
          stat   = "Maximum"
          yAxis  = { left = { min = 0 } }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Video queue depth & oldest job age"
          region = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.video_queue_name],
            [".", "ApproximateAgeOfOldestMessage", ".", ".", { yAxis = "right" }]
          ]
          period = 60
          stat   = "Maximum"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "API service (CPU / memory %)"
          region = var.aws_region
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name],
            [".", "MemoryUtilization", ".", ".", ".", "."]
          ]
          period = 60
          stat   = "Average"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Dead-letter queue (should stay 0)"
          region = var.aws_region
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.video_dlq_name]
          ]
          period = 300
          stat   = "Maximum"
        }
      },
    ]
  })
}
