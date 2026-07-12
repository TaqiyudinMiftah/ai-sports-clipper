from pathlib import Path

import pytest

from sports_clipper.source_ingestion import (
    LocalVideoSource,
    SourceAuthorizationError,
    YoutubeVideoSource,
    _find_downloaded_video,
    is_youtube_url,
    resolve_source,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://m.youtube.com/live/abc123",
        "https://music.youtube.com/watch?v=abc123",
    ],
)
def test_is_youtube_url(url: str) -> None:
    assert is_youtube_url(url)


def test_is_youtube_url_rejects_other_hosts() -> None:
    assert not is_youtube_url("https://example.com/watch?v=abc123")


def test_resolve_source_detects_local_file(tmp_path: Path) -> None:
    video = tmp_path / "match.mp4"
    video.write_bytes(b"video")
    source = resolve_source(str(video))
    assert isinstance(source, LocalVideoSource)


def test_youtube_download_requires_rights_confirmation(tmp_path: Path) -> None:
    source = YoutubeVideoSource("https://youtu.be/abc123")
    with pytest.raises(SourceAuthorizationError):
        source.acquire(tmp_path)


def test_find_downloaded_video_ignores_metadata(tmp_path: Path) -> None:
    (tmp_path / "source.info.json").write_text("{}", encoding="utf-8")
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video bytes")
    assert _find_downloaded_video(tmp_path) == video


class FakeYoutubeDL:
    def __init__(self, options: dict[str, object]):
        self.options = options

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def extract_info(self, url: str, download: bool) -> dict[str, object]:
        return {
            "id": "abc123",
            "title": "PPL Match",
            "channel_id": "channel-1",
            "channel": "Pro Padel League",
            "duration": 120.0,
            "webpage_url": url,
        }

    def sanitize_info(self, info: dict[str, object]) -> dict[str, object]:
        return info


def test_youtube_inspect_returns_structured_metadata() -> None:
    source = YoutubeVideoSource(
        "https://youtu.be/abc123",
        ydl_factory=FakeYoutubeDL,
    )
    metadata = source.inspect()
    assert metadata.video_id == "abc123"
    assert metadata.channel == "Pro Padel League"
    assert metadata.duration == 120.0
