import json
from pathlib import Path

from sports_clipper.job_queue import (
    cancel_clip_job,
    claim_next_job,
    enqueue_clip_job,
    list_clip_outputs,
    load_queued_request,
    update_job_manifest,
)


def test_enqueue_clip_job_writes_manifest_request_and_ticket(tmp_path: Path) -> None:
    result = enqueue_clip_job(
        {"source": "match.mp4", "clip_count": 2},
        jobs_root=tmp_path,
    )

    job_id = str(result["job_id"])
    job_dir = tmp_path / job_id
    assert result["status"] == "queued"
    assert (job_dir / "job.json").is_file()
    assert (job_dir / "request.json").is_file()
    assert (tmp_path / "_queue" / "pending" / f"{job_id}.json").is_file()

    request = load_queued_request(job_id, jobs_root=tmp_path)
    assert request.clip_count == 2
    assert request.jobs_root == tmp_path.resolve()

    claimed = claim_next_job(tmp_path)
    assert claimed is not None
    ticket, ticket_path = claimed
    assert ticket["job_id"] == job_id
    assert ticket_path.parent.name == "running"


def test_cancel_pending_job_moves_ticket_and_updates_manifest(tmp_path: Path) -> None:
    result = enqueue_clip_job({"source": "match.mp4"}, jobs_root=tmp_path)
    job_id = str(result["job_id"])

    cancelled = cancel_clip_job(job_id, jobs_root=tmp_path)

    assert cancelled["status"] == "cancelled"
    assert not (tmp_path / "_queue" / "pending" / f"{job_id}.json").exists()
    assert (tmp_path / "_queue" / "cancelled" / f"{job_id}.json").is_file()


def test_list_clip_outputs_returns_only_existing_paths_inside_job(tmp_path: Path) -> None:
    result = enqueue_clip_job({"source": "match.mp4"}, jobs_root=tmp_path)
    job_id = str(result["job_id"])
    final_path = tmp_path / job_id / "final" / "clip_01_social.mp4"
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"video")

    update_job_manifest(
        job_id,
        tmp_path,
        status="completed",
        clips=[{"index": 1, "final_path": str(final_path)}],
    )

    outputs = list_clip_outputs(job_id, jobs_root=tmp_path)
    assert outputs["ready"] is True
    assert outputs["media_paths"] == [str(final_path.resolve())]
    assert outputs["outputs"][0]["media_tag"].startswith("MEDIA:")

    manifest = json.loads((tmp_path / job_id / "job.json").read_text())
    assert manifest["status"] == "completed"
