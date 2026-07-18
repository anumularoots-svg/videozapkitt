# GitHub Actions -> AWS via OIDC. No long-lived keys.
#
# The alternative is an IAM user's access key stored as a GitHub secret. That
# key does not expire, works from anywhere, and is one leaked log line from a
# full account compromise. OIDC issues a short-lived token per workflow run,
# scoped to THIS repo and (optionally) THIS branch. Nothing to leak.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  name = "${var.project}-${var.environment}-gha"
}

# One OIDC provider per account. If another stack already created it, import it
# rather than declaring a second.
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

# ── Deploy role ────────────────────────────────────────

resource "aws_iam_role" "deploy" {
  name = "${local.name}-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        # The critical line. Without an exact sub match, ANY GitHub repo in the
        # world could assume this role. Locked to this repo, and to specific
        # refs (branches/tags/environments) via var.allowed_subjects.
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            for sub in var.allowed_subjects : "repo:${var.github_repo}:${sub}"
          ]
        }
      }
    }]
  })
}

# ── Permissions ────────────────────────────────────────

# Push images to ECR.
resource "aws_iam_role_policy" "ecr" {
  name = "ecr-push"
  role = aws_iam_role.deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Auth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "Push"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = var.ecr_repository_arns
      },
    ]
  })
}

# Roll the ECS service to a new task definition.
resource "aws_iam_role_policy" "ecs_deploy" {
  name = "ecs-deploy"
  role = aws_iam_role.deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RegisterAndDeploy"
        Effect = "Allow"
        Action = [
          "ecs:RegisterTaskDefinition",
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:UpdateService",
        ]
        Resource = "*" # RegisterTaskDefinition does not support resource scoping
      },
      {
        Sid    = "PassTaskRoles"
        Effect = "Allow"
        # A deploy must pass the task/execution roles to ECS. Scope this to
        # exactly those two roles -- iam:PassRole on "*" would let the deploy
        # role attach ANY role to a task and escalate to admin.
        Action   = ["iam:PassRole"]
        Resource = var.passable_role_arns
      },
    ]
  })
}

# Run terraform plan/apply. Broad by nature -- Terraform manages everything --
# so this role is assumable only from protected refs (see var.allowed_subjects).
resource "aws_iam_role_policy_attachment" "terraform" {
  count = var.grant_terraform_admin ? 1 : 0

  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}
