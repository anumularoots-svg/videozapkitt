output "db_endpoint" {
  value = aws_db_instance.main.endpoint
}

output "db_secret_arn" {
  description = "ECS tasks read the connection URL from here. The password is never in tfvars."
  value       = aws_secretsmanager_secret.db.arn
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "redis_url" {
  value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:6379/0"
}

output "assets_bucket" {
  value = aws_s3_bucket.assets.id
}

output "assets_bucket_arn" {
  value = aws_s3_bucket.assets.arn
}

output "assets_bucket_regional_domain_name" {
  description = "CloudFront origin."
  value       = aws_s3_bucket.assets.bucket_regional_domain_name
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}
