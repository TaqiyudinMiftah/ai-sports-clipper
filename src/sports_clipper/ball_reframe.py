from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class ReframeError(RuntimeError):
    """Raised when a video cannot be reframed."""


@dataclass
class TrackState:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    confidence: float = 0.0
    missing_frames: int = 0


@dataclass
class ReframeStats:
    total_frames: int = 0
    detected_frames: int = 0
    predicted_frames: int = 0
    fallback_frames: int = 0

    def to_dict(self) -> dict[str, float | int]:
        detection_rate = (
            self.detected_frames / self.total_frames if self.total_frames else 0.0
        )
        return {
            "total_frames": self.total_frames,
            "detected_frames": self.detected_frames,
            "predicted_frames": self.predicted_frames,
            "fallback_frames": self.fallback_frames,
            "ball_detection_rate": round(detection_rate, 4),
        }


def parse_normalized_roi(value: str) -> tuple[float, float, float, float]:
    """Parse left,top,right,bottom coordinates in the zero-to-one range."""
    try:
        parts = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as error:
        raise ValueError(
            "ROI must be four comma-separated numbers: left,top,right,bottom"
        ) from error
    if len(parts) != 4:
        raise ValueError("ROI must contain exactly four values")
    left, top, right, bottom = parts
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError(
            "ROI must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1"
        )
    return parts


def crop_geometry(width: int, height: int, zoom: float) -> tuple[int, int]:
    """Return an even 9:16 crop that fits inside the source frame."""
    if width <= 0 or height <= 0:
        raise ValueError("Source dimensions must be positive")
    if zoom < 1.0:
        raise ValueError("zoom must be at least 1.0")

    target_aspect = 9.0 / 16.0
    maximum_height = min(float(height), float(width) / target_aspect)
    crop_height = max(64, int(round(maximum_height / zoom)))
    crop_width = max(36, int(round(crop_height * target_aspect)))
    crop_width = min(width, crop_width) - min(width, crop_width) % 2
    crop_height = min(height, crop_height) - min(height, crop_height) % 2
    return crop_width, crop_height


def bounded_center(
    center: tuple[float, float],
    width: int,
    height: int,
    crop_width: int,
    crop_height: int,
) -> tuple[float, float]:
    half_width = crop_width / 2.0
    half_height = crop_height / 2.0
    return (
        min(max(center[0], half_width), width - half_width),
        min(max(center[1], half_height), height - half_height),
    )


def _roi_pixels(
    frame: np.ndarray,
    roi: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    height, width = frame.shape[:2]
    left, top, right, bottom = roi
    return (
        int(round(left * width)),
        int(round(top * height)),
        int(round(right * width)),
        int(round(bottom * height)),
    )


def _motion_center(
    difference: np.ndarray,
    roi: tuple[int, int, int, int],
) -> tuple[float, float] | None:
    left, top, right, bottom = roi
    region = difference[top:bottom, left:right]
    if region.size == 0 or not np.any(region):
        return None

    threshold = max(14.0, float(np.percentile(region, 94)))
    weighted = np.where(region >= threshold, region, 0).astype(np.uint8)
    moments = cv2.moments(weighted)
    if moments["m00"] <= 0:
        return None
    return (
        left + moments["m10"] / moments["m00"],
        top + moments["m01"] / moments["m00"],
    )


def _ball_candidates(
    frame: np.ndarray,
    difference: np.ndarray,
    roi: tuple[int, int, int, int],
) -> list[tuple[float, float, float]]:
    """Find small moving fluorescent-yellow/green regions."""
    left, top, right, bottom = roi
    region = frame[top:bottom, left:right]
    motion = difference[top:bottom, left:right]
    if region.size == 0:
        return []

    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    color_mask = cv2.inRange(
        hsv,
        np.array([18, 55, 110], dtype=np.uint8),
        np.array([65, 255, 255], dtype=np.uint8),
    )
    motion_threshold = max(9.0, float(np.percentile(motion, 84)))
    motion_mask = np.where(motion >= motion_threshold, 255, 0).astype(np.uint8)
    motion_mask = cv2.dilate(motion_mask, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.bitwise_and(color_mask, motion_mask)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    component_count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
    frame_scale = math.sqrt((frame.shape[0] * frame.shape[1]) / (540 * 960))
    maximum_area = max(75, int(100 * frame_scale * frame_scale))
    maximum_side = max(16, int(22 * frame_scale))
    candidates: list[tuple[float, float, float]] = []

    for component in range(1, component_count):
        x, y, width, height, area = stats[component]
        if not 2 <= area <= maximum_area:
            continue
        if width > maximum_side or height > maximum_side:
            continue
        aspect = min(width, height) / max(width, height)
        if aspect < 0.28:
            continue

        center_x, center_y = centers[component]
        pixel_x = min(max(int(round(center_x)), 0), hsv.shape[1] - 1)
        pixel_y = min(max(int(round(center_y)), 0), hsv.shape[0] - 1)
        saturation = float(hsv[pixel_y, pixel_x, 1]) / 255.0
        brightness = float(hsv[pixel_y, pixel_x, 2]) / 255.0
        compactness = min(1.0, area / max(1.0, width * height))
        appearance = 0.38 * saturation + 0.32 * brightness + 0.30 * compactness
        candidates.append((left + float(center_x), top + float(center_y), appearance))

    return candidates


def _select_candidate(
    candidates: list[tuple[float, float, float]],
    track: TrackState | None,
    diagonal: float,
) -> tuple[float, float, float] | None:
    if not candidates:
        return None
    if track is None or track.confidence < 0.1:
        return max(candidates, key=lambda candidate: candidate[2])

    predicted_x = track.x + track.vx
    predicted_y = track.y + track.vy

    def candidate_score(candidate: tuple[float, float, float]) -> float:
        x, y, appearance = candidate
        distance = math.hypot(x - predicted_x, y - predicted_y) / max(diagonal, 1.0)
        continuity = math.exp(-distance * 14.0)
        return 0.58 * appearance + 0.42 * continuity

    return max(candidates, key=candidate_score)


def _update_track(
    track: TrackState | None,
    detection: tuple[float, float, float] | None,
    fallback: tuple[float, float],
    maximum_missing: int,
) -> tuple[TrackState, str]:
    if detection is not None:
        x, y, score = detection
        if track is None:
            return TrackState(x=x, y=y, confidence=score), "detected"
        track.vx = 0.65 * track.vx + 0.35 * (x - track.x)
        track.vy = 0.65 * track.vy + 0.35 * (y - track.y)
        track.x = 0.28 * track.x + 0.72 * x
        track.y = 0.28 * track.y + 0.72 * y
        track.confidence = min(1.0, 0.55 * track.confidence + 0.45 * score + 0.1)
        track.missing_frames = 0
        return track, "detected"

    if track is not None and track.missing_frames < maximum_missing:
        track.x += track.vx
        track.y += track.vy
        track.vx *= 0.92
        track.vy *= 0.92
        track.confidence *= 0.92
        track.missing_frames += 1
        return track, "predicted"

    fallback_x, fallback_y = fallback
    if track is None:
        track = TrackState(fallback_x, fallback_y, missing_frames=maximum_missing)
    else:
        track.x = 0.92 * track.x + 0.08 * fallback_x
        track.y = 0.92 * track.y + 0.08 * fallback_y
        track.vx *= 0.75
        track.vy *= 0.75
        track.confidence *= 0.8
        track.missing_frames = maximum_missing
    return track, "fallback"


def reframe_video(
    source: Path,
    destination: Path,
    *,
    zoom: float = 1.4,
    output_width: int = 1080,
    output_height: int = 1920,
    roi: tuple[float, float, float, float] = (0.02, 0.14, 0.98, 0.76),
    smoothing: float = 0.16,
    maximum_pan_ratio: float = 0.035,
    missing_seconds: float = 0.65,
    analysis_width: int = 540,
    debug_overlay: bool = False,
) -> dict[str, object]:
    """Create a smooth 9:16 crop that follows the likely ball or rally action."""
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Video not found: {source}")
    if output_width <= 0 or output_height <= 0 or output_width % 2 or output_height % 2:
        raise ValueError("Output dimensions must be positive even numbers")
    if not 0 < smoothing <= 1:
        raise ValueError("smoothing must be between 0 and 1")
    if maximum_pan_ratio <= 0 or analysis_width < 160:
        raise ValueError("Pan ratio must be positive and analysis width at least 160")

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ReframeError(f"Could not open video: {source}")

    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    crop_width, crop_height = crop_geometry(width, height, zoom)
    scale = min(1.0, analysis_width / max(width, 1))
    small_width = max(2, int(round(width * scale)))
    small_height = max(2, int(round(height * scale)))
    maximum_missing = max(1, int(round(missing_seconds * fps)))
    maximum_pan = max(width, height) * maximum_pan_ratio

    destination.parent.mkdir(parents=True, exist_ok=True)
    statistics = ReframeStats()
    track: TrackState | None = None
    camera_center = (width / 2.0, height / 2.0)
    previous_gray: np.ndarray | None = None

    with tempfile.TemporaryDirectory(prefix="sports-reframe-") as temporary_directory:
        silent_path = Path(temporary_directory) / "silent.mp4"
        writer = cv2.VideoWriter(
            str(silent_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (output_width, output_height),
        )
        if not writer.isOpened():
            capture.release()
            raise ReframeError("Could not initialize the temporary video writer")

        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break
                statistics.total_frames += 1
                small = cv2.resize(frame, (small_width, small_height), cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)
                difference = (
                    np.zeros_like(gray)
                    if previous_gray is None
                    else cv2.absdiff(gray, previous_gray)
                )
                previous_gray = gray

                analysis_roi = _roi_pixels(small, roi)
                action_center = _motion_center(difference, analysis_roi)
                fallback = action_center or (
                    (analysis_roi[0] + analysis_roi[2]) / 2.0,
                    (analysis_roi[1] + analysis_roi[3]) / 2.0,
                )
                candidates = _ball_candidates(small, difference, analysis_roi)
                detection = _select_candidate(
                    candidates, track, math.hypot(small_width, small_height)
                )
                track, mode = _update_track(
                    track, detection, fallback, maximum_missing
                )
                if mode == "detected":
                    statistics.detected_frames += 1
                elif mode == "predicted":
                    statistics.predicted_frames += 1
                else:
                    statistics.fallback_frames += 1

                desired = bounded_center(
                    (track.x / scale, track.y / scale),
                    width,
                    height,
                    crop_width,
                    crop_height,
                )
                delta_x = desired[0] - camera_center[0]
                delta_y = desired[1] - camera_center[1]
                distance = math.hypot(delta_x, delta_y)
                if distance > maximum_pan:
                    ratio = maximum_pan / distance
                    delta_x *= ratio
                    delta_y *= ratio
                camera_center = bounded_center(
                    (
                        camera_center[0] + smoothing * delta_x,
                        camera_center[1] + smoothing * delta_y,
                    ),
                    width,
                    height,
                    crop_width,
                    crop_height,
                )

                left = int(round(camera_center[0] - crop_width / 2.0))
                top = int(round(camera_center[1] - crop_height / 2.0))
                left = min(max(left, 0), width - crop_width)
                top = min(max(top, 0), height - crop_height)
                cropped = frame[top : top + crop_height, left : left + crop_width]
                output = cv2.resize(
                    cropped, (output_width, output_height), cv2.INTER_LINEAR
                )
                if debug_overlay:
                    cv2.circle(
                        output,
                        (output_width // 2, output_height // 2),
                        16,
                        (0, 0, 255),
                        3,
                    )
                    cv2.putText(
                        output,
                        f"mode={mode} candidates={len(candidates)}",
                        (24, 48),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                writer.write(output)
        finally:
            capture.release()
            writer.release()

        if statistics.total_frames == 0:
            raise ReframeError("The video contained no readable frames")

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise ReframeError("Required executable 'ffmpeg' was not found")
        command = [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(silent_path),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ReframeError(
                result.stderr.strip() or "FFmpeg could not mux the reframed video"
            )

    report: dict[str, object] = {
        "source": str(source),
        "output": str(destination),
        "input_dimensions": [width, height],
        "output_dimensions": [output_width, output_height],
        "crop_dimensions": [crop_width, crop_height],
        "fps": fps,
        "estimated_frame_count": frame_count,
        "zoom": zoom,
        "roi": list(roi),
        "stats": statistics.to_dict(),
        "warning": (
            "Ball detection is heuristic and may follow other yellow moving objects. "
            "Review every output before publishing."
        ),
    }
    report_path = destination.with_suffix(".reframe.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
