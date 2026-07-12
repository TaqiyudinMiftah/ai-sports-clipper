from datetime import datetime, timezone

import pytest

from sports_clipper.unified_pipeline import ClipRequest, create_job_id


def test_clip_request_defaults_are_social_ready() -> None:
    request = ClipRequest(source="match.mp4")
    request.validate()
    assert request.clip_count == 3
    assert request.target_duration == 20.0
    assert request.reframe is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("clip_count", 0),
        ("target_duration", 9),
        ("threshold", 0),
        ("sample_fps", 0),
        ("slowmo_speed", 1.0),
    ],
)
def test_clip_request_rejects_invalid_settings(field: str, value: float) -> None:
    values = {"source": "match.mp4", field: value}
    with pytest.raises(ValueError):
        ClipRequest(**values).validate()


def test_create_job_id_is_timestamped_and_source_specific() -> None:
    now = datetime(2026, 7, 12, 10, 30, tzinfo=timezone.utc)
    first = create_job_id("source-a", now)
    second = create_job_id("source-b", now)
    assert first.startswith("20260712T103000Z-")
    assert first != second
