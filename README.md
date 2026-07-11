# AI Sports Clipper

A Python MVP that downloads approved source footage, analyzes long-form sports video, finds high-activity moments using audio and visual motion, ranks candidate highlights, and optionally exports preview clips with FFmpeg.

This first version intentionally focuses on **source ingestion and candidate discovery**, not autonomous social-media publishing. A human should review every exported clip before editing or posting.

## Current capabilities

- List and download approved videos from a public Google Drive folder.
- Resume interrupted Google Drive downloads and skip completed files.
- Create a source manifest with file paths, sizes, URLs, and SHA-256 hashes.
- Inspect video metadata with `ffprobe`.
- Extract and analyze mono audio for energy and transient peaks.
- Sample video frames and estimate visual motion.
- Merge audio and motion into a per-second excitement timeline.
- Detect, pad, score, and rank candidate highlights.
- Export the top candidates as MP4 files.
- Save a JSON analysis report with timestamps, scores, and reasons.

## Requirements

- Python 3.10 or newer
- FFmpeg and FFprobe available on `PATH`
- The Google Drive source folder must be accessible to the downloader

Check the media tools:

```bash
ffmpeg -version
ffprobe -version
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Video files are ignored by Git and must not be committed.

## Download the PPL source footage

The default source is the approved Pro Padel League campaign folder.
List the matching videos before downloading:

```bash
sports-clipper download-drive --list-only
```

Download the videos into `data/input/ppl/`:

```bash
sports-clipper download-drive
```

The campaign folder currently contains approximately 1.63 GiB of video, so make sure enough disk space is available. Existing completed files are skipped and interrupted downloads use gdown's continue mode.

Use a different public Drive folder or destination:

```bash
sports-clipper download-drive \
  "https://drive.google.com/drive/folders/FOLDER_ID" \
  --output data/input/another-campaign
```

Select extensions or force replacement:

```bash
sports-clipper download-drive \
  --extensions .mp4 .mov \
  --overwrite
```

Every run writes:

```text
data/input/ppl/source_manifest.json
```

The manifest records the Drive folder URL, original file URL and path, local path, size, download status, and SHA-256 hash. Use `--no-hash` when faster manifest generation is more important than provenance verification.

If Google reports permission denied, verify that the folder and files are shared appropriately. Google may also temporarily throttle popular files; rerun the command to resume partial downloads.

## Inspect a video

```bash
sports-clipper inspect "data/input/ppl/match.mov"
```

## Analyze and export candidates

```bash
sports-clipper analyze "data/input/ppl/match.mov" --top 5
```

Generate timestamps and a report without rendering clips:

```bash
sports-clipper analyze "data/input/ppl/match.mov" --top 5 --no-export
```

Useful tuning options:

```bash
sports-clipper analyze "data/input/ppl/match.mov" \
  --threshold 0.68 \
  --sample-fps 2 \
  --top 10
```

Outputs are written to:

```text
data/output/   # exported MP4 candidates
data/reports/  # JSON analysis reports
```

## How the MVP scores moments

The detector normalizes audio and motion inside each video, then combines them with a default weight of 55% audio and 45% motion. High-scoring neighboring seconds are grouped into candidate ranges, padded to preserve rally context, and expanded to at least 10 seconds.

This is a heuristic baseline. It does not yet understand the ball, score, player identity, or exact rally boundaries.

## Development roadmap

1. Collect human ratings for exported candidates.
2. Detect broadcast replays and scoreboard changes.
3. Add player pose and court-region analysis.
4. Train a learned highlight-ranking model from reviewer feedback.
5. Add vertical reframing, subtitles, watermarking, and campaign compliance.
6. Add approval-based publishing integrations.

## Run tests

```bash
pytest -q
```
