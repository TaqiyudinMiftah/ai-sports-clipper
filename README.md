# AI Sports Clipper

A Python MVP that downloads approved source footage, analyzes long-form sports video, finds high-activity moments using audio and visual motion, ranks candidate highlights, creates smooth vertical ball-follow crops, and composes social-ready edits with FFmpeg and OpenCV.

This version focuses on **source ingestion, candidate discovery, and assisted editing**, not autonomous social-media publishing. A human should review every exported clip before posting.

## Current capabilities

- List and download approved videos from a public Google Drive folder.
- Resume interrupted Google Drive downloads and skip completed files.
- Create source manifests with file paths, sizes, URLs, and SHA-256 hashes.
- Download the approved white Pro Padel League logo from the official Drive folder.
- Inspect video metadata with `ffprobe`.
- Extract and analyze mono audio for energy and transient peaks.
- Sample video frames and estimate visual motion.
- Merge audio and motion into a per-second excitement timeline.
- Detect, pad, score, and rank candidate highlights.
- Export the top candidates as MP4 files.
- Create a smooth 9:16 crop that follows the likely rally ball or action center.
- Compose an approximately 20-second vertical edit with an ending slow-motion replay.
- Apply the required PPL watermark while preserving gameplay audio.
- Save JSON reports with timestamps, scores, tracking statistics, edit plans, and asset hashes.

## Requirements

- Python 3.10 or newer
- FFmpeg and FFprobe available on `PATH`
- The Google Drive source and logo folders must be accessible to the downloader

Check the media tools:

```bash
ffmpeg -version
ffprobe -version
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Video files and downloaded assets are ignored by Git and must not be committed.

## Download the PPL source footage

The default source is the approved Pro Padel League campaign folder. List the matching videos before downloading:

```bash
sports-clipper download-drive --list-only
```

Download the videos into `data/input/ppl/`:

```bash
sports-clipper download-drive
```

The campaign folder contains approximately 1.63 GiB of video, so make sure enough disk space is available. Existing completed files are skipped and interrupted downloads use gdown's continue mode.

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

Run the reframer on an exported candidate or source clip:

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

The ball detector is heuristic. It looks for small moving fluorescent yellow/green regions, predicts briefly through occlusion, and falls back to the rally's visual-motion center. It can occasionally follow clothing, signage, or reflections, so every output must be reviewed before publishing.

## Download the official PPL logo

The default asset is `PPL_HORIZONTAL_LOCKUP_WHITE.png` from the official campaign logo folder.

```bash
sports-clipper download-logo
```

The files are written to:

```text
data/assets/ppl/PPL_HORIZONTAL_LOCKUP_WHITE.png
data/assets/ppl/assets_manifest.json
```

The manifest stores the official folder URL, selected file URL, local path, size, and SHA-256 hash. Redownload the asset with:

```bash
sports-clipper download-logo --overwrite
```

## Compose a 20-second social edit

Run this after reframing so the composer receives a vertical input:

```bash
sports-clipper compose-social \
  "data/output/candidate_01_score_067_ball_follow.mp4"
```

The default result is:

```text
data/output/candidate_01_score_067_ball_follow_social.mp4
```

The default edit:

1. Preserves the strongest ending portion of the input.
2. Plays the normal clip first.
3. Replays the final moment at `0.4x` speed.
4. Targets a total duration of 20 seconds.
5. Applies the approved white PPL logo near the bottom safe zone.
6. Preserves and time-stretches original gameplay audio.
7. Writes a `.compose.json` report beside the output.

Tune the replay speed or explicitly choose how many source seconds are replayed:

```bash
sports-clipper compose-social \
  "data/output/candidate_01_score_067_ball_follow.mp4" \
  --slowmo-speed 0.5 \
  --replay-source-seconds 2.5
```

Adjust the watermark:

```bash
sports-clipper compose-social \
  "data/output/candidate_01_score_067_ball_follow.mp4" \
  --logo-width 260 \
  --logo-bottom-margin 190 \
  --logo-opacity 0.9
```

Use another approved logo variant with `--logo /path/to/logo.png`.

### Recommended workflow

```bash
sports-clipper analyze "data/input/ppl/match.mov" --top 5
sports-clipper reframe "data/output/candidate_01_score_067.mp4"
sports-clipper download-logo
sports-clipper compose-social \
  "data/output/candidate_01_score_067_ball_follow.mp4"
```

The automatic composer assumes the strongest replay-worthy action is near the end of the input. Review the output and its report before posting. Exact rally-boundary detection and learned final-shot selection are later milestones.

## How the MVP scores moments

The highlight detector normalizes audio and motion inside each video, then combines them with a default weight of 55% audio and 45% motion. High-scoring neighboring seconds are grouped into candidate ranges, padded to preserve rally context, and expanded to at least 10 seconds.

This is a heuristic baseline. It does not yet understand the score, player identity, or exact rally boundaries.

## Development roadmap

1. Detect exact rally start and point-ending boundaries.
2. Select the final winner or impossible save using audio, ball velocity, and motion peaks.
3. Add context-aware hook text and safe-zone validation.
4. Train a dedicated ball detector and learned highlight-ranking model.
5. Add campaign compliance checks and human approval workflow.
6. Add approval-based publishing integrations.

## Run tests

```bash
pytest -q
```
