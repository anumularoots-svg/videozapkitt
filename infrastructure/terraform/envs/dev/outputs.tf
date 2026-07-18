output "api_url" {
  description = "The API endpoint. HTTP until a cert is attached."
  value       = "http${var.certificate_arn != null ? "s" : ""}://${module.api.alb_dns_name}"
}

output "ecr_api_url" {
  description = "docker push target for the API image."
  value       = module.api.ecr_api_url
}

output "ecr_worker_url" {
  description = "docker push target for the worker image."
  value       = module.api.ecr_worker_url
}

output "ecs_cluster" {
  value = module.api.cluster_name
}

output "ecs_service" {
  value = module.api.service_name
}

output "task_definition_family" {
  value = module.api.task_definition_family
}

output "assets_bucket" {
  value = module.data.assets_bucket
}

output "gpu_asg_name" {
  value = module.gpu_workers.asg_name
}

output "gpu_ami_in_use" {
  description = "If this is the Deep Learning AMI, weights are NOT baked -- scale-up downloads ~35GB."
  value       = module.gpu_workers.ami_id
}

output "dashboard_name" {
  description = "CloudWatch dashboard for GPU count, queue depth, oldest-job age."
  value       = module.observability.dashboard_name
}

output "github_deploy_role_arn" {
  description = "Set as AWS_DEPLOY_ROLE_ARN in GitHub Actions secrets."
  value       = module.github_oidc.deploy_role_arn
}

output "supported_note" {
  value = "Phase 0: English only. Telugu/Hindi (IndicF5) land at Phase 2. See ARCHITECTURE.md."
}
