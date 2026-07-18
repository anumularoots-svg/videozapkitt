output "deploy_role_arn" {
  description = "Set as AWS_DEPLOY_ROLE_ARN in GitHub. aws-actions/configure-aws-credentials assumes it via OIDC."
  value       = aws_iam_role.deploy.arn
}
