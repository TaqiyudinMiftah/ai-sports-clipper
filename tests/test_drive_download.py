from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from sports_clipper.drive_download import (
    DriveDownloadError,
    DriveSourceFile,
    download_drive_folder,
    filter_video_sources,
    list_drive_folder,
)


def completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_list_drive_folder_parses_gdown_json() -> None:
    payload = [
        {"url": "https://drive.google.com/file/d/one/view", "path": "one.mov"},
        {"url": "https://drive.google.com/file/d/two/view", "path": "notes.txt"},
    ]
    files = list_drive_folder(
        "https://drive.google.com/drive/folders/folder-id",
        runner=lambda command: completed(json.dumps(payload)),
    )
    assert files == [
        DriveSourceFile("https://drive.google.com/file/d/one/view", "one.mov"),
        DriveSourceFile("https://drive.google.com/file/d/two/view", "notes.txt"),
    ]


def test_filter_video_sources_is_case_insensitive() -> None:
    sources = [
        DriveSourceFile("u1", "A.MOV"),
        DriveSourceFile("u2", "B.mp4"),
        DriveSourceFile("u3", "readme.txt"),
    ]
    assert [item.relative_path for item in filter_video_sources(sources)] == [
        "A.MOV",
        "B.mp4",
    ]


def test_download_folder_writes_manifest_and_skips_existing(tmp_path: Path) -> None:
    payload = [
        {"url": "https://drive.google.com/file/d/one/view", "path": "match.mov"},
    ]
    destination = tmp_path / "match.mov"
    destination.write_bytes(b"video")
    calls: list[list[str]] = []

    def runner(command):
        calls.append(list(command))
        return completed(json.dumps(payload))

    manifest = download_drive_folder(
        "https://drive.google.com/drive/folders/folder-id",
        tmp_path,
        runner=runner,
    )
    assert len(calls) == 1
    assert manifest["file_count"] == 1
    assert manifest["files"][0]["status"] == "skipped_existing"
    assert manifest["files"][0]["sha256"]
    assert (tmp_path / "source_manifest.json").is_file()


def test_download_folder_rejects_path_traversal(tmp_path: Path) -> None:
    payload = [
        {"url": "https://drive.google.com/file/d/one/view", "path": "../match.mov"},
    ]
    with pytest.raises(DriveDownloadError, match="Unsafe Drive path"):
        download_drive_folder(
            "https://drive.google.com/drive/folders/folder-id",
            tmp_path,
            list_only=True,
            runner=lambda command: completed(json.dumps(payload)),
        )
