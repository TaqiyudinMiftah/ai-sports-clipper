from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from .agent_tools import get_clip_job as read_clip_job
from .brand_assets import PPL_DEFAULT_LOGO_PATH
from .job_queue import (
    TERMINAL_STATUSES,
    cancel_clip_job as request_job_cancellation,
    enqueue_clip_job,
    list_clip_outputs as read_clip_outputs,
    resolve_jobs_root,
)
from .source_ingestion import is_youtube_url


def resolve_project_root(project_root: Path | str | None = None) -> Path:
    configured = project_root or os.environ.get("CLIPPER_PROJECT_ROOT") or Path.cwd()
    return Path(configured).expanduser().resolve()


def normalize_source(source: str, *, project_root: Path) -> str:
    value = source.strip()
    if not value:
        raise ValueError("source is required")
    if is_youtube_url(value):
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return str(path.resolve())


def submit_clip_job_request(
    source: str,
    clip_count: int = 3,
    target_duration: float = 20.0,
    slowmo_speed: float = 0.4,
    threshold: float = 0.62,
    reframe: bool = True,
    confirm_rights: bool = False,
    *,
    project_root: Path | str | None = None,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Queue an authorized PPL clipping request and return immediately."""
    root = resolve_project_root(project_root)
    jobs = resolve_jobs_root(jobs_root or root / "data/jobs")
    payload: dict[str, object] = {
        "source": normalize_source(source, project_root=root),
        "clip_count": clip_count,
        "target_duration": target_duration,
        "slowmo_speed": slowmo_speed,
        "threshold": threshold,
        "reframe": reframe,
        "confirm_rights": confirm_rights,
        "jobs_root": str(jobs),
        "logo_path": str((root / PPL_DEFAULT_LOGO_PATH).resolve()),
    }
    return enqueue_clip_job(payload, jobs_root=jobs)


def get_clip_job_status(
    job_id: str,
    *,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return the durable state and progress message for one clip job."""
    jobs = resolve_jobs_root(jobs_root)
    manifest = read_clip_job(job_id, jobs_root=jobs)
    return {
        "job_id": manifest.get("job_id"),
        "status": manifest.get("status"),
        "progress_message": manifest.get("progress_message"),
        "created_at": manifest.get("created_at"),
        "updated_at": manifest.get("updated_at"),
        "completed_at": manifest.get("completed_at"),
        "error": manifest.get("error"),
        "clip_count": len(manifest.get("clips", []))
        if isinstance(manifest.get("clips"), list)
        else 0,
    }


def wait_for_clip_job_status(
    job_id: str,
    timeout_seconds: int = 120,
    poll_seconds: float = 5.0,
    *,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Wait until a job finishes or a bounded timeout expires.

    The timeout is capped at five minutes so a Hermes tool call cannot block
    indefinitely. A timed-out response is not a failure; Hermes can report the
    job ID and check again in a later turn.
    """
    timeout = max(1, min(int(timeout_seconds), 300))
    interval = max(0.25, min(float(poll_seconds), 30.0))
    deadline = time.monotonic() + timeout
    status = get_clip_job_status(job_id, jobs_root=jobs_root)

    while status.get("status") not in TERMINAL_STATUSES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
        status = get_clip_job_status(job_id, jobs_root=jobs_root)

    status["timed_out"] = status.get("status") not in TERMINAL_STATUSES
    return status


def list_clip_job_outputs(
    job_id: str,
    *,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return absolute MP4 paths suitable for Hermes Telegram MEDIA delivery."""
    return read_clip_outputs(job_id, jobs_root=resolve_jobs_root(jobs_root))


def cancel_clip_job_request(
    job_id: str,
    *,
    jobs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Cancel a queued job or request cancellation of a running job."""
    return request_job_cancellation(job_id, jobs_root=resolve_jobs_root(jobs_root))


def build_server(
    *,
    project_root: Path | str | None = None,
    jobs_root: Path | str | None = None,
):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "Hermes MCP support is not installed. Run "
            "python -m pip install -e '.[hermes]'"
        ) from error

    root = resolve_project_root(project_root)
    jobs = resolve_jobs_root(jobs_root or root / "data/jobs")
    server = FastMCP("AI Sports Clipper")

    @server.tool()
    def submit_clip_job(
        source: str,
        clip_count: int = 3,
        target_duration: float = 20.0,
        slowmo_speed: float = 0.4,
        threshold: float = 0.62,
        reframe: bool = True,
        confirm_rights: bool = False,
    ) -> dict[str, Any]:
        """Queue social clips from authorized PPL local or YouTube footage."""
        return submit_clip_job_request(
            source,
            clip_count,
            target_duration,
            slowmo_speed,
            threshold,
            reframe,
            confirm_rights,
            project_root=root,
            jobs_root=jobs,
        )

    @server.tool()
    def get_clip_job(job_id: str) -> dict[str, Any]:
        """Check queued clip progress, completion, cancellation, or failure."""
        return get_clip_job_status(job_id, jobs_root=jobs)

    @server.tool()
    def wait_for_clip_job(
        job_id: str,
        timeout_seconds: int = 120,
        poll_seconds: float = 5.0,
    ) -> dict[str, Any]:
        """Wait up to five minutes for a job to reach a terminal state."""
        return wait_for_clip_job_status(
            job_id,
            timeout_seconds,
            poll_seconds,
            jobs_root=jobs,
        )

    @server.tool()
    def list_clip_outputs(job_id: str) -> dict[str, Any]:
        """List completed absolute MP4 paths for native Telegram delivery."""
        return list_clip_job_outputs(job_id, jobs_root=jobs)

    @server.tool()
    def cancel_clip_job(job_id: str) -> dict[str, Any]:
        """Cancel a queued clip job or request cooperative cancellation."""
        return cancel_clip_job_request(job_id, jobs_root=jobs)

    return server


def main() -> int:
    root = resolve_project_root()
    os.chdir(root)
    server = build_server(project_root=root)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
