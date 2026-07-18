# Stateful layer: RDS Postgres, ElastiCache Redis, S3 assets.
#
# Three things the previous main.tf got wrong, fixed here:
#   1. RDS had no subnet group and no security group -> it landed in the default
#      VPC, publicly addressable. It is now private-subnet-only and reachable
#      only from the app security groups.
#   2. The DB password came from a tfvars variable, so it lived in plaintext in
#      state and in whatever file held it. It is now generated and stored in
#      Secrets Manager; nobody ever types it.
#   3. No lifecycle rules on S3, so every intermediate render (keyframes, per-
#      scene clips, voice wavs) accumulated forever. A 60s video produces
#      hundreds of MB of scratch. Scratch now expires.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

locals {
  name = "${var.project}-${var.environment}"
}

# ── Security groups ────────────────────────────────────

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "Postgres. Ingress only from app tiers."
  vpc_id      = var.vpc_id

  tags = { Name = "${local.name}-rds" }
}

resource "aws_security_group" "redis" {
  name        = "${local.name}-redis"
  description = "Redis. Ingress only from app tiers."
  vpc_id      = var.vpc_id

  tags = { Name = "${local.name}-redis" }
}

# Rules are separate resources so callers can attach their own client SGs
# without a cycle (api -> data -> api).
resource "aws_vpc_security_group_ingress_rule" "rds_from_clients" {
  for_each = toset(var.client_security_group_ids)

  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = each.value
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Postgres from app tier"
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_clients" {
  for_each = toset(var.client_security_group_ids)

  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = each.value
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  description                  = "Redis from app tier"
}

# ── RDS ────────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db"
  subnet_ids = var.private_subnet_ids

  tags = { Name = "${local.name}-db" }
}

resource "random_password" "db" {
  length = 32
  # RDS rejects several punctuation characters in master passwords; this set is
  # accepted. Length carries the entropy regardless.
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db" {
  name        = "${local.name}/db-credentials"
  description = "Postgres master credentials. Read by ECS tasks at boot."

  # Dev gets same-day deletion so a destroy/apply cycle isn't blocked by a
  # 30-day name reservation. Prod keeps the default recovery window.
  recovery_window_in_days = var.environment == "dev" ? 0 : 30
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    dbname   = var.db_name
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    url      = "postgresql+asyncpg://${var.db_username}:${urlencode(random_password.db.result)}@${aws_db_instance.main.endpoint}/${var.db_name}"
  })
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name}-db"
  engine         = "postgres"
  engine_version = var.postgres_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 4 # autoscale headroom
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false # the point

  backup_retention_period = var.environment == "prod" ? 14 : 1
  skip_final_snapshot     = var.environment != "prod"
  final_snapshot_identifier = (
    var.environment == "prod" ? "${local.name}-final-${var.snapshot_suffix}" : null
  )
  deletion_protection = var.environment == "prod"

  performance_insights_enabled = var.environment == "prod"
  auto_minor_version_upgrade   = true

  tags = { Name = "${local.name}-db" }
}

# ── ElastiCache ────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name}-redis"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${local.name}-redis"
  engine               = "redis"
  engine_version       = var.redis_version
  node_type            = var.redis_node_type
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  tags = { Name = "${local.name}-redis" }
}

# ── S3 assets ──────────────────────────────────────────

resource "aws_s3_bucket" "assets" {
  bucket = "${local.name}-assets-${var.account_id}"
  tags   = { Name = "${local.name}-assets" }
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket = aws_s3_bucket.assets.id

  # Finished videos are served via CloudFront OAC, never by making the bucket
  # public.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id

  # Scratch: keyframes, per-scene clips, voice wavs, stitched intermediates.
  # Valuable for debugging a render, worthless a week later. Hundreds of MB per
  # video -- this rule is the difference between a flat and a climbing S3 bill.
  rule {
    id     = "expire-scratch"
    status = "Enabled"

    filter {
      prefix = "scratch/"
    }

    expiration {
      days = var.scratch_retention_days
    }
  }

  # Finished videos: keep, but stop paying Standard rates for old ones nobody
  # streams.
  rule {
    id     = "tier-finished-videos"
    status = "Enabled"

    filter {
      prefix = "videos/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7 # otherwise failed uploads bill forever, invisibly
    }
  }
}
