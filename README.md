# AI Video Compiler

**Turn one idea into a cinematic 60-second Reel in any language.**

An AI Video Compiler that transforms a single idea into a ready-to-publish
cinematic Reel using a compiler-driven, blueprint-based, agent-orchestrated
architecture with DAG execution, scene-level retries, and a curated character library.

## Architecture

```
User Input → Parser → DSL Engine → Blueprint Generator → Validator → Optimizer
→ Execution Planner → DAG Orchestrator → Agents → Quality Validator → Renderer → Export
```

## V1 Scope

- **Mode:** Auto only (one text box, one button)
- **Format:** 9:16 (YouTube Shorts / Instagram Reels)
- **Duration:** 30s or 60s
- **Video types:** Story, Educational, Motivational, Corporate Explainer
- **Characters:** 15 curated (5 male, 5 female, 2 narrators, 2 business, 1 robot)
- **Languages:** 50+ via NLLB translation
- **AI Models:** All open-source (Flux, Wan 2.1, Kokoro, Whisper, NLLB)

## Quick Start

```bash
# 1. Clone and enter
cd ai-video-compiler

# 2. Copy environment config
cp .env.example .env

# 3. Start everything
docker-compose up -d

# 4. Run database migrations
docker-compose exec backend alembic upgrade head

# 5. Open
# Backend API:  http://localhost:8000/docs
# Frontend:     http://localhost:3000
# Redis:        localhost:6379
# PostgreSQL:   localhost:5432
```

## Tech Stack

| Layer          | Technology                    |
|----------------|-------------------------------|
| Frontend       | Next.js + Tailwind            |
| Backend        | FastAPI + Python 3.11         |
| Queue          | Redis + Celery                |
| Database       | PostgreSQL                    |
| Storage        | S3 (MinIO locally)            |
| GPU Workers    | Docker                        |
| Rendering      | FFmpeg                        |
| Infrastructure | Terraform + Docker Compose    |
| Monitoring     | Prometheus + Grafana          |
| CI/CD          | GitHub Actions                |

## Project Structure

```
ai-video-compiler/
├── backend/
│   ├── api/              # FastAPI routes & middleware
│   ├── compiler/         # Video Compiler (parser, DSL, blueprint, validator)
│   ├── agents/           # AI Agents (script, voice, character, music, etc.)
│   ├── orchestrator/     # DAG-based agent orchestrator
│   ├── renderer/         # FFmpeg render pipeline
│   ├── workers/          # Celery GPU workers
│   ├── queue/            # Redis queue config
│   ├── services/         # Business logic services
│   ├── models/           # SQLAlchemy / Pydantic models
│   ├── storage/          # S3 storage abstraction
│   └── utils/            # Shared utilities
├── frontend/             # Next.js app
├── infrastructure/       # Docker + Terraform
├── character_packs/      # Curated character assets
├── templates/            # Video DSL templates
└── docs/                 # Documentation
```
