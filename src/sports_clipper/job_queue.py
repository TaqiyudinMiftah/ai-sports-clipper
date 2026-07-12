from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class QueueError(RuntimeError):
    """Raised when a queued clip job cannot be created or updated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_jobs_root() -> Path:
    return Path(os.environ.get("CLIPPER_JOBS_ROOT", "data/jobs")).expanduser().resolve()


def _validate_job_id(job_id: str) -> str:
    if not job_id or any(token in job_id for token in ("/", "\\", "..")):
        raise ValueError("invalid job_id")
    return job_id


def queue_paths(jobs_root: Path) -> dict[str, Path]:
    root = jobs_root.expanduser().resolve()
    paths = {
        "root": root,
        "pending": root / "queue" / "pending",
        "running": root / "queue" / "running",
        "completed": root / "queue" / "completed",
        "failed": root / "queue" / "failed",
        "cancelled": root / "queue" / "cancelled",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def submit_job(payload: dict[str, Any], *, jobs_root: Path | None = None) -> dict[str, Any]:
    source = payload.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a non-empty string")

    root = (jobs_root or default_jobs_root()).expanduser().resolve()
    paths = queue_paths(root)
    job_id = f"hermes-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    record: dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "request": payload,
        "progress": {"state": "queued", "message": "Waiting for a clipper worker"},
        "clips": [],
    }
    job_dir = root / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    _atomic_write(job_dir / "job.json", record)
    _atomic_write(paths["pending"] / f"{job_id}.json", {"job_id": job_id})
    return record


def get_job(job_id: str, *, jobs_root: Path | None = None) -> dict[str, Any]:
    validated = _validate_job_id(job_id)
    root = (jobs_root or default_jobs_root()).expanduser().resolve()
    manifest = root / validated / "job.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"Job not found: {validated}")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise QueueError(f"Invalid job manifest: {manifest}")
    return payload


def update_job(job_id: str, changes: dict[str, Any], *, jobs_root: Path | None = None) -> dict[str, Any]:
    root = (jobs_root or default_jobs_root()).expanduser().resolve()
    record = get_job(job_id, jobs_root=root)
    record.update(changes)
    record["updated_at"] = utc_now()
    _atomic_write(root / job_id / "job.json", record)
    return record


def claim_next_job(*, jobs_root: Path | None = None) -> dict[str, Any] | None:
    root = (jobs_root or default_jobs_root()).expanduser().resolve()
    paths = queue_paths(root)
    for pending in sorted(paths["pending"].glob("*.json")):
        running = paths["running"] / pending.name
        try:
            pending.replace(running)
        except FileNotFoundError:
            continue
        job_id = pending.stem
        record = update_job(
            job_id,
            {
                "status": "running",
                "started_at": utc_now(),
                "progress": {"state": "running", "message": "Worker claimed the job"},
            },
            jobs_root=root,
        )
        record["queue_file"] = str(running)
        return record
    return None


def finish_job(
    job_id: str,
    *,
    status: str,
    changes: dict[str, Any] | None = None,
    jobs_root: Path | None = None,
) -> dict[str, Any]:
    if status not in {"completed", "failed", "cancelled"}:
        raise ValueError("terminal status must be completed, failed, or cancelled")
    root = (jobs_root or default_jobs_root()).expanduser().resolve()
    paths = queue_paths(root)
    payload = {"status": status, f"{status}_at": utc_now()}
    payload.update(changes or {})
    record = update_job(job_id, payload, jobs_root=root)
    for state in ("pending", "running"):
        marker = paths[state] / f"{job_id}.json"
        if marker.exists():
            marker.replace(paths[status] / marker.name)
            break
    return record


def cancel_job(job_id: str, *, jobs_root: Path | None = None) -> dict[str, Any]:
    root = (jobs_root or default_jobs_root()).expanduser().resolve()
    record = get_job(job_id, jobs_root=root)
    if record.get("status") in {"completed", "failed", "cancelled"}:
        return record
    if record.get("status") == "running":
        return update_job(
            job_id,
            {"cancel_requested": True, "progress": {"state": "running", "message": "Cancellation requested"}},
            jobs_root=root,
        )
    return finish_job(
        job_id,
        status="cancelled",
        changes={"progress": {"state": "cancelled", "message": "Job cancelled before processing"}},
        jobs_root=root,
    )


def list_outputs(job_id: str, *, jobs_root: Path | None = None) -> list[str]:
    record = get_job(job_id, jobs_root=jobs_root)
    outputs: list[str] = []
    for clip in record.get("clips", []):
        if isinstance(clip, dict):
            path = clip.get("final_path")
            if isinstance(path, str) and Path(path).is_file():
                outputs.append(str(Path(path).expanduser().resolve()))
    return outputs
