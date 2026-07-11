from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Sequence

PPL_SOURCE_FOLDER_URL = (
    "https://drive.google.com/drive/folders/1YpCPlbqJ77WPkk-h9j2WZyG79qDpl2aY"
)
DEFAULT_VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".m4v")


class DriveDownloadError(RuntimeError):
    """Raised when a Google Drive source cannot be listed or downloaded."""


@dataclass(frozen=True)
class DriveSourceFile:
    source_url: str
    relative_path: str

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.relative_path).suffix.lower()

    def to_dict(self) -> dict[str, str]:
        return {
            "source_url": self.source_url,
            "relative_path": self.relative_path,
        }


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise DriveDownloadError(
            "gdown is not installed. Run: pip install -e '.'"
        ) from error
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or str(error)).strip()
        raise DriveDownloadError(f"gdown failed: {details}") from error


def _gdown_command(*arguments: str) -> list[str]:
    return [sys.executable, "-m", "gdown", *arguments]


def _normalize_extensions(extensions: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for extension in extensions:
        value = extension.strip().lower()
        if not value:
            continue
        normalized.add(value if value.startswith(".") else f".{value}")
    if not normalized:
        raise ValueError("At least one file extension is required")
    return normalized


def _safe_destination(root: Path, relative_path: str) -> Path:
    drive_path = PurePosixPath(relative_path)
    if drive_path.is_absolute() or ".." in drive_path.parts:
        raise DriveDownloadError(f"Unsafe Drive path: {relative_path!r}")

    destination = root.joinpath(*drive_path.parts)
    root_resolved = root.resolve()
    destination_resolved = destination.resolve()
    try:
        destination_resolved.relative_to(root_resolved)
    except ValueError as error:
        raise DriveDownloadError(f"Unsafe Drive path: {relative_path!r}") from error
    return destination


def list_drive_folder(
    folder_url: str,
    *,
    runner: CommandRunner = _default_runner,
) -> list[DriveSourceFile]:
    if "/drive/folders/" not in folder_url:
        raise ValueError("Expected a Google Drive folder URL")

    result = runner(
        _gdown_command(folder_url, "--folder", "--json", "--quiet")
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DriveDownloadError("gdown returned invalid folder JSON") from error

    if not isinstance(payload, list):
        raise DriveDownloadError("gdown folder JSON must be a list")

    files: list[DriveSourceFile] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        source_url = item.get("url")
        relative_path = item.get("path")
        if isinstance(source_url, str) and isinstance(relative_path, str):
            files.append(
                DriveSourceFile(
                    source_url=source_url,
                    relative_path=relative_path,
                )
            )
    return files


def filter_video_sources(
    files: Iterable[DriveSourceFile],
    extensions: Iterable[str] = DEFAULT_VIDEO_EXTENSIONS,
) -> list[DriveSourceFile]:
    allowed = _normalize_extensions(extensions)
    return sorted(
        (file for file in files if file.suffix in allowed),
        key=lambda file: file.relative_path.casefold(),
    )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download_drive_folder(
    folder_url: str,
    output_dir: Path,
    *,
    extensions: Iterable[str] = DEFAULT_VIDEO_EXTENSIONS,
    overwrite: bool = False,
    compute_hashes: bool = True,
    list_only: bool = False,
    runner: CommandRunner = _default_runner,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = filter_video_sources(
        list_drive_folder(folder_url, runner=runner),
        extensions,
    )
    if not sources:
        raise DriveDownloadError("No matching video files were found in the folder")

    records: list[dict[str, object]] = []
    for source in sources:
        destination = _safe_destination(output_dir, source.relative_path)
        status = "listed"

        if not list_only:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not overwrite:
                status = "skipped_existing"
            else:
                if overwrite and destination.exists():
                    destination.unlink()
                command = _gdown_command(
                    source.source_url,
                    "-O",
                    str(destination),
                    "--continue",
                    "--quiet",
                )
                runner(command)
                if not destination.is_file():
                    raise DriveDownloadError(
                        f"Download completed without creating {destination}"
                    )
                status = "downloaded"

        record: dict[str, object] = {
            **source.to_dict(),
            "local_path": str(destination),
            "status": status,
        }
        if destination.is_file():
            record["size_bytes"] = destination.stat().st_size
            if compute_hashes:
                record["sha256"] = sha256_file(destination)
        records.append(record)

    manifest = {
        "source_folder_url": folder_url,
        "output_dir": str(output_dir),
        "extensions": sorted(_normalize_extensions(extensions)),
        "list_only": list_only,
        "file_count": len(records),
        "files": records,
    }
    manifest_path = output_dir / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
