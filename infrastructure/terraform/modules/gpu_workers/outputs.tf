output "asg_name" {
  value = aws_autoscaling_group.worker.name
}

output "asg_arn" {
  value = aws_autoscaling_group.worker.arn
}

output "security_group_id" {
  value = aws_security_group.worker.id
}

output "role_arn" {
  value = aws_iam_role.worker.arn
}

output "log_group" {
  value = aws_cloudwatch_log_group.worker.name
}

output "ami_id" {
  description = "AMI actually in use. If this is the DLAMI, weights are NOT baked and scale-up pays ~35GB of downloads."
  value       = aws_launch_template.worker.image_id
}
