from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _robust_normalize(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low = float(np.percentile(values, 10))
    high = float(np.percentile(values, 95))
    if high <= low:
        return np.zeros_like(values, dtype=np.float64)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def analyze_motion_windows(
    video_path: Path,
    duration: float,
    sample_fps: float = 2.0,
    analysis_width: int = 320,
) -> list[float]:
    if sample_fps <= 0:
        raise ValueError("sample_fps must be greater than zero")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")

    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    if source_fps <= 0:
        capture.release()
        raise RuntimeError("Could not determine source FPS")

    frame_step = max(1, round(source_fps / sample_fps))
    second_count = max(1, int(np.ceil(duration)))
    per_second: list[list[float]] = [[] for _ in range(second_count)]
    previous_gray: np.ndarray | None = None
    frame_index = 0

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % frame_step != 0:
                frame_index += 1
                continue

            height, width = frame.shape[:2]
            target_height = max(1, round(height * (analysis_width / width)))
            resized = cv2.resize(frame, (analysis_width, target_height))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            timestamp = frame_index / source_fps
            second = min(int(timestamp), second_count - 1)
            if previous_gray is not None:
                difference = cv2.absdiff(previous_gray, gray)
                motion = float(np.mean(difference) / 255.0)
                per_second[second].append(motion)
            previous_gray = gray
            frame_index += 1
    finally:
        capture.release()

    raw = np.asarray(
        [float(np.mean(values)) if values else 0.0 for values in per_second],
        dtype=np.float64,
    )
    normalized = _robust_normalize(raw)
    return [float(value) for value in normalized]
