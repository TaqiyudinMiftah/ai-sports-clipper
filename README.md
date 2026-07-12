# AI Sports Clipper

A Python pipeline that turns long-form padel footage into vertical social clips. It can ingest a local video or an authorized YouTube link, detect likely highlights, create a ball-follow crop, add an ending slow-motion replay, apply the official PPL watermark, and preserve gameplay audio.

A human should review every result before posting.

## Requirements

- Python 3.10 or newer
- FFmpeg and FFprobe on `PATH`
- Enough disk space for source videos and rendered clips

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

Verify the command interfaces:

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
- `--json`: print a machine-readable result

## Hermes Agent and Telegram

Hermes should manage Telegram and natural-language conversation. This repository supplies a restricted MCP tool server and a persistent background worker.

```text
Telegram
   ↓
Hermes Gateway
   ↓
AI Sports Clipper MCP tools
   ↓
Persistent queue
   ↓
clipper-worker
   ↓
Final MP4 files
```

The MCP surface exposes only:

```text
submit_clip_job
get_clip_job
list_clip_outputs
cancel_clip_job
```

It does not expose arbitrary shell execution.

### 1. Install Hermes support

From the repository:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev,hermes]"
```

Or run the integration helper:

```bash
bash integrations/hermes/install.sh
```

The helper installs the MCP dependency and copies the skill to:

```text
~/.hermes/skills/media/padel-clipper/SKILL.md
```

### 2. Configure the MCP server

Merge this block into `~/.hermes/config.yaml`, using your actual absolute path:

```yaml
mcp_servers:
  sports_clipper:
    command: "/home/USER/ai-sports-clipper/.venv/bin/clipper-mcp"
    env:
      CLIPPER_PROJECT_ROOT: "/home/USER/ai-sports-clipper"
      CLIPPER_JOBS_ROOT: "/home/USER/ai-sports-clipper/data/jobs"
    tools:
      include:
        - submit_clip_job
        - get_clip_job
        - list_clip_outputs
        - cancel_clip_job
```

A template is available at `integrations/hermes/config.example.yaml`.

### 3. Start the background worker

```bash
clipper-worker
```

The worker watches `data/jobs/_queue/pending`, processes jobs one at a time, and moves queue tickets into `completed`, `failed`, or `cancelled`.

For a one-job test:

```bash
clipper-worker --once --json
```

A systemd template is available at:

```text
integrations/hermes/clipper-worker.service.example
```

### 4. Configure Telegram in Hermes

Install Hermes separately, then run:

```bash
hermes gateway setup
```

Choose Telegram and provide the BotFather token plus your allowed numeric Telegram user ID.

Start the messaging gateway:

```bash
hermes gateway
```

For a local always-on ThinkCentre, Hermes' default Telegram long-polling mode is appropriate.

### 5. Command Hermes from Telegram

Example:

```text
Create 3 clips from this official PPL match:
https://www.youtube.com/watch?v=VIDEO_ID

Make them around 20 seconds with slow motion at the end.
I confirm that I have permission to download and edit this footage.
```

Hermes calls `submit_clip_job` and returns a job ID immediately while `clipper-worker` performs the long video job.

Check later with:

```text
What is the status of job 20260712T120000Z-ab12cd34-a1b2c3?
```

When completed:

```text
Send me the clips for job 20260712T120000Z-ab12cd34-a1b2c3.
```

The Hermes skill calls `list_clip_outputs` and returns each absolute MP4 path as a `MEDIA:` attachment for Telegram.

## Persistent queue layout

```text
data/jobs/
├── _queue/
│   ├── pending/
│   ├── running/
│   ├── completed/
│   ├── failed/
│   └── cancelled/
└── <job-id>/
    ├── request.json
    ├── job.json
    ├── source/
    ├── candidates/
    ├── reframed/
    ├── final/
    │   ├── clip_01_social.mp4
    │   └── clip_02_social.mp4
    └── reports/
```

`job.json` records queued and pipeline state, request settings, progress messages, source provenance, candidate timestamps, scores, reasons, errors, and final output paths.

The queue is file-backed so jobs survive restarts without requiring Redis for the single-machine MVP.

## Python agent contracts

Synchronous processing remains available:

```python
from sports_clipper.agent_tools import create_clip_job

result = create_clip_job(
    {
        "source": "data/input/ppl/match.mov",
        "clip_count": 3,
    }
)
```

Non-blocking Hermes submission uses:

```python
from sports_clipper.job_queue import enqueue_clip_job

job = enqueue_clip_job(
    {
        "source": "https://www.youtube.com/watch?v=VIDEO_ID",
        "clip_count": 3,
        "target_duration": 20,
        "confirm_rights": True,
    }
)
```

## What the pipeline does

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

## Advanced commands

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
- The file-backed worker processes one job at a time on one machine.
- Running-job cancellation is cooperative and takes effect at the next pipeline checkpoint.
- Hermes does not proactively push a completion message in this milestone; ask for the job status and completed outputs.
- Clips are generated for review and are not automatically posted.

## Next implementation phases

1. Add automatic Hermes completion notifications to the originating Telegram conversation.
2. Add approval and regeneration controls.
3. Add natural-language edit controls such as “less zoom” and “longer rally.”
4. Add exact rally-boundary and final-shot detection.
5. Add multi-worker locking or Redis when processing moves beyond one machine.

## Run tests

```bash
pytest -q
```
