"""
Celery configuration.

Broker is SQS, not Redis. This is a coherence requirement, not a preference: the
GPU autoscaling group scales on the SQS queue's depth (modules/gpu_workers). If
the app enqueued to Redis instead, SQS would stay empty, the ASG would never
scale up, and jobs would queue forever while the fleet sat at zero. The queue
the app pushes to must be the queue the infra watches.

On EC2 the SQS broker authenticates via the worker's IAM role -- no keys. Redis
stays on as the result backend only (fast, and results are ephemeral).

One queue, `video`, matching the Terraform. The previous config routed to seven
queues named for pipeline stages (planner/script/character/render/export) that
the rewrite collapsed into a single compile_video task.
"""

from __future__ import annotations

import os

from celery import Celery

from config import get_settings

settings = get_settings()

# Map Celery's logical "video" queue to the real SQS queue URL, injected by the
# worker's environment (Terraform sets VIDEO_QUEUE_URL in user_data).
_video_queue_url = os.environ.get("VIDEO_QUEUE_URL")

_broker_transport_options: dict = {
    "region": settings.aws_region,
    # Must exceed the slowest job or SQS redelivers mid-render. Mirrors the
    # queue module's visibility_timeout_seconds default (3600).
    "visibility_timeout": 3600,
    "polling_interval": 5,
    "wait_time_seconds": 20,  # long polling -> fewer empty receives -> lower cost
}

if _video_queue_url:
    # predefined_queues lets Celery target an existing SQS queue by URL instead
    # of trying to create/list queues (which the worker IAM role can't do, by
    # design -- it has ReceiveMessage/DeleteMessage only).
    _broker_transport_options["predefined_queues"] = {
        "video": {"url": _video_queue_url}
    }

# Broker is SQS in prod, Redis for local docker-compose. There is no SQS locally,
# so hardcoding sqs:// would break `docker-compose up`. config.celery_broker
# selects; docker-compose sets it to "redis".
if settings.celery_broker == "redis":
    _broker_url = settings.celery_broker_url
    _transport_options: dict = {}
else:
    _broker_url = "sqs://"  # credentials from the instance IAM role
    _transport_options = _broker_transport_options

celery_app = Celery(
    "video_compiler",
    broker=_broker_url,
    backend=settings.celery_result_backend,  # Redis
)

celery_app.conf.update(
    broker_transport_options=_transport_options,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # acks_late + prefetch=1: a job is deleted from SQS only after it SUCCEEDS,
    # and a worker holds exactly one job at a time. If a spot instance dies
    # mid-render, SQS redelivers the job to another worker after the visibility
    # timeout -- the video is delayed, never lost.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,

    task_default_queue="video",
    task_routes={
        "workers.tasks.compile_video": {"queue": "video"},
    },

    # A whole video is generated in one task. Limits must cover the slowest
    # realistic render or Celery kills a healthy job. Phase 0 (15s, Wan 1.3B)
    # runs ~8-10 min; Phase 1's 60s videos run longer. Generous on purpose.
    task_soft_time_limit=3000,   # 50 min: task can catch this and clean up
    task_time_limit=3300,        # 55 min: hard kill. < SQS visibility (3600).

    task_default_retry_delay=30,
    task_max_retries=2,
)
