from __future__ import annotations

import subprocess
from pathlib import Path

from .video_info import MediaToolError, require_binary


def export_clip(
    source: Path,
    output: Path,
    start_time: float,
    end_time: float,
) -> Path:
    if start_time < 0 or end_time <= start_time:
        raise ValueError("Invalid clip time range")

    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_binary("ffmpeg"),
        "-y",
        "-v",
        "error",
        "-ss",
        f"{start_time:.3f}",
        "-i",
        str(source),
        "-t",
        f"{end_time - start_time:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaToolError(result.stderr.strip() or "Could not export clip")
    return output
