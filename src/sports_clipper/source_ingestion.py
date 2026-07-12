from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .drive_download import sha256_file
from .video_info import get_video_info


class SourceError(RuntimeError):
    """Raised when a source cannot be resolved or acquired."""


class SourceAuthorizationError(SourceError):
    """Raised when a remote source has not been authorized for download."""


@dataclass(frozen=True)
class SourceMetadata:
    source_type: str
    source: str
    title: str | None = None
    video_id: str | None = None
    channel_id: str | None = None
    channel: str | None = None
    duration: float | None = None
    webpage_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def is_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    return host in {"youtube.com", "youtu.be", "music.youtube.com"}


class LocalVideoSource:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()

    def inspect(self) -> SourceMetadata:
        info = get_video_info(self.path)
        return SourceMetadata(
            source_type="local",
            source=str(self.path),
            title=self.path.stem,
            duration=info.duration,
        )

    def acquire(self, destination_dir: Path) -> tuple[Path, dict[str, object]]:
        if not self.path.is_file():
            raise FileNotFoundError(f"Video not found: {self.path}")
        destination_dir.mkdir(parents=True, exist_ok=True)
        metadata = self.inspect()
        record: dict[str, object] = {
            "metadata": metadata.to_dict(),
            "local_path": str(self.path),
            "size_bytes": self.path.stat().st_size,
            "sha256": sha256_file(self.path),
            "copied": False,
        }
        manifest_path = destination_dir / "source_manifest.json"
        manifest_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        record["manifest_path"] = str(manifest_path)
        return self.path, record


YoutubeDLFactory = Callable[[dict[str, object]], Any]


def _default_youtube_dl_factory(options: dict[str, object]) -> Any:
    try:
        import yt_dlp
    except ImportError as error:
        raise SourceError(
            "yt-dlp is not installed. Activate the virtual environment and run "
            "python -m pip install -e '.[dev]'"
        ) from error
    return yt_dlp.YoutubeDL(options)


def _clean_youtube_metadata(info: dict[str, Any]) -> SourceMetadata:
    return SourceMetadata(
        source_type="youtube",
        source=str(info.get("webpage_url") or info.get("original_url") or ""),
        title=str(info.get("title")) if info.get("title") else None,
        video_id=str(info.get("id")) if info.get("id") else None,
        channel_id=str(info.get("channel_id")) if info.get("channel_id") else None,
        channel=(
            str(info.get("channel") or info.get("uploader"))
            if info.get("channel") or info.get("uploader")
            else None
        ),
        duration=float(info["duration"]) if info.get("duration") is not None else None,
        webpage_url=str(info.get("webpage_url")) if info.get("webpage_url") else None,
    )


def _find_downloaded_video(destination_dir: Path) -> Path:
    ignored_suffixes = {".json", ".part", ".ytdl", ".jpg", ".jpeg", ".png", ".webp"}
    candidates = [
        path
        for path in destination_dir.glob("source.*")
        if path.is_file() and path.suffix.lower() not in ignored_suffixes
    ]
    if not candidates:
        raise SourceError(
            f"yt-dlp completed without creating a video in {destination_dir}"
        )
    return max(candidates, key=lambda path: path.stat().st_size)


class YoutubeVideoSource:
    def __init__(
        self,
        url: str,
        *,
        confirm_rights: bool = False,
        ydl_factory: YoutubeDLFactory = _default_youtube_dl_factory,
    ):
        if not is_youtube_url(url):
            raise ValueError("Expected a YouTube URL")
        self.url = url.strip()
        self.confirm_rights = confirm_rights
        self.ydl_factory = ydl_factory

    def inspect(self) -> SourceMetadata:
        options: dict[str, object] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with self.ydl_factory(options) as ydl:
            raw = ydl.extract_info(self.url, download=False)
            info = ydl.sanitize_info(raw) if hasattr(ydl, "sanitize_info") else raw
        if not isinstance(info, dict):
            raise SourceError("yt-dlp returned invalid metadata")
        return _clean_youtube_metadata(info)

    def acquire(self, destination_dir: Path) -> tuple[Path, dict[str, object]]:
        if not self.confirm_rights:
            raise SourceAuthorizationError(
                "YouTube download requires explicit permission confirmation. "
                "Rerun with --confirm-rights only when you are authorized to use the footage."
            )

        destination_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(destination_dir / "source.%(ext)s")
        options: dict[str, object] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "continuedl": True,
            "format": "bv*[height<=1080]+ba/b[height<=1080]/best",
            "merge_output_format": "mp4",
            "outtmpl": output_template,
            "writeinfojson": True,
        }
        with self.ydl_factory(options) as ydl:
            raw = ydl.extract_info(self.url, download=True)
            info = ydl.sanitize_info(raw) if hasattr(ydl, "sanitize_info") else raw
        if not isinstance(info, dict):
            raise SourceError("yt-dlp returned invalid metadata")

        video_path = _find_downloaded_video(destination_dir)
        metadata = _clean_youtube_metadata(info)
        record: dict[str, object] = {
            "metadata": metadata.to_dict(),
            "local_path": str(video_path),
            "size_bytes": video_path.stat().st_size,
            "sha256": sha256_file(video_path),
            "rights_confirmed": True,
        }
        manifest_path = destination_dir / "source_manifest.json"
        manifest_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        record["manifest_path"] = str(manifest_path)
        return video_path, record


def resolve_source(
    value: str,
    *,
    confirm_rights: bool = False,
    ydl_factory: YoutubeDLFactory = _default_youtube_dl_factory,
) -> LocalVideoSource | YoutubeVideoSource:
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return LocalVideoSource(candidate)
    if is_youtube_url(value):
        return YoutubeVideoSource(
            value,
            confirm_rights=confirm_rights,
            ydl_factory=ydl_factory,
        )
    if candidate.exists():
        raise SourceError(f"Expected a video file, received: {candidate}")
    raise SourceError(
        "Source must be an existing local video file or a valid YouTube URL"
    )
