from pathlib import Path

from sports_clipper.hermes_mcp import (
    cancel_clip_job_request,
    get_clip_job_status,
    normalize_source,
    submit_clip_job_request,
)


def test_normalize_source_keeps_youtube_and_resolves_local_paths(tmp_path: Path) -> None:
    youtube = "https://www.youtube.com/watch?v=abc123"
    assert normalize_source(youtube, project_root=tmp_path) == youtube
    assert normalize_source("videos/match.mov", project_root=tmp_path) == str(
        (tmp_path / "videos/match.mov").resolve()
    )


def test_submit_status_and_cancel_helpers_use_shared_job_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    jobs_root = project_root / "data/jobs"

    queued = submit_clip_job_request(
        "videos/match.mov",
        clip_count=2,
        project_root=project_root,
        jobs_root=jobs_root,
    )
    job_id = str(queued["job_id"])

    status = get_clip_job_status(job_id, jobs_root=jobs_root)
    assert status["status"] == "queued"
    assert status["clip_count"] == 0

    cancelled = cancel_clip_job_request(job_id, jobs_root=jobs_root)
    assert cancelled["status"] == "cancelled"
