# AI Sports Clipper

A Python pipeline that turns long-form padel footage into vertical social clips. It can ingest a local video or an authorized YouTube link, detect likely highlights, create a ball-follow crop, add an ending slow-motion replay, apply the official PPL watermark, and preserve gameplay audio.

A human should review every result before posting.

## Requirements

- Python 3.10 or newer
- FFmpeg and FFprobe on `PATH`
- Enough disk space for the source video and rendered clips

```bash
ffmpeg -version
ffprobe -version
```

## Setup

```bash
git clone https://github.com/TaqiyudinMiftah/ai-sports-clipper.git
cd ai-sports-clipper

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Verify both command interfaces:

```bash
clipper --help
sports-clipper --help
```

## One-command workflow

### Local video

```bash
clipper "data/input/ppl/match.mov"
```

### Authorized YouTube video

```bash
clipper "https://www.youtube.com/watch?v=VIDEO_ID" --confirm-rights
```

`--confirm-rights` is required for YouTube ingestion. Use it only when you are authorized to download and edit the footage. The pipeline stores the source URL, YouTube metadata, local file path, size, and SHA-256 hash in the job manifest.

### Common options

```bash
clipper "SOURCE" \
  --clips 3 \
  --duration 20 \
  --slowmo-speed 0.4 \
  --threshold 0.62
```

- `--clips`: number of final clips, from 1 to 20
- `--duration`: target final duration; minimum 10 seconds
- `--slowmo-speed`: replay speed from 0.25 to below 1.0
- `--threshold`: highlight sensitivity; lower values return more candidates
- `--sample-fps`: visual-analysis sampling rate
- `--no-reframe`: skip ball-follow vertical reframing
- `--jobs-dir`: change the job workspace root
- `--json`: print a machine-readable result for agent integrations

## What the command does

```text
Resolve local or YouTube source
        ↓
Acquire and fingerprint the source
        ↓
Download the official PPL logo when missing
        ↓
Analyze audio and visual motion
        ↓
Rank highlight candidates
        ↓
Export each candidate
        ↓
Create a smooth 9:16 ball-follow crop
        ↓
Add an ending slow-motion replay
        ↓
Apply the PPL watermark and preserve audio
        ↓
Write final MP4 files and a durable job manifest
```

## Job output

Every request creates a workspace under:

```text
data/jobs/<job-id>/
├── source/
│   └── source_manifest.json
├── candidates/
├── reframed/
├── final/
│   ├── clip_01_social.mp4
│   └── clip_02_social.mp4
└── job.json
```

`job.json` records the current state, request settings, source provenance, candidate timestamps, scores, reasons, and final output paths. This file is the durable interface used by future Telegram and WhatsApp workers.

## Agent tool contract

The repository now exposes a stable Python function for chat agents:

```python
from sports_clipper.agent_tools import create_clip_job

result = create_clip_job(
    {
        "source": "https://www.youtube.com/watch?v=VIDEO_ID",
        "clip_count": 3,
        "target_duration": 20,
        "slowmo_speed": 0.4,
        "confirm_rights": True,
    }
)
```

Read a job later with:

```python
from sports_clipper.agent_tools import get_clip_job

job = get_clip_job("20260712T103000Z-ab12cd34")
```

Telegram and WhatsApp adapters should call these functions instead of executing arbitrary shell commands.

## Advanced commands

The original commands remain available for debugging and manual control.

### Download approved Drive footage

```bash
sports-clipper download-drive --list-only
sports-clipper download-drive
```

### Analyze a source

```bash
sports-clipper analyze "data/input/ppl/match.mov" --top 5
```

### Create a ball-follow crop

```bash
sports-clipper reframe "data/output/candidate_01_score_067.mp4"
```

### Download the official logo

```bash
sports-clipper download-logo
```

### Compose a social edit

```bash
sports-clipper compose-social \
  "data/output/candidate_01_score_067_ball_follow.mp4"
```

## Current limitations

- YouTube ingestion requires explicit rights confirmation; an official PPL channel allowlist is not configured yet.
- The highlight detector uses audio and motion heuristics rather than exact rally boundaries.
- The ball follower is a lightweight color-and-motion tracker and can lose the ball.
- The replay composer assumes the strongest action is near the end of each candidate.
- Processing is synchronous. A Redis-backed worker queue is the next step before Telegram or WhatsApp deployment.
- Clips are generated for review and are not automatically posted.

## Next implementation phases

1. Add persistent queued jobs and retry support.
2. Add a Telegram bot with URL intake, progress messages, previews, and approval buttons.
3. Add natural-language edit controls such as “less zoom” and “longer rally.”
4. Add a WhatsApp Cloud API adapter using the same agent tool contract.
5. Add exact rally-boundary and final-shot detection.

## Run tests

```bash
pytest -q
```
