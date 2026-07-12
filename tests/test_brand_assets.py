from pathlib import Path
import subprocess

from sports_clipper.brand_assets import (
    PPL_DEFAULT_LOGO_FILE_ID,
    download_ppl_logo,
)


def test_download_ppl_logo_uses_gdown_file_id_and_writes_manifest(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "logo.png"
    commands: list[list[str]] = []

    def runner(command):
        commands.append(list(command))
        destination.write_bytes(b"official-logo")
        return subprocess.CompletedProcess(command, 0, "", "")

    record = download_ppl_logo(destination, runner=runner)

    assert record["status"] == "downloaded"
    assert record["local_path"] == str(destination)
    assert record["source_file_id"] == PPL_DEFAULT_LOGO_FILE_ID
    assert len(record["sha256"]) == 64
    assert Path(record["manifest_path"]).is_file()

    command = commands[0]
    assert "gdown" in command
    assert PPL_DEFAULT_LOGO_FILE_ID in command
    assert "--fuzzy" not in command


def test_download_ppl_logo_skips_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "logo.png"
    destination.write_bytes(b"already-here")

    def runner(command):
        raise AssertionError("runner should not be called")

    record = download_ppl_logo(destination, runner=runner)
    assert record["status"] == "skipped_existing"
