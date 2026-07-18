#!/bin/bash
# GPU worker boot script.
#
# Runs on every scale-up, so it is on the critical path for job latency. Keep it
# short. Anything slow here (model downloads, pip installs) belongs in the AMI
# instead -- see infrastructure/packer/.
set -euxo pipefail

exec > >(tee /var/log/worker-boot.log | logger -t worker-boot) 2>&1

echo "=== GPU worker boot: $(date -u +%FT%TZ) ==="

# ── Fail loudly if the GPU is not there ────────────────
# Without this, a driver problem shows up as "jobs are slow" instead of
# "instance is broken", and the ASG happily keeps a useless box running.
if ! nvidia-smi; then
  echo "FATAL: nvidia-smi failed. No usable GPU; refusing to accept work."
  shutdown -h now
  exit 1
fi

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# ── Config ─────────────────────────────────────────────
cat >/etc/video-compiler.env <<EOF
AWS_REGION=${aws_region}
VIDEO_QUEUE_URL=${video_queue_url}
S3_BUCKET=${assets_bucket}
DB_SECRET_ARN=${db_secret_arn}
APP_SECRET_ARN=${app_secret_arn}
REDIS_URL=${redis_url}
CELERY_BROKER_URL=${redis_url}
HF_HOME=${model_cache_path}
GPU_DEVICE=cuda
EOF

# ── Docker + NVIDIA runtime ────────────────────────────
if ! command -v docker >/dev/null; then
  echo "Docker missing from AMI -- installing (slow; bake it instead)."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker info 2>/dev/null | grep -q nvidia; then
  echo "NVIDIA container runtime missing -- installing (slow; bake it instead)."
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey |
    gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list |
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
      >/etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update && apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
fi

# ── Model cache ────────────────────────────────────────
# Baked into the AMI by Packer. If it is empty the worker still runs, but the
# first job pays ~35GB of downloads -- which defeats scale-to-zero, since every
# scale-up would take 15+ minutes before rendering a single frame.
mkdir -p ${model_cache_path}
if [ -z "$(ls -A ${model_cache_path} 2>/dev/null)" ]; then
  echo "WARNING: model cache empty. First job will download ~35GB."
  echo "WARNING: build a baked AMI (infrastructure/packer/) before relying on this."
fi

# ── Pull worker image ──────────────────────────────────
aws ecr get-login-password --region ${aws_region} |
  docker login --username AWS --password-stdin "$(echo ${worker_image} | cut -d/ -f1)"

docker pull ${worker_image}

# ── Run ────────────────────────────────────────────────
# --gpus all is what makes the card visible inside the container.
# --restart unless-stopped: a crashed worker restarts instead of leaving a live
# GPU idle and billing.
docker run -d \
  --name video-worker \
  --restart unless-stopped \
  --gpus all \
  --env-file /etc/video-compiler.env \
  -v ${model_cache_path}:${model_cache_path} \
  -v /tmp/render:/tmp/render \
  --log-driver=awslogs \
  --log-opt awslogs-region=${aws_region} \
  --log-opt awslogs-group=${log_group} \
  --log-opt awslogs-stream="$(ec2-metadata --instance-id | cut -d' ' -f2)" \
  ${worker_image}

echo "=== Worker started: $(date -u +%FT%TZ) ==="

# ── Spot interruption handling ─────────────────────────
# AWS gives a 2-minute warning. Stop accepting NEW work but let the current
# clip finish -- SQS redelivers anything unacked after the visibility timeout,
# so a hard kill loses only the in-flight clip, not the job.
cat >/usr/local/bin/spot-watch.sh <<'WATCH'
#!/bin/bash
while true; do
  TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  if curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
    http://169.254.169.254/latest/meta-data/spot/instance-action | grep -q action; then
    echo "Spot interruption notice -- draining."
    docker stop --time 100 video-worker || true
    exit 0
  fi
  sleep 5
done
WATCH

chmod +x /usr/local/bin/spot-watch.sh
nohup /usr/local/bin/spot-watch.sh >/var/log/spot-watch.log 2>&1 &
