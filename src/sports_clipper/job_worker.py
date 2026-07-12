from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from .job_queue import (
    JobCancelled,
    claim_next_job,
    finish_claim,
    is_cancellation_requested,
    load_queued_request,
    resolve_jobs_root,
    update_job_manifest,
    utc_now,
)
from .unified_pipeline import process_clip_request, validate_job_id


Processor = Callable[..., object]
Reporter = Callable[[str], None]


def _result_payload(result: object) -> dict[str, Any]:
    if isinstance(result, dict):
        return dict(result)
    converter = getattr(result, "to_dict", None)
    if callable(converter):
        payload = converter()
        if isinstance(payload, dict):
            return payload
    return {}


def process_next_job(
    jobs_root: Path | str | None = None,
    *,
    processor: Processor = process_clip_request,
    reporter: Reporter | None = print,
) -> dict[str, Any] | None:
    """Claim and process one queued job, returning its final manifest."""
    root = resolve_jobs_root(jobs_root)
    claimed = claim_next_job(root)
    if claimed is None:
        return None

    ticket, ticket_path = claimed
    job_id = validate_job_id(str(ticket.get("job_id", "")))

    def report(message: str) -> None:
        if reporter is not None:
            reporter(message)

    try:
        if is_cancellation_requested(job_id, root):
            raise JobCancelled("Job was cancelled before processing started")

        update_job_manifest(
            job_id,
            root,
            status="running",
            progress_message="Clipper worker started",
            worker_started_at=utc_now(),
        )
        report(f"[{job_id}] running")
        request = load_queued_request(job_id, jobs_root=root)

        def progress(state: str, message: str) -> None:
            if is_cancellation_requested(job_id, root):
                raise JobCancelled("Cancellation requested")
            update_job_manifest(
                job_id,
                root,
                status=state,
                progress_message=message,
            )
            report(f"[{job_id}] {state}: {message}")

        result = processor(request, progress=progress, job_id=job_id)
        payload = _result_payload(result)
        changes: dict[str, Any] = {
            "status": "completed",
            "progress_message": "Clips are ready for delivery",
            "worker_completed_at": utc_now(),
            "result": payload,
        }
        if isinstance(payload.get("clips"), list):
            changes["clips"] = payload["clips"]
        manifest = update_job_manifest(job_id, root, **changes)
        finish_claim(ticket_path, "completed")
        report(f"[{job_id}] completed")
        return manifest
    except JobCancelled as error:
        manifest = update_job_manifest(
            job_id,
            root,
            status="cancelled",
            progress_message=str(error),
            cancelled_at=utc_now(),
        )
        finish_claim(ticket_path, "cancelled")
        report(f"[{job_id}] cancelled: {error}")
        return manifest
    except Exception as error:
        manifest = update_job_manifest(
            job_id,
            root,
            status="failed",
            progress_message=str(error),
            error=str(error),
            worker_failed_at=utc_now(),
        )
        finish_claim(ticket_path, "failed")
        report(f"[{job_id}] failed: {error}")
        return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipper-worker",
        description="Process persistent AI Sports Clipper jobs for Hermes Agent.",
    )
    parser.add_argument(
        "--jobs-root",
        type=Path,
        default=None,
        help="Job workspace root. Defaults to CLIPPER_JOBS_ROOT or data/jobs.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Seconds to wait when no queued job is available.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one job and then exit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final manifest as JSON in --once mode.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.poll_seconds <= 0:
        raise SystemExit("--poll-seconds must be positive")

    root = resolve_jobs_root(args.jobs_root)
    try:
        while True:
            manifest = process_next_job(
                root,
                reporter=None if args.json else print,
            )
            if args.once:
                if args.json:
                    print(json.dumps(manifest or {"status": "idle"}, indent=2))
                return 0 if manifest is None or manifest.get("status") != "failed" else 1
            if manifest is None:
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("clipper-worker stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
