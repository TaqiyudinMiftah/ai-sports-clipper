from pathlib import Path

from sports_clipper.job_queue import (
    cancel_job,
    claim_next_job,
    finish_job,
    get_job,
    list_outputs,
    submit_job,
)


def test_submit_claim_and_finish_job(tmp_path: Path) -> None:
    record = submit_job({"source": "match.mp4", "clip_count": 2}, jobs_root=tmp_path)
    job_id = str(record["job_id"])

    assert get_job(job_id, jobs_root=tmp_path)["status"] == "queued"

    claimed = claim_next_job(jobs_root=tmp_path)
    assert claimed is not None
    assert claimed["job_id"] == job_id
    assert get_job(job_id, jobs_root=tmp_path)["status"] == "running"

    output = tmp_path / job_id / "final.mp4"
    output.write_bytes(b"video")
    finished = finish_job(
        job_id,
        status="completed",
        changes={"clips": [{"final_path": str(output)}]},
        jobs_root=tmp_path,
    )

    assert finished["status"] == "completed"
    assert list_outputs(job_id, jobs_root=tmp_path) == [str(output.resolve())]


def test_cancel_pending_job(tmp_path: Path) -> None:
    record = submit_job({"source": "match.mp4"}, jobs_root=tmp_path)
    cancelled = cancel_job(str(record["job_id"]), jobs_root=tmp_path)

    assert cancelled["status"] == "cancelled"
    assert claim_next_job(jobs_root=tmp_path) is None


def test_cancel_running_job_sets_request_flag(tmp_path: Path) -> None:
    record = submit_job({"source": "match.mp4"}, jobs_root=tmp_path)
    job_id = str(record["job_id"])
    assert claim_next_job(jobs_root=tmp_path) is not None

    cancelled = cancel_job(job_id, jobs_root=tmp_path)

    assert cancelled["status"] == "running"
    assert cancelled["cancel_requested"] is True
