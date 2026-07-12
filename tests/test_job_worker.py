from pathlib import Path

from sports_clipper.job_queue import enqueue_clip_job, list_clip_outputs
from sports_clipper.job_worker import process_next_job


def test_worker_processes_one_job_with_injected_processor(tmp_path: Path) -> None:
    queued = enqueue_clip_job({"source": "match.mp4"}, jobs_root=tmp_path)
    job_id = str(queued["job_id"])

    def fake_processor(request, *, progress, job_id):
        progress("analyzing", "Synthetic analysis")
        final_path = request.jobs_root / job_id / "final" / "clip_01_social.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"video")
        return {
            "job_id": job_id,
            "clips": [
                {
                    "index": 1,
                    "score": 0.9,
                    "start_time": 1.0,
                    "end_time": 11.0,
                    "candidate_path": "candidate.mp4",
                    "reframed_path": "vertical.mp4",
                    "final_path": str(final_path),
                    "reasons": ["test"],
                }
            ],
        }

    manifest = process_next_job(
        tmp_path,
        processor=fake_processor,
        reporter=None,
    )

    assert manifest is not None
    assert manifest["status"] == "completed"
    assert (tmp_path / "_queue" / "completed" / f"{job_id}.json").is_file()
    outputs = list_clip_outputs(job_id, jobs_root=tmp_path)
    assert outputs["ready"] is True
    assert len(outputs["media_paths"]) == 1


def test_worker_records_processor_failure(tmp_path: Path) -> None:
    queued = enqueue_clip_job({"source": "match.mp4"}, jobs_root=tmp_path)
    job_id = str(queued["job_id"])

    def failing_processor(request, *, progress, job_id):
        progress("analyzing", "About to fail")
        raise RuntimeError("synthetic failure")

    manifest = process_next_job(
        tmp_path,
        processor=failing_processor,
        reporter=None,
    )

    assert manifest is not None
    assert manifest["status"] == "failed"
    assert manifest["error"] == "synthetic failure"
    assert (tmp_path / "_queue" / "failed" / f"{job_id}.json").is_file()
