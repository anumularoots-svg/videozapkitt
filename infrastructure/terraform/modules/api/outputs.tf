output "alb_dns_name" {
  description = "Hit the API here until a domain is attached."
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "For a Route53 alias record."
  value       = aws_lb.main.zone_id
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "service_name" {
  value = aws_ecs_service.api.name
}

output "task_definition_family" {
  description = "CI registers new revisions against this family."
  value       = aws_ecs_task_definition.api.family
}

output "task_security_group_id" {
  value = aws_security_group.task.id
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "ecr_api_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecr_worker_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "ecr_api_arn" {
  value = aws_ecr_repository.api.arn
}

output "ecr_worker_arn" {
  value = aws_ecr_repository.worker.arn
}

output "log_group" {
  value = aws_cloudwatch_log_group.api.name
}
