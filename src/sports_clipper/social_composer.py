from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .drive_download import sha256_file
from .video_info import get_video_info, require_binary


class SocialComposeError(RuntimeError):
    """Raised when a social-ready edit cannot be composed."""


@dataclass(frozen=True)
class SocialEditPlan:
    source_duration: float
    target_duration: float
    normal_start: float
    normal_end: float
    replay_start: float
    replay_end: float
    slowmo_speed: float
    replay_output_duration: float
    hold_duration: float

    @property
    def normal_duration(self) -> float:
        return self.normal_end - self.normal_start

    @property
    def composed_duration(self) -> float:
        return self.normal_duration + self.replay_output_duration + self.hold_duration

    def to_dict(self) -> dict[str, float]:
        payload = asdict(self)
        payload["normal_duration"] = self.normal_duration
        payload["composed_duration"] = self.composed_duration
        return {key: round(float(value), 4) for key, value in payload.items()}


def atempo_chain(speed: float) -> str:
    """Return an FFmpeg atempo chain for a playback speed from 0.25 to 2.0."""
    if not 0.25 <= speed <= 2.0:
        raise ValueError("slowmo speed must be between 0.25 and 2.0")

    remaining = speed
    factors: list[float] = []
    while remaining < 0.5 - 1e-9:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0 + 1e-9:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return ",".join(f"atempo={factor:.6f}" for factor in factors)


def build_social_edit_plan(
    source_duration: float,
    *,
    target_duration: float = 20.0,
    slowmo_speed: float = 0.4,
    replay_source_seconds: float | None = None,
    minimum_replay_output: float = 3.0,
    maximum_auto_replay_source: float = 4.0,
) -> SocialEditPlan:
    """Plan normal playback followed by a slow-motion replay of the ending."""
    if source_duration <= 0:
        raise ValueError("source duration must be positive")
    if target_duration < 10:
        raise ValueError("target duration must be at least 10 seconds")
    if not 0.25 <= slowmo_speed < 1.0:
        raise ValueError("slowmo speed must be between 0.25 and 1.0")
    if minimum_replay_output <= 0 or maximum_auto_replay_source <= 0:
        raise ValueError("replay duration limits must be positive")

    if replay_source_seconds is not None:
        if replay_source_seconds <= 0:
            raise ValueError("replay source duration must be positive")
        replay_source = min(replay_source_seconds, source_duration)
        replay_output = replay_source / slowmo_speed
        normal_duration = min(source_duration, max(0.5, target_duration - replay_output))
    elif source_duration <= target_duration - minimum_replay_output:
        normal_duration = source_duration
        required_source = (target_duration - normal_duration) * slowmo_speed
        replay_source = min(
            source_duration,
            max(0.5, min(maximum_auto_replay_source, required_source)),
        )
        replay_output = replay_source / slowmo_speed
    else:
        replay_output = minimum_replay_output
        replay_source = replay_output * slowmo_speed
        normal_duration = min(source_duration, target_duration - replay_output)

    normal_start = max(0.0, source_duration - normal_duration)
    normal_end = source_duration
    replay_end = source_duration
    replay_start = max(normal_start, replay_end - replay_source)
    actual_replay_source = replay_end - replay_start
    replay_output = actual_replay_source / slowmo_speed
    hold_duration = max(0.0, target_duration - normal_duration - replay_output)

    return SocialEditPlan(
        source_duration=source_duration,
        target_duration=target_duration,
        normal_start=normal_start,
        normal_end=normal_end,
        replay_start=replay_start,
        replay_end=replay_end,
        slowmo_speed=slowmo_speed,
        replay_output_duration=replay_output,
        hold_duration=hold_duration,
    )


def _fit_vertical_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def compose_social_video(
    source: Path,
    destination: Path,
    logo: Path,
    *,
    target_duration: float = 20.0,
    slowmo_speed: float = 0.4,
    replay_source_seconds: float | None = None,
    output_width: int = 1080,
    output_height: int = 1920,
    logo_width: int = 300,
    logo_bottom_margin: int = 170,
    logo_opacity: float = 0.94,
) -> dict[str, object]:
    """Compose normal playback plus a slow-motion ending replay and watermark."""
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    logo = logo.expanduser().resolve()

    if not source.is_file():
        raise FileNotFoundError(f"Video not found: {source}")
    if not logo.is_file():
        raise FileNotFoundError(
            f"Logo not found: {logo}. Run 'sports-clipper download-logo' first."
        )
    if output_width <= 0 or output_height <= 0 or output_width % 2 or output_height % 2:
        raise ValueError("output dimensions must be positive even numbers")
    if logo_width <= 0 or logo_bottom_margin < 0:
        raise ValueError("logo dimensions and margin must be valid")
    if not 0 < logo_opacity <= 1:
        raise ValueError("logo opacity must be between 0 and 1")

    info = get_video_info(source)
    if not info.has_audio:
        raise SocialComposeError(
            "The source video has no audio. Campaign edits must preserve gameplay audio."
        )

    plan = build_social_edit_plan(
        info.duration,
        target_duration=target_duration,
        slowmo_speed=slowmo_speed,
        replay_source_seconds=replay_source_seconds,
    )
    fit = _fit_vertical_filter(output_width, output_height)
    audio_speed = atempo_chain(slowmo_speed)
    hold = plan.hold_duration

    filter_parts = [
        (
            f"[0:v]trim=start={plan.normal_start:.6f}:end={plan.normal_end:.6f},"
            f"setpts=PTS-STARTPTS,{fit}[normalv]"
        ),
        (
            f"[0:a]atrim=start={plan.normal_start:.6f}:end={plan.normal_end:.6f},"
            "asetpts=PTS-STARTPTS[normala]"
        ),
        (
            f"[0:v]trim=start={plan.replay_start:.6f}:end={plan.replay_end:.6f},"
            f"setpts=(PTS-STARTPTS)/{slowmo_speed:.6f},{fit}[replayv]"
        ),
        (
            f"[0:a]atrim=start={plan.replay_start:.6f}:end={plan.replay_end:.6f},"
            f"asetpts=PTS-STARTPTS,{audio_speed}[replaya]"
        ),
        "[normalv][normala][replayv][replaya]concat=n=2:v=1:a=1[editv][edita]",
        (
            f"[1:v]scale={logo_width}:-1,format=rgba,"
            f"colorchannelmixer=aa={logo_opacity:.4f}[logo]"
        ),
    ]

    video_tail = (
        f"[editv][logo]overlay=(W-w)/2:H-h-{logo_bottom_margin}:"
        "eof_action=repeat:format=auto"
    )
    if hold > 1e-3:
        video_tail += f",tpad=stop_mode=clone:stop_duration={hold:.6f}"
    video_tail += f",trim=duration={target_duration:.6f},setpts=PTS-STARTPTS[outv]"
    filter_parts.append(video_tail)

    audio_tail = "[edita]"
    if hold > 1e-3:
        audio_tail += f"apad=pad_dur={hold:.6f},"
    audio_tail += f"atrim=duration={target_duration:.6f},asetpts=PTS-STARTPTS[outa]"
    filter_parts.append(audio_tail)

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_binary("ffmpeg"),
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-loop",
        "1",
        "-i",
        str(logo),
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[outv]",
        "-map",
        "[outa]",
        "-t",
        f"{target_duration:.6f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "FFmpeg composition failed").strip()
        raise SocialComposeError(details)
    if not destination.is_file():
        raise SocialComposeError("FFmpeg completed without creating the social edit")

    warnings: list[str] = []
    if plan.normal_start > 0.05:
        warnings.append(
            "The source was longer than the target; the composer preserved the ending "
            "and trimmed time from the beginning."
        )
    if plan.replay_output_duration > 7.0:
        warnings.append(
            "The source clip was short, so the automatic slow-motion replay is longer "
            "than seven seconds. Use --replay-source-seconds to shorten it."
        )
    if plan.hold_duration > 1.0:
        warnings.append(
            "The edit needed an ending freeze to reach the target duration. Use a longer "
            "source clip or a longer replay selection for a more natural result."
        )

    report: dict[str, object] = {
        "source": info.to_dict(),
        "destination": str(destination),
        "output": {
            "duration": target_duration,
            "width": output_width,
            "height": output_height,
        },
        "plan": plan.to_dict(),
        "watermark": {
            "path": str(logo),
            "sha256": sha256_file(logo),
            "width": logo_width,
            "bottom_margin": logo_bottom_margin,
            "opacity": logo_opacity,
        },
        "warnings": warnings,
    }
    report_path = destination.with_suffix(".compose.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
