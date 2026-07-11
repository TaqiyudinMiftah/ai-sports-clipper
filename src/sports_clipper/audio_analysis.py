from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from .video_info import MediaToolError, require_binary


def extract_mono_audio(video_path: Path, output_wav: Path, sample_rate: int = 16_000) -> Path:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_binary("ffmpeg"),
        "-y",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaToolError(result.stderr.strip() or "Could not extract audio")
    return output_wav


def _robust_normalize(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low = float(np.percentile(values, 10))
    high = float(np.percentile(values, 95))
    if high <= low:
        return np.zeros_like(values, dtype=np.float64)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def analyze_audio_windows(wav_path: Path, window_seconds: float = 1.0) -> list[float]:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be greater than zero")

    with wave.open(str(wav_path), "rb") as audio_file:
        channels = audio_file.getnchannels()
        sample_width = audio_file.getsampwidth()
        sample_rate = audio_file.getframerate()
        frames = audio_file.readframes(audio_file.getnframes())

    if channels != 1 or sample_width != 2:
        raise ValueError("Expected 16-bit mono PCM audio")

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    window_size = max(1, int(sample_rate * window_seconds))
    rms_values: list[float] = []
    transient_values: list[float] = []

    for start in range(0, samples.size, window_size):
        window = samples[start : start + window_size]
        if window.size == 0:
            continue
        rms_values.append(float(np.sqrt(np.mean(np.square(window)))))
        if window.size > 1:
            transient_values.append(float(np.percentile(np.abs(np.diff(window)), 99)))
        else:
            transient_values.append(0.0)

    rms = _robust_normalize(np.asarray(rms_values, dtype=np.float64))
    transients = _robust_normalize(np.asarray(transient_values, dtype=np.float64))
    combined = (0.7 * rms) + (0.3 * transients)
    return [float(value) for value in combined]
