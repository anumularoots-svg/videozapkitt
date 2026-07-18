output "vpc_id" {
  value = aws_vpc.main.id
}

output "vpc_cidr" {
  value = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "ALB only."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "ECS tasks, GPU workers, RDS, ElastiCache."
  value       = aws_subnet.private[*].id
}

output "nat_public_ips" {
  description = "Egress IPs. Allowlist these with third parties (e.g. Groq) if needed."
  value       = aws_eip.nat[*].public_ip
}
