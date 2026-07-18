#!/usr/bin/env python3
"""
Phase 0 runner.

    python run_phase0.py "A short story about a farmer who learns to code"

Produces a playable mp4 plus every intermediate asset in the work directory.

Judge the output on: do audio, subtitles and video stay locked? Does QC pass?
NOT on beauty -- Wan 1.3B is not a cinematic model and Phase 0 does not ask it
to be. See ARCHITECTURE.md §12.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import structlog

from pipeline.phase0 import Phase0Config, run_phase0
from providers.base import ProviderError, UnsupportedCapability
from providers.bootstrap import build_registry
from qc.gates import QCFailure

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ]
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 0 vertical slice.")
    parser.add_argument("idea", help="What the video should be about")
    parser.add_argument("--duration", type=int, default=15, help="Seconds (default: 15)")
    parser.add_argument("--scenes", type=int, default=3, help="Scene count (default: 3)")
    parser.add_argument("--language", default="en", help="ISO 639-1 code (default: en)")
    parser.add_argument("--seed", type=int, default=42, help="Fixed seed for comparable runs")
    parser.add_argument("--work-dir", default="/tmp/render/phase0", help="Output directory")
    parser.add_argument(
        "--no-strict-qc",
        action="store_true",
        help="Report QC failures without raising. Use to inspect a bad render.",
    )
    args = parser.parse_args()

    registry = build_registry()

    config = Phase0Config(
        duration_s=args.duration,
        scene_count=args.scenes,
        language=args.language,
        seed=args.seed,
        strict_qc=not args.no_strict_qc,
    )

    try:
        result = await run_phase0(
            idea=args.idea,
            registry=registry,
            work_dir=Path(args.work_dir),
            config=config,
        )
    except UnsupportedCapability as e:
        # The most likely first failure: asking for Telugu before Phase 2.
        print(f"\n✗ Unsupported: {e}", file=sys.stderr)
        print(f"  Languages available now: {sorted(registry.supported_languages())}", file=sys.stderr)
        print("  Telugu/Hindi arrive in Phase 2 via IndicF5.", file=sys.stderr)
        return 2
    except QCFailure as e:
        print(f"\n✗ {e.report.summary()}", file=sys.stderr)
        print(f"\n  Intermediates kept in {args.work_dir} for inspection.", file=sys.stderr)
        print("  Re-run with --no-strict-qc to produce the file anyway.", file=sys.stderr)
        return 3
    except ProviderError as e:
        print(f"\n✗ Provider failed: {e}", file=sys.stderr)
        return 4

    print(f"\n✓ {result.video}")
    print(f"  Title:    {result.title}")
    print(f"  Duration: {result.duration_s:.1f}s  (planned {result.reconcile.planned_duration_s:.1f}s, "
          f"drift {result.reconcile.drift_s:+.1f}s)")
    print(f"  Wall:     {result.elapsed_s:.0f}s")
    print(f"  QC:       {result.qc.summary()}")

    if result.reconcile.scenes_shortened:
        print(f"  Shortened scenes: {result.reconcile.scenes_shortened} "
              f"(script pacing ran long -- expected, reconcile handled it)")

    print("\n  Stage timings:")
    for stage, seconds in result.stage_timings.items():
        print(f"    {stage:<16} {seconds:6.1f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
