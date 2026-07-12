from __future__ import annotations

import argparse
import json
from pathlib import Path

from .source_ingestion import SourceError
from .unified_pipeline import ClipRequest, process_clip_request
from .video_info import MediaToolError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipper",
        description=(
            "Turn a local video or authorized YouTube URL into vertical social clips."
        ),
    )
    parser.add_argument("source", help="Local video path or YouTube URL")
    parser.add_argument("--clips", type=int, default=3, help="Number of clips to create")
    parser.add_argument(
        "--duration",
        type=float,
        default=20.0,
        help="Target duration for each final clip",
    )
    parser.add_argument("--threshold", type=float, default=0.62)
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--slowmo-speed", type=float, default=0.4)
    parser.add_argument(
        "--no-reframe",
        action="store_true",
        help="Skip ball-follow vertical reframing",
    )
    parser.add_argument(
        "--confirm-rights",
        action="store_true",
        help=(
            "Confirm that you are authorized to download and edit a YouTube source"
        ),
    )
    parser.add_argument("--jobs-dir", type=Path, default=Path("data/jobs"))
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the final job result as JSON",
    )
    return parser


def _progress(state: str, message: str) -> None:
    print(f"[{state}] {message}", flush=True)


def main() -> int:
    args = build_parser().parse_args()
    request = ClipRequest(
        source=args.source,
        clip_count=args.clips,
        target_duration=args.duration,
        threshold=args.threshold,
        sample_fps=args.sample_fps,
        slowmo_speed=args.slowmo_speed,
        reframe=not args.no_reframe,
        confirm_rights=args.confirm_rights,
        jobs_root=args.jobs_dir,
    )
    try:
        result = process_clip_request(
            request,
            progress=None if args.json else _progress,
        )
    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        SourceError,
        MediaToolError,
    ) as error:
        raise SystemExit(f"Error: {error}") from error

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"\nJob {result.job_id} completed")
    for clip in result.clips:
        print(f"- {clip.final_path}")
    print(f"Manifest: {result.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
