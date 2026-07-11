# AI Sports Clipper

A Python MVP that downloads approved source footage, analyzes long-form sports video, finds high-activity moments using audio and visual motion, ranks candidate highlights, optionally exports preview clips, and creates smooth vertical ball-follow crops with FFmpeg and OpenCV.

This first version intentionally focuses on **source ingestion, candidate discovery, and assisted editing**, not autonomous social-media publishing. A human should review every exported clip before editing or posting.

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
- Create a smooth 9:16 crop that follows the likely rally ball or action center.
- Save JSON reports with timestamps, scores, tracking statistics, and reasons.

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

## Create a ball-follow vertical crop

Run the reframer on an exported candidate or a source clip:

```bash
sports-clipper reframe \
  "data/output/candidate_01_score_067.mp4"
```

The default output is:

```text
data/output/candidate_01_score_067_ball_follow.mp4
```

The reframer creates a 1080x1920 video, preserves source audio, and writes a tracking report next to the video:

```text
data/output/candidate_01_score_067_ball_follow.reframe.json
```

Use a stronger or weaker zoom:

```bash
sports-clipper reframe \
  "data/output/candidate_01_score_067.mp4" \
  --zoom 1.55
```

Preview the tracking logic with an overlay:

```bash
sports-clipper reframe \
  "data/output/candidate_01_score_067.mp4" \
  --debug-overlay \
  --output data/output/debug_ball_follow.mp4
```

Tune the court region when the default detector includes scoreboards, spectators, or advertising. Values are normalized `left,top,right,bottom` coordinates:

```bash
sports-clipper reframe \
  "data/output/candidate_01_score_067.mp4" \
  --roi "0.02,0.16,0.98,0.72"
```

Useful reframing controls:

- `--zoom`: crop magnification; `1.0` shows the largest possible 9:16 area.
- `--smoothing`: camera response from 0 to 1; lower values are steadier.
- `--analysis-width`: detection resolution; lower values are faster.
- `--debug-overlay`: displays tracker state for tuning.
- `--width` and `--height`: output resolution; both must be even numbers.

The ball detector is heuristic. It looks for small moving fluorescent yellow/green regions, predicts briefly through occlusion, and falls back to the rally's visual-motion center. It can occasionally follow clothing, signage, or reflections, so every output must be reviewed before publishing. A trained ball-detection model will be needed for production-level accuracy across different courts and broadcasts.

## How the MVP scores moments

The highlight detector normalizes audio and motion inside each video, then combines them with a default weight of 55% audio and 45% motion. High-scoring neighboring seconds are grouped into candidate ranges, padded to preserve rally context, and expanded to at least 10 seconds.

This is a heuristic baseline. It does not yet understand the score, player identity, or exact rally boundaries.

## Development roadmap

1. Collect human ratings for exported candidates.
2. Detect broadcast replays and scoreboard changes.
3. Add player pose and court-region analysis.
4. Train a dedicated ball detector and learned highlight-ranking model.
5. Add subtitles, watermarking, and campaign compliance.
6. Add approval-based publishing integrations.

## Run tests

```bash
pytest -q
```
