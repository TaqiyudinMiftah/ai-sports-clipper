from __future__ import annotations

import argparse
import time
import traceback
from pathlib import Path
from typing import Any

from .job_queue import claim_next_job, default_jobs_root, finish_job, get_job, update_job
from .unified_pipeline import ClipRequest, process_clip_request


def _request_from_payload(payload: dict[str, Any], jobs_root: Path) -> ClipRequest:
    return ClipRequest(
        source=str(payload["source"]),
        clip_count=int(payload.get("clip_count", 3)),
        target_duration=float(payload.get("target_duration", 20.0)),
        threshold=float(payload.get("threshold", 0.62)),
        sample_fps=float(payload.get("sample_fps", 2.0)),
        slowmo_speed=float(payload.get("slowmo_speed", 0.4)),
        reframe=bool(payload.get("reframe", True)),
        confirm_rights=bool(payload.get("confirm_rights", False)),
        jobs_root=jobs_root / "pipeline",
    )


def process_queued_job(job: dict[str, Any], *, jobs_root: Path) -> dict[str, Any]:
    job_id = str(job["job_id"])
    request_payload = job.get("request")
    if not isinstance(request_payload, dict):
        raise ValueError("queued job request must be an object")

    def progress(state: str, message: str) -> None:
        current = get_job(job_id, jobs_root=jobs_root)
        if current.get("cancel_requested"):
            raise RuntimeError("Job cancelled by user")
        update_job(
            job_id,
            {"progress": {"state": state, "message": message}},
            jobs_root=jobs_root,
        )

    try:
        result = process_clip_request(
            _request_from_payload(request_payload, jobs_root),
            progress=progress,
        ).to_dict()
        return finish_job(
            job_id,
            status="completed",
            changes={
                "pipeline_job_id": result["job_id"],
                "pipeline_manifest_path": result["manifest_path"],
                "clips": result["clips"],
                "progress": {"state": "completed", "message": f"Created {len(result['clips'])} clips"},
            },
            jobs_root=jobs_root,
        )
    except Exception as error:
        current = get_job(job_id, jobs_root=jobs_root)
        cancelled = bool(current.get("cancel_requested"))
        return finish_job(
            job_id,
            status="cancelled" if cancelled else "failed",
            changes={
                "error": str(error),
                "traceback": traceback.format_exc(),
                "progress": {
                    "state": "cancelled" if cancelled else "failed",
                    "message": str(error),
                },
            },
            jobs_root=jobs_root,
        )


def run_worker(*, jobs_root: Path, poll_seconds: float = 2.0, once: bool = False) -> int:
    print(f"Clipper worker watching {jobs_root}", flush=True)
    while True:
        job = claim_next_job(jobs_root=jobs_root)
        if job is None:
            if once:
                return 0
            time.sleep(poll_seconds)
            continue
        print(f"Processing {job['job_id']}", flush=True)
        result = process_queued_job(job, jobs_root=jobs_root)
        print(f"Finished {job['job_id']}: {result['status']}", flush=True)
        if once:
            return 0 if result["status"] == "completed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process queued AI sports clipping jobs.")
    parser.add_argument("--jobs-root", type=Path, default=default_jobs_root())
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_worker(
        jobs_root=args.jobs_root.expanduser().resolve(),
        poll_seconds=max(0.2, args.poll_seconds),
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
