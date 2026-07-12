from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .audio_analysis import analyze_audio_windows, extract_mono_audio
from .ball_reframe import reframe_video
from .brand_assets import PPL_DEFAULT_LOGO_PATH, download_ppl_logo
from .candidate_detection import build_timeline, detect_candidates
from .clip_exporter import export_clip
from .motion_analysis import analyze_motion_windows
from .scoring import rank_candidates
from .social_composer import compose_social_video
from .source_ingestion import resolve_source
from .video_info import get_video_info


class PipelineError(RuntimeError):
    """Raised when the unified clipping pipeline cannot complete."""


ProgressCallback = Callable[[str, str], None]


@dataclass(frozen=True)
class ClipRequest:
    source: str
    clip_count: int = 3
    target_duration: float = 20.0
    threshold: float = 0.62
    sample_fps: float = 2.0
    slowmo_speed: float = 0.4
    reframe: bool = True
    confirm_rights: bool = False
    jobs_root: Path = field(default_factory=lambda: Path("data/jobs"))
    logo_path: Path = field(default_factory=lambda: PPL_DEFAULT_LOGO_PATH)

    def validate(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")
        if not 1 <= self.clip_count <= 20:
            raise ValueError("clip_count must be between 1 and 20")
        if self.target_duration < 10:
            raise ValueError("target_duration must be at least 10 seconds")
        if not 0 < self.threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if self.sample_fps <= 0:
            raise ValueError("sample_fps must be positive")
        if not 0.25 <= self.slowmo_speed < 1:
            raise ValueError("slowmo_speed must be between 0.25 and 1.0")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["jobs_root"] = str(self.jobs_root)
        payload["logo_path"] = str(self.logo_path)
        return payload


@dataclass(frozen=True)
class ClipOutput:
    index: int
    score: float
    start_time: float
    end_time: float
    candidate_path: str
    reframed_path: str
    final_path: str
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ClipJobResult:
    job_id: str
    job_dir: str
    source_path: str
    clips: list[ClipOutput]
    manifest_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "job_dir": self.job_dir,
            "source_path": self.source_path,
            "clips": [clip.to_dict() for clip in self.clips],
            "manifest_path": self.manifest_path,
        }


def create_job_id(source: str, now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:8]
    return f"{moment.strftime('%Y%m%dT%H%M%SZ')}-{digest}"


def validate_job_id(job_id: str) -> str:
    if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
        raise ValueError("invalid job_id")
    return job_id


def _emit(callback: ProgressCallback | None, state: str, message: str) -> None:
    if callback is not None:
        callback(state, message)


def _analyze_video(
    video: Path,
    *,
    clip_count: int,
    threshold: float,
    sample_fps: float,
) -> tuple[object, list[object]]:
    info = get_video_info(video)
    with tempfile.TemporaryDirectory(prefix="clipper-analyze-") as temp_dir:
        wav_path = Path(temp_dir) / "audio.wav"
        if info.has_audio:
            extract_mono_audio(video, wav_path)
            audio_scores = analyze_audio_windows(wav_path)
        else:
            audio_scores = [0.0] * max(1, int(info.duration))
        motion_scores = analyze_motion_windows(
            video,
            duration=info.duration,
            sample_fps=sample_fps,
        )

    timeline = build_timeline(audio_scores, motion_scores)
    candidates = rank_candidates(
        detect_candidates(timeline, threshold=threshold, minimum_duration=10)
    )[:clip_count]
    return info, candidates


def process_clip_request(
    request: ClipRequest,
    *,
    progress: ProgressCallback | None = None,
    job_id: str | None = None,
) -> ClipJobResult:
    request.validate()
    resolved_job_id = validate_job_id(job_id) if job_id is not None else create_job_id(request.source)
    job_dir = request.jobs_root.expanduser() / resolved_job_id
    source_dir = job_dir / "source"
    candidates_dir = job_dir / "candidates"
    reframed_dir = job_dir / "reframed"
    final_dir = job_dir / "final"
    reports_dir = job_dir / "reports"
    for directory in (source_dir, candidates_dir, reframed_dir, final_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    manifest_path = job_dir / "job.json"
    now = datetime.now(timezone.utc).isoformat()
    existing: dict[str, object] = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}

    manifest: dict[str, object] = {
        **existing,
        "job_id": resolved_job_id,
        "status": "received",
        "created_at": existing.get("created_at", now),
        "started_at": now,
        "updated_at": now,
        "request": request.to_dict(),
        "clips": [],
    }

    def save_manifest() -> None:
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def set_status(state: str, message: str) -> None:
        manifest["status"] = state
        manifest["progress_message"] = message
        save_manifest()
        _emit(progress, state, message)

    save_manifest()

    try:
        set_status("validating", "Resolving video source")
        source = resolve_source(request.source, confirm_rights=request.confirm_rights)

        set_status("downloading", "Acquiring source video")
        source_path, source_record = source.acquire(source_dir)
        manifest["source"] = source_record
        save_manifest()

        logo_path = request.logo_path.expanduser()
        if not logo_path.is_file():
            set_status("assets", "Downloading official PPL logo")
            download_ppl_logo(logo_path)

        set_status("analyzing", "Finding highlight candidates")
        source_info, candidates = _analyze_video(
            source_path,
            clip_count=request.clip_count,
            threshold=request.threshold,
            sample_fps=request.sample_fps,
        )
        if not candidates:
            raise PipelineError(
                "No highlight candidates were found. Try a lower --threshold value."
            )
        manifest["source_video"] = source_info.to_dict()
        save_manifest()

        outputs: list[ClipOutput] = []
        for index, candidate in enumerate(candidates, start=1):
            set_status(
                "rendering",
                f"Rendering clip {index} of {len(candidates)}",
            )
            candidate_path = candidates_dir / f"clip_{index:02d}_candidate.mp4"
            export_clip(
                source_path,
                candidate_path,
                candidate.start_time,
                candidate.end_time,
            )

            reframed_path = reframed_dir / f"clip_{index:02d}_vertical.mp4"
            if request.reframe:
                reframe_video(candidate_path, reframed_path)
            else:
                reframed_path = candidate_path

            final_path = final_dir / f"clip_{index:02d}_social.mp4"
            compose_social_video(
                reframed_path,
                final_path,
                logo_path,
                target_duration=request.target_duration,
                slowmo_speed=request.slowmo_speed,
            )

            output = ClipOutput(
                index=index,
                score=float(candidate.score),
                start_time=float(candidate.start_time),
                end_time=float(candidate.end_time),
                candidate_path=str(candidate_path),
                reframed_path=str(reframed_path),
                final_path=str(final_path),
                reasons=list(candidate.reasons),
            )
            outputs.append(output)
            manifest["clips"] = [item.to_dict() for item in outputs]
            save_manifest()

        manifest["status"] = "completed"
        manifest["progress_message"] = f"Created {len(outputs)} social clips"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["clips"] = [item.to_dict() for item in outputs]
        save_manifest()
        _emit(progress, "completed", f"Created {len(outputs)} social clips")
        return ClipJobResult(
            job_id=resolved_job_id,
            job_dir=str(job_dir),
            source_path=str(source_path),
            clips=outputs,
            manifest_path=str(manifest_path),
        )
    except Exception as error:
        manifest["status"] = "failed"
        manifest["progress_message"] = str(error)
        manifest["failed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["error"] = str(error)
        save_manifest()
        _emit(progress, "failed", str(error))
        raise
