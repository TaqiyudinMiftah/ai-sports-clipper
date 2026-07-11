from sports_clipper.video_info import _parse_fps


def test_parse_fractional_fps() -> None:
    assert round(_parse_fps("30000/1001"), 3) == 29.97


def test_parse_unknown_fps() -> None:
    assert _parse_fps("0/0") == 0.0
