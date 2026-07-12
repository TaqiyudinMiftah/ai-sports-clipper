import pytest

from sports_clipper.hermes_mcp import _validate_submission


def test_youtube_requires_explicit_rights_confirmation() -> None:
    with pytest.raises(ValueError, match="confirm_rights=true"):
        _validate_submission(
            "https://www.youtube.com/watch?v=abc123",
            3,
            20.0,
            0.4,
            False,
        )


def test_authorized_youtube_submission_is_valid() -> None:
    _validate_submission(
        "https://youtu.be/abc123",
        3,
        20.0,
        0.4,
        True,
    )


def test_submission_limits_are_enforced() -> None:
    with pytest.raises(ValueError, match="clip_count"):
        _validate_submission("match.mp4", 11, 20.0, 0.4, False)

    with pytest.raises(ValueError, match="target_duration"):
        _validate_submission("match.mp4", 3, 8.0, 0.4, False)
