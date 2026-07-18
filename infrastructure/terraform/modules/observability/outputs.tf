output "alarm_topic_arn" {
  description = "Wire into queue module's alarm_topic_arns so DLQ/backlog alarms notify here."
  value       = aws_sns_topic.alarms.arn
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.main.dashboard_name
}
