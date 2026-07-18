# Remote state backend. Run this ONCE, before anything in envs/.
#
# Chicken-and-egg: Terraform state needs somewhere to live, and that somewhere
# is itself Terraform. So this root uses LOCAL state and is committed
# (bootstrap/terraform.tfstate). It is tiny, changes ~never, and losing it only
# means re-importing two resources.
#
#   cd infrastructure/terraform/bootstrap
#   terraform init && terraform apply
#
# Then envs/dev/backend.tf points at the bucket this creates.
#
# Why remote state at all: local state means one laptop is the source of truth
# for production infrastructure, and two people applying at once silently
# corrupt it. The DynamoDB lock makes concurrent applies fail loudly instead.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "video-compiler"
      ManagedBy = "terraform"
      Component = "bootstrap"
    }
  }
}

variable "aws_region" {
  description = "AWS region for state storage."
  type        = string
  default     = "ap-south-1"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform state."
  type        = string
  # Account 005572111409. Must match envs/dev/backend.tf.
  default = "video-compiler-tfstate-005572111409"
}

# ── State bucket ───────────────────────────────────────

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  # State is the map of everything you own. Deleting it does not delete the
  # infrastructure -- it deletes your ability to manage or destroy it.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled" # lets you roll back a corrupted state file
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# State contains database passwords and secret ARNs in plaintext. It must never
# be public.
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Lock table ─────────────────────────────────────────

resource "aws_dynamodb_table" "lock" {
  name         = "video-compiler-tf-lock"
  billing_mode = "PAY_PER_REQUEST" # a few cents/month at this volume
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

# ── Outputs ────────────────────────────────────────────

output "state_bucket" {
  description = "Put this in envs/*/backend.tf"
  value       = aws_s3_bucket.state.id
}

output "lock_table" {
  value = aws_dynamodb_table.lock.name
}
