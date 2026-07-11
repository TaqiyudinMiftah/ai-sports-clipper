from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .audio_analysis import analyze_audio_windows, extract_mono_audio
from .ball_reframe import (
    ReframeError,
    parse_normalized_roi,
    reframe_video,
)
from .candidate_detection import build_timeline, detect_candidates
from .clip_exporter import export_clip
from .drive_download import (
    DEFAULT_VIDEO_EXTENSIONS,
    PPL_SOURCE_FOLDER_URL,
    DriveDownloadError,
    download_drive_folder,
)
from .motion_analysis import analyze_motion_windows
from .scoring import rank_candidates
from .video_info import MediaToolError, get_video_info


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_bytes(size: object) -> str:
    if not isinstance(size, int):
        return "unknown size"
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def inspect_command(video: Path) -> int:
    info = get_video_info(video)
    print(json.dumps(info.to_dict(), indent=2))
    return 0


def download_drive_command(
    folder_url: str,
    output_dir: Path,
    extensions: list[str],
    overwrite: bool,
    compute_hashes: bool,
    list_only: bool,
) -> int:
    manifest = download_drive_folder(
        folder_url,
        output_dir,
        extensions=extensions,
        overwrite=overwrite,
        compute_hashes=compute_hashes,
        list_only=list_only,
    )
    for record in manifest["files"]:
        print(
            f"[{record['status']}] {record['relative_path']} "
            f"({_format_bytes(record.get('size_bytes'))})"
        )
    print(f"Source manifest saved to {manifest['manifest_path']}")
    return 0


def reframe_command(
    video: Path,
    output: Path | None,
    zoom: float,
    width: int,
    height: int,
    roi: tuple[float, float, float, float],
    smoothing: float,
    analysis_width: int,
    debug_overlay: bool,
) -> int:
    destination = output or Path("data/output") / f"{video.stem}_ball_follow.mp4"
    report = reframe_video(
        video,
        destination,
        zoom=zoom,
        output_width=width,
        output_height=height,
        roi=roi,
        smoothing=smoothing,
        analysis_width=analysis_width,
        debug_overlay=debug_overlay,
    )
    print(json.dumps(report, indent=2))
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

    download_parser = subparsers.add_parser(
        "download-drive",
        help="Download approved video sources from a public Google Drive folder",
    )
    download_parser.add_argument(
        "folder_url",
        nargs="?",
        default=PPL_SOURCE_FOLDER_URL,
        help="Public Drive folder URL; defaults to the PPL campaign source folder",
    )
    download_parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/input/ppl"),
    )
    download_parser.add_argument(
        "--extensions",
        nargs="+",
        default=list(DEFAULT_VIDEO_EXTENSIONS),
        help="Allowed video extensions",
    )
    download_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace completed files instead of skipping them",
    )
    download_parser.add_argument(
        "--no-hash",
        action="store_true",
        help="Skip SHA-256 calculation for faster manifest generation",
    )
    download_parser.add_argument(
        "--list-only",
        action="store_true",
        help="List matching files and write a manifest without downloading bytes",
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect video metadata")
    inspect_parser.add_argument("video", type=Path)

    reframe_parser = subparsers.add_parser(
        "reframe",
        help="Create a smooth vertical crop that follows the likely rally ball",
    )
    reframe_parser.add_argument("video", type=Path)
    reframe_parser.add_argument(
        "--output",
        type=Path,
        help="Output MP4; defaults to data/output/<name>_ball_follow.mp4",
    )
    reframe_parser.add_argument("--zoom", type=float, default=1.4)
    reframe_parser.add_argument("--width", type=int, default=1080)
    reframe_parser.add_argument("--height", type=int, default=1920)
    reframe_parser.add_argument(
        "--roi",
        type=parse_normalized_roi,
        default=parse_normalized_roi("0.02,0.14,0.98,0.76"),
        help="Normalized court ROI: left,top,right,bottom",
    )
    reframe_parser.add_argument(
        "--smoothing",
        type=float,
        default=0.16,
        help="Camera response from 0 to 1; lower values move more smoothly",
    )
    reframe_parser.add_argument(
        "--analysis-width",
        type=int,
        default=540,
        help="Width used by the detector; lower values are faster",
    )
    reframe_parser.add_argument(
        "--debug-overlay",
        action="store_true",
        help="Draw tracking mode and crop-center markers on the output",
    )

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
        if args.command == "download-drive":
            return download_drive_command(
                folder_url=args.folder_url,
                output_dir=args.output,
                extensions=args.extensions,
                overwrite=args.overwrite,
                compute_hashes=not args.no_hash,
                list_only=args.list_only,
            )
        if args.command == "inspect":
            return inspect_command(args.video)
        if args.command == "reframe":
            return reframe_command(
                video=args.video,
                output=args.output,
                zoom=args.zoom,
                width=args.width,
                height=args.height,
                roi=args.roi,
                smoothing=args.smoothing,
                analysis_width=args.analysis_width,
                debug_overlay=args.debug_overlay,
            )
        return analyze_command(
            video=args.video,
            output_dir=args.output,
            report_dir=args.reports,
            top=max(1, args.top),
            threshold=args.threshold,
            sample_fps=args.sample_fps,
            export=not args.no_export,
        )
    except (
        DriveDownloadError,
        ReframeError,
        FileNotFoundError,
        ValueError,
        RuntimeError,
        MediaToolError,
    ) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    raise SystemExit(main())
