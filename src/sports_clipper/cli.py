from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .audio_analysis import analyze_audio_windows, extract_mono_audio
from .candidate_detection import build_timeline, detect_candidates
from .clip_exporter import export_clip
from .motion_analysis import analyze_motion_windows
from .scoring import rank_candidates
from .video_info import MediaToolError, get_video_info


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def inspect_command(video: Path) -> int:
    info = get_video_info(video)
    print(json.dumps(info.to_dict(), indent=2))
    return 0


def analyze_command(
    video: Path,
    output_dir: Path,
    report_dir: Path,
    top: int,
    threshold: float,
    sample_fps: float,
    export: bool,
) -> int:
    info = get_video_info(video)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sports-clipper-") as temp_dir:
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
    )[:top]

    exported: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        name = f"candidate_{index:02d}_score_{round(candidate.score):03d}.mp4"
        destination = output_dir / name
        if export:
            export_clip(video, destination, candidate.start_time, candidate.end_time)
            exported.append(str(destination))
        print(
            f"{index}. {_format_time(candidate.start_time)}-"
            f"{_format_time(candidate.end_time)} score={candidate.score:.2f} "
            f"reasons={'; '.join(candidate.reasons)}"
        )

    report = {
        "source": info.to_dict(),
        "settings": {
            "threshold": threshold,
            "sample_fps": sample_fps,
            "top": top,
            "clips_exported": export,
        },
        "candidates": [candidate.to_dict() for candidate in candidates],
        "exported_files": exported,
    }
    report_path = report_dir / f"{video.stem}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved to {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sports-clipper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect video metadata")
    inspect_parser.add_argument("video", type=Path)

    analyze_parser = subparsers.add_parser(
        "analyze", help="Find and optionally export highlight candidates"
    )
    analyze_parser.add_argument("video", type=Path)
    analyze_parser.add_argument("--output", type=Path, default=Path("data/output"))
    analyze_parser.add_argument("--reports", type=Path, default=Path("data/reports"))
    analyze_parser.add_argument("--top", type=int, default=5)
    analyze_parser.add_argument("--threshold", type=float, default=0.62)
    analyze_parser.add_argument("--sample-fps", type=float, default=2.0)
    analyze_parser.add_argument(
        "--no-export",
        action="store_true",
        help="Generate timestamps and a report without rendering MP4 clips",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "inspect":
            return inspect_command(args.video)
        return analyze_command(
            video=args.video,
            output_dir=args.output,
            report_dir=args.reports,
            top=max(1, args.top),
            threshold=args.threshold,
            sample_fps=args.sample_fps,
            export=not args.no_export,
        )
    except (FileNotFoundError, ValueError, RuntimeError, MediaToolError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    raise SystemExit(main())
