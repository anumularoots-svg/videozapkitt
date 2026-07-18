# AI Video Compiler — Complete Setup Guide

## What You're Building

An AI Video Compiler that transforms a single idea into a ready-to-publish cinematic 60-second Reel in any language. Internally it is a compiler-driven, blueprint-based, agent-orchestrated system. Externally it is one input box and one button.

---

## Prerequisites

Before starting, install these on your machine:

- **Docker Desktop** (v24+) with Docker Compose
- **Python 3.11+** (for local development)
- **Node.js 20+** (for frontend)
- **Git**
- A machine with at least **16GB RAM** (for local dev)
- A **GPU with 24GB VRAM** (for AI model inference — not needed for development, only for actual video generation)

---

## Step 1: Clone and Configure

```bash
git clone https://github.com/your-org/ai-video-compiler.git
cd ai-video-compiler
cp .env.example .env
```

Edit `.env` with your actual secrets for production. For local development, the defaults work with Docker Compose.

---

## Step 2: Start the Stack

```bash
docker-compose up -d
```

This starts 7 services:

| Service    | Port  | Purpose                |
|------------|-------|------------------------|
| backend    | 8000  | FastAPI server         |
| worker     | —     | Celery GPU workers     |
| frontend   | 3000  | Next.js UI             |
| db         | 5432  | PostgreSQL             |
| redis      | 6379  | Queue + Cache          |
| minio      | 9000  | S3-compatible storage  |
| flower     | 5555  | Celery monitoring      |

---

## Step 3: Initialize Database

```bash
docker-compose exec backend alembic revision --autogenerate -m "initial"
docker-compose exec backend alembic upgrade head
```

---

## Step 4: Verify Everything Works

```bash
# Backend health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs

# Frontend
open http://localhost:3000

# MinIO console
open http://localhost:9001  # minioadmin / minioadmin

# Celery monitoring
open http://localhost:5555
```

---

## Step 5: Set Up AI Models (For Actual Video Generation)

V1 requires these open-source models. For development, the system works without them (agents fall back to defaults). For production video generation, deploy each model:

### LLM (Script & Planning)
```bash
# Option A: vLLM server
pip install vllm
vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8080

# Option B: Ollama
ollama pull llama3.1:8b
ollama serve
```

Update `.env`: `LLM_API_URL=http://localhost:8080/v1`

### Image Generation (FLUX)
```bash
# Using ComfyUI or diffusers
pip install diffusers torch
# Deploy as API endpoint on GPU machine
```

### Video Generation (Wan 2.1)
```bash
pip install diffusers torch
# Deploy Wan2.1-T2V-14B as API
# Requires 24GB+ VRAM GPU
```

### Voice (Kokoro TTS)
```bash
pip install kokoro
# Deploy as API endpoint
```

### Translation (NLLB)
```bash
pip install transformers
# facebook/nllb-200-distilled-600M runs on CPU
```

### Upscaling (Real-ESRGAN)
```bash
pip install realesrgan
```

---

## Architecture Overview

### The 10-Stage Compiler Pipeline

```
Stage 1: Input Parser        → Classify video type, normalize language
Stage 2: Template Selector   → Pick story structure (educational, motivational, etc.)
Stage 3: Video DSL Generator → Create intermediate DSL representation
Stage 4: Blueprint Generator → Convert DSL to Blueprint JSON (source of truth)
Stage 5: Blueprint Validator → Validate durations, characters, scenes
Stage 6: Blueprint Optimizer → Optimize pacing, transitions, GPU batching
Stage 7: Execution Planner   → Build DAG of parallel/sequential tasks
Stage 8: DAG Orchestrator    → Execute agents according to DAG
Stage 9: Quality Validator   → PASS/FAIL checks on all generated assets
Stage 10: Render + Export    → FFmpeg stitch, audio mix, subtitle burn, upload
```

### Agent System

Each agent receives a Blueprint JSON and returns an updated Blueprint JSON:

```
Director Agent   → Makes all creative decisions (characters, emotions, camera)
Script Agent     → Writes narration script per scene (uses LLM)
Character Agent  → Assigns characters, builds consistency prompts
Voice Agent      → Configures TTS parameters per scene
Music Agent      → Plans background music arc
Subtitle Agent   → Generates SRT subtitle data
Consistency Agent → Checks character visual consistency across scenes
Quality Agent    → Runs PASS/FAIL validation before render
```

### DAG Execution Order

```
Parallel:   Character Agent + Music Agent + Voice Agent  (after Script)
Sequential: Script → Voice → Subtitle
Parallel:   Scene Video 1 + Scene Video 2 + ... (after Character)
Sequential: Consistency Check → Render → Quality Check → Export
```

### Blueprint JSON (Source of Truth)

Every project has a versioned Blueprint JSON that is the single source of truth:

```json
{
  "project_id": "abc-123",
  "version": 1,
  "video_type": "educational",
  "duration": 60,
  "language": "Telugu",
  "style": "cinematic",
  "scenes": [
    {
      "id": 1,
      "duration": 8,
      "character": "narrator_m_01",
      "camera": "close_up",
      "emotion": "curious",
      "environment": "cloud_lab",
      "voice": "male",
      "music": "corporate_soft",
      "script": "...",
      "subtitle": "...",
      "full_prompt": "..."
    }
  ]
}
```

---

## Project Structure

```
ai-video-compiler/
├── backend/
│   ├── main.py                         # FastAPI app entry point
│   ├── config.py                       # Environment configuration
│   ├── alembic.ini                     # Database migration config
│   ├── requirements.txt
│   │
│   ├── api/
│   │   ├── __init__.py                 # Router registration
│   │   ├── routes/
│   │   │   ├── auth.py                 # POST /auth/signup, /auth/login
│   │   │   └── video.py                # POST /video/create, GET /video/status, etc.
│   │   └── middleware/
│   │       └── auth.py                 # JWT authentication
│   │
│   ├── compiler/
│   │   ├── video_compiler.py           # Main compiler (orchestrates stages 1-7)
│   │   ├── parser/
│   │   │   └── input_parser.py         # Stage 1: Parse & classify user input
│   │   ├── dsl/
│   │   │   ├── engine.py               # Stage 3-4: DSL → Blueprint JSON
│   │   │   └── templates.py            # Stage 2: Story structure templates
│   │   ├── validator/
│   │   │   └── blueprint_validator.py  # Stage 5: Validate blueprint
│   │   ├── optimizer/
│   │   │   └── blueprint_optimizer.py  # Stage 6: Optimize for rendering
│   │   └── planner/
│   │       └── execution_planner.py    # Stage 7: Build DAG
│   │
│   ├── agents/
│   │   ├── base_agent.py               # Abstract base agent
│   │   ├── llm_client.py               # OpenAI-compatible LLM client
│   │   ├── director/agent.py           # AI Movie Director
│   │   ├── script/agent.py             # Script writer
│   │   ├── character/agent.py          # Character consistency engine
│   │   ├── voice/agent.py              # TTS configuration
│   │   ├── music/agent.py              # Background music planner
│   │   ├── subtitle/agent.py           # SRT subtitle generator
│   │   ├── consistency/agent.py        # Cross-scene consistency checker
│   │   └── quality/agent.py            # PASS/FAIL quality validation
│   │
│   ├── orchestrator/
│   │   └── dag_orchestrator.py         # Stage 8: Execute DAG plan
│   │
│   ├── renderer/
│   │   └── render_pipeline.py          # Stages 9-10: FFmpeg render + export
│   │
│   ├── workers/
│   │   ├── celery_app.py               # Celery configuration + queues
│   │   └── tasks.py                    # Async GPU tasks
│   │
│   ├── models/
│   │   ├── database.py                 # SQLAlchemy models
│   │   └── schemas.py                  # Pydantic request/response schemas
│   │
│   ├── services/
│   │   └── database.py                 # Async DB session management
│   │
│   └── storage/
│       └── s3_storage.py               # S3/MinIO storage abstraction
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                  # Root layout
│   │   ├── globals.css                 # Global styles
│   │   ├── page.tsx                    # Home page (create video)
│   │   └── status/page.tsx             # Generation progress page
│   └── lib/
│       └── api.ts                      # API client
│
├── infrastructure/
│   ├── docker/
│   │   ├── Dockerfile.backend
│   │   ├── Dockerfile.worker
│   │   └── Dockerfile.frontend
│   └── terraform/
│       └── main.tf                     # AWS infrastructure
│
├── character_packs/                    # Curated character assets
│   └── narrator_01/metadata.json
│
├── templates/                          # Video DSL templates
│   └── video_templates.json
│
├── docker-compose.yml                  # Full local dev stack
├── .env.example                        # Environment template
├── .gitignore
└── README.md
```

---

## API Reference (V1)

| Method | Endpoint                    | Description              |
|--------|-----------------------------|--------------------------|
| POST   | /api/v1/auth/signup         | Create account           |
| POST   | /api/v1/auth/login          | Login                    |
| POST   | /api/v1/video/create        | Create video from idea   |
| GET    | /api/v1/video/status/{id}   | Check progress           |
| GET    | /api/v1/video/project/{id}  | Get project details      |
| POST   | /api/v1/video/regenerate-scene | Retry a failed scene  |
| GET    | /api/v1/video/download/{id} | Get download URL         |
| GET    | /api/v1/video/credits       | Check remaining credits  |
| GET    | /health                     | Health check             |

---

## Running Tests

```bash
cd backend
pip install pytest pytest-asyncio
pytest tests/ -v
```

---

## Queue Architecture

Seven independent queues for independent scaling:

| Queue            | Tasks                      | GPU Required |
|------------------|----------------------------|-------------|
| planner_queue    | Video compilation          | No          |
| script_queue     | Script generation (LLM)    | No          |
| character_queue  | Character image generation  | Yes         |
| voice_queue      | TTS voice generation       | Yes         |
| video_queue      | Scene video generation     | Yes         |
| render_queue     | FFmpeg rendering           | Yes         |
| export_queue     | Final export + upload      | No          |

---

## Cost Optimization Rules

1. **0 GPUs when idle** — Auto-scale from 0 based on queue depth
2. **AWS Spot Instances** — Up to 70% savings on GPU instances
3. **Scene-level retries** — Never regenerate the full video for one failed scene
4. **Cache everything** — Characters, voices, music, scenes stored in S3 for reuse
5. **Blueprint validation before GPU** — Catch errors before allocating expensive resources

---

## Production Deployment

```bash
# 1. Set up AWS infrastructure
cd infrastructure/terraform
terraform init
terraform plan
terraform apply

# 2. Build and push Docker images
docker build -f infrastructure/docker/Dockerfile.backend -t your-ecr/backend:latest ./backend
docker push your-ecr/backend:latest

# 3. Deploy to ECS
# Use the Terraform-managed ECS cluster

# 4. Run migrations
# Connect to the backend container and run:
alembic upgrade head

# 5. Set up CloudFront for CDN delivery of generated videos
```

---

## V1 Scope Checklist

- [x] Auto Mode only (one text box, one button)
- [x] 9:16 aspect ratio (YouTube Shorts / Instagram Reels)
- [x] 30-second and 60-second videos
- [x] 4 video categories (story, educational, motivational, corporate)
- [x] 15 curated characters
- [x] Compiler-driven architecture (10 stages)
- [x] Video DSL + Blueprint JSON as source of truth
- [x] DAG-based parallel agent execution
- [x] Scene-level generation and retries
- [x] PASS/FAIL quality validation
- [x] Credit-based pricing structure
- [x] GPU auto-scaling (0 to N)
- [x] Open-source AI models only
- [x] No prompt engineering exposed to users

---

## Future Roadmap

| Version | Features                           |
|---------|------------------------------------|
| V2      | Hybrid Mode (user customization)   |
| V3      | Manual Mode (upload your assets)   |
| V4      | YouTube long-form videos           |
| V5      | 3D, Anime, Product Ads             |
| V6      | AI Avatar videos                   |
| V7      | Movie trailer generator            |
