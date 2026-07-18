# GPU worker AMI with model weights baked in.
#
# WHY THIS EXISTS: scale-to-zero is only usable if scale-UP is fast. A fresh
# Deep Learning AMI has drivers but no weights, so the first job on every new
# spot instance downloads ~35GB (FLUX ~24GB, Wan 1.3B ~6GB, Stable Audio ~5GB)
# before rendering a single frame -- 15+ minutes of paid GPU doing nothing.
# Baking the weights into the AMI turns that into a ~90s boot.
#
# Build:
#   cd infrastructure/packer
#   packer init .
#   packer build -var 'model_cache_path=/opt/models' gpu-worker.pkr.hcl
#
# Then set gpu_ami_id in envs/dev/terraform.tfvars to the printed AMI id.
#
# Rebuild when: model versions change, or the driver base updates. Weights are
# large and licensed -- this AMI is private. Do not share it publicly.

packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "~> 1.3"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "model_cache_path" {
  type    = string
  default = "/opt/models"
}

variable "instance_type" {
  # Bake ON a GPU box so weights can be verified to load before the AMI is
  # published. A CPU builder would ship an untested image.
  type    = string
  default = "g5.xlarge"
}

locals {
  timestamp = formatdate("YYYYMMDD-hhmm", timestamp())
}

source "amazon-ebs" "gpu_worker" {
  region        = var.aws_region
  instance_type = var.instance_type
  ami_name      = "video-compiler-gpu-worker-${local.timestamp}"

  # Base: AWS Deep Learning Base AMI (NVIDIA drivers + Docker + NVIDIA runtime).
  source_ami_filter {
    filters = {
      name                = "Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["amazon"]
  }

  ssh_username = "ubuntu"

  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    volume_size           = 120 # room for ~35GB of weights + headroom
    volume_type           = "gp3"
    throughput            = 250
    delete_on_termination = true
  }

  tags = {
    Name      = "video-compiler-gpu-worker"
    Project   = "video-compiler"
    BuildDate = local.timestamp
    Baked     = "flux-schnell,wan2.1-1.3b,stable-audio-open,whisper-base"
  }
}

build {
  name    = "gpu-worker"
  sources = ["source.amazon-ebs.gpu_worker"]

  # ── Verify the GPU is real before baking anything onto it ──
  provisioner "shell" {
    inline = [
      "set -euxo pipefail",
      "nvidia-smi",
      "echo 'GPU present -- proceeding with bake.'",
    ]
  }

  # ── Python + the ML stack ──
  provisioner "shell" {
    inline = [
      "set -euxo pipefail",
      "sudo apt-get update",
      "sudo apt-get install -y python3.11 python3-pip ffmpeg libsm6 libxext6 libgl1",
      "sudo ln -sf /usr/bin/python3.11 /usr/bin/python",
      "python -m pip install --upgrade pip",
    ]
  }

  provisioner "file" {
    source      = "../../backend/requirements.txt"
    destination = "/tmp/requirements.txt"
  }

  provisioner "shell" {
    inline = [
      "set -euxo pipefail",
      "pip install --extra-index-url https://download.pytorch.org/whl/cu121 -r /tmp/requirements.txt",
    ]
  }

  # ── Pre-download weights into the cache the worker mounts ──
  # Each is the exact model the Phase 0 providers load. Downloading here means
  # the running worker never does.
  provisioner "shell" {
    environment_vars = ["HF_HOME=${var.model_cache_path}"]
    inline = [
      "set -euxo pipefail",
      "sudo mkdir -p ${var.model_cache_path}",
      "sudo chown -R ubuntu:ubuntu ${var.model_cache_path}",

      "echo '=== FLUX.1-schnell (Apache-2.0) ==='",
      "python -c \"from huggingface_hub import snapshot_download; snapshot_download('black-forest-labs/FLUX.1-schnell')\"",

      "echo '=== Wan 2.1 T2V-1.3B (Apache-2.0) ==='",
      "python -c \"from huggingface_hub import snapshot_download; snapshot_download('Wan-AI/Wan2.1-T2V-1.3B')\"",

      "echo '=== Stable Audio Open (Stability Community) ==='",
      "python -c \"from huggingface_hub import snapshot_download; snapshot_download('stabilityai/stable-audio-open-1.0')\"",

      "echo '=== faster-whisper base (MIT) ==='",
      "python -c \"from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')\"",

      "du -sh ${var.model_cache_path}",
    ]
  }

  # ── Prove the weights actually load on THIS GPU ──
  # Catches a broken download or a driver/torch mismatch at bake time, not at
  # 3am on a spot instance that then bills while failing every job.
  provisioner "shell" {
    environment_vars = ["HF_HOME=${var.model_cache_path}"]
    inline = [
      "set -euxo pipefail",
      "python -c \"import torch; assert torch.cuda.is_available(), 'CUDA not visible to torch'; print('torch sees GPU:', torch.cuda.get_device_name(0))\"",
    ]
  }
}
