from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .unified_pipeline import ClipRequest, process_clip_request


AgentProgressCallback = Callable[[str, str], None]


def create_clip_job(
    payload: dict[str, object],
    *,
    progress: AgentProgressCallback | None = None,
) -> dict[str, object]:
    """Stable tool contract for chat agents and future messaging adapters."""
    source = payload.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("payload.source must be a non-empty string")

    request = ClipRequest(
        source=source,
        clip_count=int(payload.get("clip_count", 3)),
        target_duration=float(payload.get("target_duration", 20.0)),
        threshold=float(payload.get("threshold", 0.62)),
        sample_fps=float(payload.get("sample_fps", 2.0)),
        slowmo_speed=float(payload.get("slowmo_speed", 0.4)),
        reframe=bool(payload.get("reframe", True)),
        confirm_rights=bool(payload.get("confirm_rights", False)),
        jobs_root=Path(str(payload.get("jobs_root", "data/jobs"))),
    )
    return process_clip_request(request, progress=progress).to_dict()


def get_clip_job(job_id: str, *, jobs_root: Path = Path("data/jobs")) -> dict[str, object]:
    """Read the durable job manifest used by CLI and future bots."""
    if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
        raise ValueError("invalid job_id")
    manifest_path = jobs_root.expanduser() / job_id / "job.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Job not found: {job_id}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid job manifest: {manifest_path}")
    return payload
