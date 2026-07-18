# GPU worker fleet. Spot instances, scale-to-zero, driven by SQS depth.
#
# THIS IS THE COST CENTER. Everything else in this stack is rounding error next
# to an idle GPU. Two rules follow:
#
#   1. min_size = 0. Not "small" -- zero. An idle g5.xlarge is ~$0.30/hr on spot
#      (~$220/mo) doing nothing.
#   2. Scale on QUEUE DEPTH, not CPU. A GPU rendering video may show low CPU;
#      CPU-based scaling would shut a worker down mid-render.
#
# The old ASG set desired_capacity = 0 with NO scaling policy attached. That is
# not scale-to-zero -- it is a fleet that never starts. Jobs would queue forever.
#
# Instance sizing follows the Phase 0 decision (Wan 1.3B, ~8.2GB VRAM):
#   g5.xlarge   A10G 24GB  -> fits 1.3B with room for FLUX + Stable Audio
#   g5.12xlarge 4x A10G    -> what the 14B tier (40-48GB @480p) would need
# Changing var.instance_types is the whole of the Phase 6 tier change.
#
# ⚠️ QUOTA: new accounts often have a G-instance vCPU limit of 0, for on-demand
# AND spot separately. terraform apply succeeds and instances silently never
# launch. Request the increase before you need it -- it takes days.

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
  name = "${var.project}-${var.environment}-gpu"
}

# Falls back to the AWS Deep Learning AMI when no baked AMI is supplied.
# The DLAMI has drivers but NOT the model weights, so first boot downloads
# ~35GB before it can render anything. Fine to start; Packer
# (infrastructure/packer/) bakes them in, which is what makes scale-up fast
# enough for scale-to-zero to be usable rather than just cheap.
data "aws_ami" "deep_learning" {
  count = var.ami_id == null ? 1 : 0

  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# ── Security group ─────────────────────────────────────

resource "aws_security_group" "worker" {
  name        = local.name
  description = "GPU workers. Egress only -- nothing connects to a worker."
  vpc_id      = var.vpc_id

  tags = { Name = local.name }
}

# No ingress rules at all. Workers pull from SQS and push to S3; nothing needs
# to reach in. Use SSM Session Manager to get a shell, not SSH.
resource "aws_vpc_security_group_egress_rule" "worker_all" {
  security_group_id = aws_security_group.worker.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Model weights, ECR, S3, SQS"
}

# ── IAM ────────────────────────────────────────────────

resource "aws_iam_role" "worker" {
  name = "${local.name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_instance_profile" "worker" {
  name = "${local.name}-profile"
  role = aws_iam_role.worker.name
}

resource "aws_iam_role_policy" "worker" {
  name = "${local.name}-policy"
  role = aws_iam_role.worker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ConsumeVideoQueue"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility",
        ]
        Resource = var.video_queue_arn
      },
      {
        Sid    = "ReadWriteAssets"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
        ]
        Resource = "${var.assets_bucket_arn}/*"
      },
      {
        Sid      = "ListAssets"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.assets_bucket_arn
      },
      {
        Sid      = "ReadDbCredentials"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.db_secret_arn
      },
      {
        Sid      = "ReadAppSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.app_secret_arn
      },
      {
        Sid    = "PullImages"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
        ]
        Resource = "*"
      },
      {
        Sid    = "Telemetry"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = "*"
      },
    ]
  })
}

# Shell access without opening port 22 or managing keys.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# ── Launch template ────────────────────────────────────

resource "aws_launch_template" "worker" {
  name_prefix = "${local.name}-"
  image_id    = var.ami_id != null ? var.ami_id : data.aws_ami.deep_learning[0].id

  iam_instance_profile {
    arn = aws_iam_instance_profile.worker.arn
  }

  # Just the worker SG. data grants it Postgres/Redis ingress via its
  # client_security_group_ids -- a second SG here would only risk a cycle.
  vpc_security_group_ids = [aws_security_group.worker.id]

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      # Model weights are large: FLUX ~24GB + Wan 1.3B ~6GB + Stable Audio ~5GB,
      # plus scratch render space. 40GB will not fit them.
      volume_size           = var.root_volume_gb
      volume_type           = "gp3"
      throughput            = 250 # loading weights is throughput-bound
      delete_on_termination = true
      encrypted             = true
    }
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required" # IMDSv2 only
  }

  monitoring {
    enabled = true
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    aws_region       = var.aws_region
    video_queue_url  = var.video_queue_url
    assets_bucket    = var.assets_bucket
    db_secret_arn    = var.db_secret_arn
    app_secret_arn   = var.app_secret_arn
    redis_url        = var.redis_url
    worker_image     = var.worker_image
    log_group        = aws_cloudwatch_log_group.worker.name
    model_cache_path = var.model_cache_path
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name      = local.name
      Component = "gpu-worker"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/ec2/${local.name}"
  retention_in_days = var.environment == "prod" ? 30 : 7
}

# ── Auto Scaling Group ─────────────────────────────────

resource "aws_autoscaling_group" "worker" {
  name                = local.name
  vpc_zone_identifier = var.private_subnet_ids

  min_size = 0 # THE point. Not "small". Zero.
  max_size = var.max_workers

  # Never hardcode desired_capacity alongside scaling policies -- Terraform and
  # the policies would fight, reverting scale-up on every apply.
  desired_capacity = null

  # A GPU that is up but not registered still bills. Fail fast.
  health_check_type         = "EC2"
  health_check_grace_period = var.health_check_grace_period

  # Give a worker time to finish the clip it is on before termination.
  default_instance_warmup = 300

  capacity_rebalance = true # act on spot interruption warnings

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = var.on_demand_percentage
      spot_allocation_strategy                 = "price-capacity-optimized"
    }

    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.worker.id
        version            = "$Latest"
      }

      # More types = fewer spot interruptions. All must fit the model tier's
      # VRAM: every g5 here has a 24GB A10G.
      dynamic "override" {
        for_each = var.instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }

  tag {
    key                 = "Name"
    value               = local.name
    propagate_at_launch = true
  }

  timeouts {
    delete = "20m"
  }
}

# ── Scaling ────────────────────────────────────────────
#
# Target tracking on "messages per instance". At target = 1, N queued jobs pull
# up N workers, and an empty queue tracks back to zero on its own.
#
# The metric math is what makes 0 reachable: a raw SQS metric cannot express
# "backlog per instance", and CPU-based tracking would scale down a busy GPU.

resource "aws_autoscaling_policy" "queue_depth" {
  name                   = "${local.name}-queue-depth"
  autoscaling_group_name = aws_autoscaling_group.worker.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    target_value = var.messages_per_worker

    # Scale-in is deliberately slow: tearing down a worker mid-render wastes the
    # GPU minutes already spent on that video.
    disable_scale_in = false

    customized_metric_specification {
      metrics {
        id    = "backlog"
        label = "Messages waiting"

        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"

            dimensions {
              name  = "QueueName"
              value = var.video_queue_name
            }
          }
          stat = "Average"
        }

        return_data = false
      }

      metrics {
        id    = "capacity"
        label = "Running workers"

        metric_stat {
          metric {
            namespace   = "AWS/AutoScaling"
            metric_name = "GroupInServiceInstances"

            dimensions {
              name  = "AutoScalingGroupName"
              value = local.name
            }
          }
          stat = "Average"
        }

        return_data = false
      }

      metrics {
        id = "backlog_per_worker"
        # MAX(capacity, 1) avoids divide-by-zero at zero workers -- without it
        # the metric goes blank exactly when it must trigger the first scale-up,
        # and the fleet never leaves zero.
        expression  = "backlog / MAX([capacity, 1])"
        label       = "Backlog per worker"
        return_data = true
      }
    }
  }
}
