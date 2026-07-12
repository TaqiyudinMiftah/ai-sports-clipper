from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .job_queue import cancel_job, default_jobs_root, get_job, list_outputs, submit_job
from .source_ingestion import is_youtube_url

mcp = FastMCP("AI Sports Clipper")


def _jobs_root() -> Path:
    return default_jobs_root()


def _validate_submission(
    source: str,
    clip_count: int,
    target_duration: float,
    slowmo_speed: float,
    confirm_rights: bool,
) -> None:
    if not source.strip():
        raise ValueError("source is required")
    if not 1 <= clip_count <= 10:
        raise ValueError("clip_count must be between 1 and 10")
    if not 10 <= target_duration <= 60:
        raise ValueError("target_duration must be between 10 and 60 seconds")
    if not 0.25 <= slowmo_speed < 1:
        raise ValueError("slowmo_speed must be between 0.25 and 1.0")
    if is_youtube_url(source) and not confirm_rights:
        raise ValueError(
            "YouTube sources require confirm_rights=true after the user confirms "
            "the footage is official or otherwise authorized."
        )


def _job_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": record["job_id"],
        "status": record["status"],
        "progress": record.get("progress"),
        "error": record.get("error"),
        "clip_count": len(record.get("clips", [])),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


@mcp.tool()
def submit_clip_job(
    source: str,
    clip_count: int = 3,
    target_duration: float = 20.0,
    slowmo_speed: float = 0.4,
    confirm_rights: bool = False,
    threshold: float = 0.62,
    reframe: bool = True,
) -> dict[str, Any]:
    """Queue social clips from an authorized local video or YouTube URL.

    YouTube requests must set confirm_rights only after the user explicitly confirms
    they have permission to process the footage.
    """
    _validate_submission(
        source,
        clip_count,
        target_duration,
        slowmo_speed,
        confirm_rights,
    )
    record = submit_job(
        {
            "source": source.strip(),
            "clip_count": clip_count,
            "target_duration": target_duration,
            "slowmo_speed": slowmo_speed,
            "confirm_rights": confirm_rights,
            "threshold": threshold,
            "reframe": reframe,
        },
        jobs_root=_jobs_root(),
    )
    return {
        "job_id": record["job_id"],
        "status": record["status"],
        "progress": record["progress"],
        "message": "Clip job queued. Use wait_for_clip_job or get_clip_job to check progress.",
    }


@mcp.tool()
def get_clip_job(job_id: str) -> dict[str, Any]:
    """Return the current status, progress, errors, and clip count for one job."""
    return _job_summary(get_job(job_id, jobs_root=_jobs_root()))


@mcp.tool()
def wait_for_clip_job(
    job_id: str,
    timeout_seconds: int = 120,
    poll_seconds: float = 5.0,
) -> dict[str, Any]:
    """Wait for a job to finish or until a bounded timeout expires.

    Use this after submit_clip_job so one Hermes turn can remain active while the
    background worker processes the video. The timeout is capped at five minutes.
    """
    timeout = max(1, min(int(timeout_seconds), 300))
    interval = max(1.0, min(float(poll_seconds), 30.0))
    deadline = time.monotonic() + timeout
    record = get_job(job_id, jobs_root=_jobs_root())
    while record.get("status") not in {"completed", "failed", "cancelled"}:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
        record = get_job(job_id, jobs_root=_jobs_root())
    summary = _job_summary(record)
    summary["timed_out"] = record.get("status") not in {"completed", "failed", "cancelled"}
    return summary


@mcp.tool()
def list_clip_outputs(job_id: str) -> dict[str, Any]:
    """Return absolute final MP4 paths for a completed job.

    Hermes can include each path as MEDIA:/absolute/path.mp4 to deliver it to
    Telegram as a native attachment.
    """
    record = get_job(job_id, jobs_root=_jobs_root())
    outputs = list_outputs(job_id, jobs_root=_jobs_root())
    return {
        "job_id": job_id,
        "status": record["status"],
        "outputs": outputs,
        "media_tags": [f"MEDIA:{path}" for path in outputs],
    }


@mcp.tool()
def cancel_clip_job(job_id: str) -> dict[str, Any]:
    """Cancel a queued job or request cancellation of a running job."""
    record = cancel_job(job_id, jobs_root=_jobs_root())
    return {
        "job_id": job_id,
        "status": record["status"],
        "cancel_requested": record.get("cancel_requested", False),
        "progress": record.get("progress"),
    }


def main() -> None:
    project_root = os.environ.get("CLIPPER_PROJECT_ROOT")
    if project_root:
        os.chdir(Path(project_root).expanduser().resolve())
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
