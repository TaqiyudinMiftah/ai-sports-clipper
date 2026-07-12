from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_tools import clip_request_from_payload, get_clip_job
from .unified_pipeline import ClipRequest, create_job_id, validate_job_id


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class QueueError(RuntimeError):
    """Raised when a persistent queue operation cannot be completed."""


class JobCancelled(RuntimeError):
    """Raised by a worker when cooperative cancellation is requested."""


@dataclass(frozen=True)
class QueuePaths:
    root: Path
    pending: Path
    running: Path
    completed: Path
    failed: Path
    cancelled: Path

    @classmethod
    def from_jobs_root(cls, jobs_root: Path) -> "QueuePaths":
        root = jobs_root / "_queue"
        paths = cls(
            root=root,
            pending=root / "pending",
            running=root / "running",
            completed=root / "completed",
            failed=root / "failed",
            cancelled=root / "cancelled",
        )
        for directory in (
            paths.pending,
            paths.running,
            paths.completed,
            paths.failed,
            paths.cancelled,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return paths


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_jobs_root(jobs_root: Path | str | None = None) -> Path:
    configured = jobs_root or os.environ.get("CLIPPER_JOBS_ROOT") or "data/jobs"
    return Path(configured).expanduser().resolve()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as error:
        raise QueueError(f"Could not read JSON file {path}: {error}") from error
    if not isinstance(payload, dict):
        raise QueueError(f"Expected a JSON object in {path}")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def job_directory(job_id: str, jobs_root: Path | str | None = None) -> Path:
    return resolve_jobs_root(jobs_root) / validate_job_id(job_id)


def job_manifest_path(job_id: str, jobs_root: Path | str | None = None) -> Path:
    return job_directory(job_id, jobs_root) / "job.json"


def cancellation_path(job_id: str, jobs_root: Path | str | None = None) -> Path:
    return job_directory(job_id, jobs_root) / "cancel.requested"


def create_queue_job_id(source: str) -> str:
    return f"{create_job_id(source)}-{secrets.token_hex(3)}"


def update_job_manifest(
    job_id: str,
    jobs_root: Path | str | None = None,
    **changes: Any,
) -> dict[str, Any]:
    path = job_manifest_path(job_id, jobs_root)
    current = _read_json(path) if path.is_file() else {"job_id": validate_job_id(job_id)}
    current.update(changes)
    current["updated_at"] = utc_now()
    _atomic_write_json(path, current)
    return current


def enqueue_clip_job(
    payload: dict[str, object],
    *,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Validate and persist a clip request without running video processing."""
    root = resolve_jobs_root(jobs_root or payload.get("jobs_root"))
    normalized_payload = dict(payload)
    normalized_payload["jobs_root"] = str(root)
    request = clip_request_from_payload(normalized_payload, default_jobs_root=root)
    request = replace(request, jobs_root=root)

    job_id = create_queue_job_id(request.source)
    job_dir = root / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    created_at = utc_now()
    request_payload = request.to_dict()
    request_record = {
        "job_id": job_id,
        "submitted_at": created_at,
        "request": request_payload,
    }
    manifest: dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "progress_message": "Waiting for a clipper worker",
        "created_at": created_at,
        "updated_at": created_at,
        "request": request_payload,
        "clips": [],
    }

    request_path = job_dir / "request.json"
    manifest_path = job_dir / "job.json"
    _atomic_write_json(request_path, request_record)
    _atomic_write_json(manifest_path, manifest)

    queue_paths = QueuePaths.from_jobs_root(root)
    ticket = {
        "job_id": job_id,
        "submitted_at": created_at,
        "request_path": str(request_path),
    }
    _atomic_write_json(queue_paths.pending / f"{job_id}.json", ticket)

    return {
        **manifest,
        "job_dir": str(job_dir),
        "manifest_path": str(manifest_path),
    }


def claim_next_job(
    jobs_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path] | None:
    """Atomically move the oldest pending ticket into the running directory."""
    root = resolve_jobs_root(jobs_root)
    paths = QueuePaths.from_jobs_root(root)
    for pending_path in sorted(paths.pending.glob("*.json")):
        running_path = paths.running / pending_path.name
        try:
            pending_path.replace(running_path)
        except FileNotFoundError:
            continue
        ticket = _read_json(running_path)
        return ticket, running_path
    return None


def finish_claim(ticket_path: Path, status: str) -> Path:
    if status not in {"completed", "failed", "cancelled"}:
        raise ValueError(f"unsupported terminal queue status: {status}")
    queue_root = ticket_path.parent.parent
    destination_dir = queue_root / status
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / ticket_path.name
    if ticket_path.exists():
        ticket_path.replace(destination)
    return destination


def is_cancellation_requested(
    job_id: str,
    jobs_root: Path | str | None = None,
) -> bool:
    return cancellation_path(job_id, jobs_root).is_file()


def cancel_clip_job(
    job_id: str,
    *,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Cancel a queued job immediately or request cooperative running cancellation."""
    root = resolve_jobs_root(jobs_root)
    validated = validate_job_id(job_id)
    manifest = get_clip_job(validated, jobs_root=root)
    status = str(manifest.get("status", ""))
    if status in TERMINAL_STATUSES:
        return manifest

    paths = QueuePaths.from_jobs_root(root)
    pending_ticket = paths.pending / f"{validated}.json"
    if pending_ticket.is_file():
        finish_claim(pending_ticket, "cancelled")
        return update_job_manifest(
            validated,
            root,
            status="cancelled",
            progress_message="Cancelled before processing started",
            cancelled_at=utc_now(),
        )

    marker = cancellation_path(validated, root)
    marker.write_text(utc_now(), encoding="utf-8")
    return update_job_manifest(
        validated,
        root,
        status="cancellation_requested",
        progress_message="Cancellation will be applied at the next pipeline checkpoint",
        cancellation_requested_at=utc_now(),
    )


def load_queued_request(
    job_id: str,
    *,
    jobs_root: Path | str | None = None,
) -> ClipRequest:
    root = resolve_jobs_root(jobs_root)
    record = _read_json(job_directory(job_id, root) / "request.json")
    payload = record.get("request")
    if not isinstance(payload, dict):
        raise QueueError(f"Job {job_id} has no valid request payload")
    request = clip_request_from_payload(payload, default_jobs_root=root)
    return replace(request, jobs_root=root)


def list_clip_outputs(
    job_id: str,
    *,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return absolute, host-readable clip paths for Hermes MEDIA delivery."""
    root = resolve_jobs_root(jobs_root)
    validated = validate_job_id(job_id)
    manifest = get_clip_job(validated, jobs_root=root)
    clips = manifest.get("clips", [])
    output_records: list[dict[str, Any]] = []
    media_paths: list[str] = []
    job_root = (root / validated).resolve()

    if isinstance(clips, list):
        for position, clip in enumerate(clips, start=1):
            if not isinstance(clip, dict):
                continue
            raw_path = clip.get("final_path")
            if not isinstance(raw_path, str) or not raw_path:
                continue
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            else:
                path = path.resolve()
            if not path.is_relative_to(job_root):
                continue
            exists = path.is_file()
            record = {
                "index": int(clip.get("index", position)),
                "path": str(path),
                "exists": exists,
                "media_tag": f"MEDIA:{path}" if exists else None,
            }
            output_records.append(record)
            if exists:
                media_paths.append(str(path))

    return {
        "job_id": validated,
        "status": manifest.get("status"),
        "outputs": output_records,
        "media_paths": media_paths,
        "ready": bool(media_paths) and manifest.get("status") == "completed",
    }
