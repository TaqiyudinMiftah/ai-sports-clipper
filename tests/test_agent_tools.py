import json
from pathlib import Path

import pytest

from sports_clipper.agent_tools import get_clip_job
from sports_clipper.simple_cli import build_parser


def test_get_clip_job_reads_manifest(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-1"
    job_dir.mkdir()
    (job_dir / "job.json").write_text(
        json.dumps({"job_id": "job-1", "status": "completed"}),
        encoding="utf-8",
    )
    payload = get_clip_job("job-1", jobs_root=tmp_path)
    assert payload["status"] == "completed"


def test_get_clip_job_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        get_clip_job("../secret", jobs_root=tmp_path)


def test_simple_cli_defaults() -> None:
    args = build_parser().parse_args(["match.mp4"])
    assert args.clips == 3
    assert args.duration == 20.0
    assert args.confirm_rights is False
