# dev environment — composition root.
#
# Wires the modules together. Read top to bottom, it is the whole system:
#   network -> data + queue -> api + gpu_workers -> observability -> github_oidc
#
# Dependency direction is deliberate. api and gpu_workers are CLIENTS of data
# (they hold the SGs data grants access to), so data takes client SG ids as a
# second-pass input via aws_vpc_security_group_ingress_rule inside the module,
# breaking what would otherwise be a cycle.

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

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  azs = ["${var.aws_region}a", "${var.aws_region}b"]
}

# ── Network ────────────────────────────────────────────

module "network" {
  source = "../../modules/network"

  project            = var.project
  environment        = var.environment
  aws_region         = var.aws_region
  availability_zones = local.azs
  single_nat_gateway = true # dev: one NAT, ~$32/mo
}

# ── Application secrets ─────────────────────────────────
#
# App-level secrets (LLM key, JWT/secret keys). The value is provided once via
# tfvars; ECS reads it at task start. Kept out of the container image and out of
# env files in the repo.

resource "random_password" "secret_key" {
  length  = 48
  special = false
}

resource "random_password" "jwt_secret" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project}-${var.environment}/app"
  recovery_window_in_days = 0 # dev: allow same-day recreate
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    secret_key  = random_password.secret_key.result
    jwt_secret  = random_password.jwt_secret.result
    llm_api_key = var.llm_api_key # Groq key, from tfvars/CI secret
  })
}

# ── Data ───────────────────────────────────────────────

module "data" {
  source = "../../modules/data"

  project     = var.project
  environment = var.environment
  account_id  = data.aws_caller_identity.current.account_id

  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids

  # api + gpu_workers SGs, allowed to reach Postgres/Redis.
  client_security_group_ids = [
    module.api.task_security_group_id,
    module.gpu_workers.security_group_id,
  ]

  db_instance_class = var.db_instance_class
  redis_node_type   = var.redis_node_type
}

# ── Queue ──────────────────────────────────────────────

module "queue" {
  source = "../../modules/queue"

  project     = var.project
  environment = var.environment

  alarm_topic_arns = [module.observability.alarm_topic_arn]
}

# ── API ────────────────────────────────────────────────

module "api" {
  source = "../../modules/api"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  vpc_id             = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  private_subnet_ids = module.network.private_subnet_ids

  # Placeholder until CI pushes the first real image. ECS won't run a task that
  # can't pull, but terraform apply succeeds -- the service stabilises once CI
  # pushes and rolls it. desired_count changes are ignored, so this is safe.
  api_image       = var.api_image
  desired_count   = 1
  certificate_arn = var.certificate_arn

  video_queue_url   = module.queue.video_queue_url
  video_queue_arn   = module.queue.video_queue_arn
  assets_bucket     = module.data.assets_bucket
  assets_bucket_arn = module.data.assets_bucket_arn
  db_secret_arn     = module.data.db_secret_arn
  app_secret_arn    = aws_secretsmanager_secret.app.arn
  redis_url         = module.data.redis_url
}

# ── GPU workers ────────────────────────────────────────

module "gpu_workers" {
  source = "../../modules/gpu_workers"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids

  instance_types = var.gpu_instance_types # Phase 0: 24GB A10G g5s
  ami_id         = var.gpu_ami_id         # null until Packer bakes one
  max_workers    = var.max_gpu_workers

  worker_image = var.worker_image

  video_queue_url  = module.queue.video_queue_url
  video_queue_arn  = module.queue.video_queue_arn
  video_queue_name = module.queue.video_queue_name

  assets_bucket     = module.data.assets_bucket
  assets_bucket_arn = module.data.assets_bucket_arn
  db_secret_arn     = module.data.db_secret_arn
  app_secret_arn    = aws_secretsmanager_secret.app.arn
  redis_url         = module.data.redis_url
}

# ── Observability ──────────────────────────────────────

module "observability" {
  source = "../../modules/observability"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  alarm_emails       = var.alarm_emails
  monthly_budget_usd = var.monthly_budget_usd

  gpu_asg_name     = module.gpu_workers.asg_name
  video_queue_name = module.queue.video_queue_name
  video_dlq_name   = "${var.project}-${var.environment}-video-dlq"
  ecs_cluster_name = module.api.cluster_name
  ecs_service_name = module.api.service_name
}

# ── GitHub OIDC ────────────────────────────────────────

module "github_oidc" {
  create_oidc_provider = false
  source = "../../modules/github_oidc"

  project     = var.project
  environment = var.environment
  github_repo = var.github_repo

  # dev deploys from main. plan-on-PR uses a separate, read-only path.
  allowed_subjects = ["ref:refs/heads/main", "environment:${var.environment}"]

  ecr_repository_arns = [
    module.api.ecr_api_arn,
    module.api.ecr_worker_arn,
  ]

  passable_role_arns = [
    module.api.task_role_arn,
    module.api.execution_role_arn,
    module.gpu_workers.role_arn,
  ]

  grant_terraform_admin = true # dev: same role plans+applies. prod: split.
}
