import cv2
import numpy as np
import pytest

from sports_clipper.ball_reframe import (
    _ball_candidates,
    bounded_center,
    crop_geometry,
    parse_normalized_roi,
)


def test_parse_normalized_roi() -> None:
    assert parse_normalized_roi("0.1,0.2,0.9,0.8") == (0.1, 0.2, 0.9, 0.8)


@pytest.mark.parametrize(
    "value",
    ["0,0,1", "0.5,0,0.4,1", "-0.1,0,1,1", "zero,0,1,1"],
)
def test_parse_normalized_roi_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_normalized_roi(value)


def test_crop_geometry_is_vertical_and_even() -> None:
    crop_width, crop_height = crop_geometry(1920, 1080, zoom=1.0)
    assert crop_width % 2 == 0
    assert crop_height % 2 == 0
    assert crop_width <= 1920
    assert crop_height <= 1080
    assert abs(crop_width / crop_height - 9 / 16) < 0.01


def test_crop_geometry_zoom_reduces_crop() -> None:
    normal = crop_geometry(1080, 1920, zoom=1.0)
    zoomed = crop_geometry(1080, 1920, zoom=1.5)
    assert zoomed[0] < normal[0]
    assert zoomed[1] < normal[1]


def test_bounded_center_keeps_crop_inside_frame() -> None:
    assert bounded_center((0, 0), 1000, 800, 400, 600) == (200, 300)
    assert bounded_center((1000, 800), 1000, 800, 400, 600) == (800, 500)


def test_ball_candidates_detect_moving_yellow_circle() -> None:
    previous = np.zeros((360, 640, 3), dtype=np.uint8)
    current = previous.copy()
    cv2.circle(current, (320, 180), 4, (0, 255, 255), -1)
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    difference = cv2.absdiff(current_gray, previous_gray)

    candidates = _ball_candidates(current, difference, (0, 0, 640, 360))

    assert candidates
    x, y, _ = max(candidates, key=lambda candidate: candidate[2])
    assert abs(x - 320) < 8
    assert abs(y - 180) < 8
