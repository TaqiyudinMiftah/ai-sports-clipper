from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from .drive_download import sha256_file

PPL_LOGO_FOLDER_URL = (
    "https://drive.google.com/drive/folders/1QODBNZy3eoWAEq-rALAMDF-7a9ky8HDu"
)
PPL_DEFAULT_LOGO_FILE_ID = "1-7fVkEfTIpjMbUu11e9ACGRZO7KWUPXF"
PPL_DEFAULT_LOGO_URL = (
    f"https://drive.google.com/file/d/{PPL_DEFAULT_LOGO_FILE_ID}/view"
)
PPL_DEFAULT_LOGO_FILENAME = "PPL_HORIZONTAL_LOCKUP_WHITE.png"
PPL_DEFAULT_LOGO_PATH = Path("data/assets/ppl") / PPL_DEFAULT_LOGO_FILENAME


class BrandAssetError(RuntimeError):
    """Raised when an official brand asset cannot be downloaded."""


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
        raise BrandAssetError(
            "gdown is not installed. Activate the virtual environment and run "
            "python -m pip install -e '.[dev]'"
        ) from error
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or str(error)).strip()
        raise BrandAssetError(f"Could not download the PPL logo: {details}") from error


def download_ppl_logo(
    destination: Path = PPL_DEFAULT_LOGO_PATH,
    *,
    overwrite: bool = False,
    runner: CommandRunner = _default_runner,
) -> dict[str, object]:
    """Download the approved white PPL logo and write an asset manifest."""
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)

    status = "skipped_existing"
    if overwrite or not destination.is_file():
        if overwrite and destination.exists():
            destination.unlink()
        runner(
            [
                sys.executable,
                "-m",
                "gdown",
                PPL_DEFAULT_LOGO_FILE_ID,
                "-O",
                str(destination),
                "--quiet",
            ]
        )
        if not destination.is_file():
            raise BrandAssetError(
                f"Download completed without creating the logo at {destination}"
            )
        status = "downloaded"

    record = {
        "source_folder_url": PPL_LOGO_FOLDER_URL,
        "source_file_url": PPL_DEFAULT_LOGO_URL,
        "source_file_id": PPL_DEFAULT_LOGO_FILE_ID,
        "filename": PPL_DEFAULT_LOGO_FILENAME,
        "local_path": str(destination),
        "status": status,
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
    }
    manifest_path = destination.parent / "assets_manifest.json"
    manifest_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    record["manifest_path"] = str(manifest_path)
    return record
