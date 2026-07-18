# Infrastructure — AWS via Terraform + GitHub Actions

The complete `dev` environment as code. Cloud is AWS, IaC is Terraform, deploys
run from GitHub Actions over OIDC (no stored AWS keys).

## What this provisions

```
                    Internet
                       │
                 ┌─────▼─────┐   public subnets
                 │    ALB    │   (only thing public)
                 └─────┬─────┘
        ┌──────────────▼──────────────┐  private subnets
        │      ECS Fargate (API)      │  CPU-only: validate, enqueue
        └──┬────────┬────────┬────────┘
           │        │        │
      ┌────▼──┐ ┌───▼───┐ ┌──▼────────┐
      │  RDS  │ │ Redis │ │    SQS    │  ← queue depth is the scaling signal
      │(privt)│ │(privt)│ └──┬────────┘
      └───────┘ └───────┘    │
                    ┌─────────▼──────────┐  private subnets
                    │  GPU ASG (spot)    │  min=0, scales on SQS depth
                    │  Wan 1.3B + FLUX   │  → S3 (assets)
                    └────────────────────┘
```

Modules (`infrastructure/terraform/modules/`):

| Module | What | The thing that was wrong before |
|---|---|---|
| network | VPC, public+private subnets ×2 AZ, NAT, S3 endpoint | RDS was on public subnets |
| data | RDS, ElastiCache, S3, Secrets Manager | DB public, password in plaintext, no S3 lifecycle |
| queue | SQS + DLQ + alarms | didn't exist |
| gpu_workers | spot ASG, **scale-to-zero on SQS depth**, spot drain | `desired_capacity=0` with no scaling policy → never started |
| api | ECR, ECS Fargate, ALB, split IAM roles | cluster only — no task def, service, ALB, or roles |
| github_oidc | keyless deploy role, repo-scoped | didn't exist |
| observability | budget alarm, SNS, dashboard | didn't exist |

Everything is `terraform validate`-clean, including the full `envs/dev`
composition. That proves the wiring type-checks; it does **not** prove a live
`apply` succeeds — see "What is verified" at the bottom.

---

## First-time setup

### 0. Prerequisites
- AWS account + admin credentials for the first apply
- Terraform ≥ 1.9, configured AWS CLI
- **GPU quota**: request a G-instance vCPU increase NOW (Service Quotas →
  EC2 → "All G and VG Spot Instance Requests"). New accounts sit at 0 and the
  ASG will silently launch nothing until this clears. It takes days.

### 1. Remote state (once per account)
```bash
cd infrastructure/terraform/bootstrap
terraform init
terraform apply -var state_bucket_name=video-compiler-tfstate-<unique>
```
Copy the printed `state_bucket` into `envs/dev/backend.tf`.

### 2. Configure dev
```bash
cd ../envs/dev
cp terraform.tfvars.example terraform.tfvars
# set github_repo and alarm_emails; export TF_VAR_llm_api_key for the Groq key
terraform init
terraform apply
```

First apply creates everything with placeholder container images (busybox). The
API won't serve real traffic yet — that's the next step. Nothing renders until
an image is pushed.

### 3. Wire GitHub Actions
From the apply output:
```bash
terraform output github_deploy_role_arn
```
In GitHub → repo → Settings → Secrets and variables → Actions, add:
- `AWS_DEPLOY_ROLE_ARN` — the value above
- `AWS_PLAN_ROLE_ARN` — same role for dev (split for prod)
- `LLM_API_KEY` — Groq key

Create a GitHub **environment** named `dev` (add required reviewers before you
point this at anything that costs real money).

### 4. First real deploy
Push to `main`. `deploy.yml` runs: CI → terraform apply → build+push api/worker
images → roll the ECS service. The API comes live at:
```bash
terraform output api_url
```

### 5. Bake the GPU AMI (before relying on scale-to-zero)
```bash
cd infrastructure/packer
packer init . && packer build gpu-worker.pkr.hcl
```
Put the printed AMI id in `terraform.tfvars` as `gpu_ami_id` and re-apply.
Without this, every GPU scale-up downloads ~35GB before rendering — which makes
scale-to-zero technically work but painfully slow.

---

## The two things most likely to cost you money

1. **GPU left running.** The ASG scales to zero on an empty queue. If you see
   GPUs up with an empty queue on the dashboard, the scaling policy is broken —
   investigate immediately. The budget alarm (default $75/mo, forecast at 80%)
   is the backstop, not the plan.

2. **A poison job looping.** A job that crashes its worker is retried 3× then
   sent to the DLQ. The `dlq-not-empty` alarm fires when that happens. A job
   stuck redelivering holds a GPU the whole time.

---

## Cost shape (dev, rough)

| Item | Idle | Note |
|---|---|---|
| NAT gateway | ~$32/mo | largest fixed cost; one, not per-AZ |
| RDS t4g.micro | ~$12/mo | free-tier eligible first year |
| ElastiCache t4g.micro | ~$11/mo | |
| ALB | ~$16/mo | |
| Fargate API (0.5 vCPU) | ~$15/mo | always-on |
| **GPU workers** | **$0 idle** | ~$0.30–0.50/hr spot *while rendering* |

Idle floor is roughly **$85/mo**; the variable cost is GPU-hours, which is why
scale-to-zero is the whole game. For pure pipeline iteration, RunPod (PHASE0.md)
is still cheaper than keeping this dev env warm — this infra is for when you need
the real API + queue + autoscaling, i.e. Phase 4.

---

## App ↔ infra coherence (why the broker changed)

The API enqueues to **SQS** and the GPU ASG scales on **SQS depth**. So Celery's
broker was switched from Redis to SQS (`workers/celery_app.py`). Had it stayed on
Redis, jobs would land in Redis, SQS would stay empty, and the fleet would never
leave zero. Redis remains as the Celery result backend only. If you ever point
the broker back at Redis, the autoscaling stops working — they are one decision.

---

## What is verified, and what is not

**Verified on this machine:** `terraform fmt`, and `terraform validate` on all
seven modules, the `bootstrap` root, and the full `envs/dev` composition. The
composition validating means module inputs/outputs and types line up end to end.

**NOT verified:** no `terraform apply` has run — that needs a live AWS account,
and some errors only surface then (quota denials, AMI availability in-region,
IAM propagation timing). The backend Python has never executed either (no Python
on the build machine; see PHASE0.md). Treat the first `apply` and the first
`deploy.yml` run as the real integration test, and watch the dashboard.
