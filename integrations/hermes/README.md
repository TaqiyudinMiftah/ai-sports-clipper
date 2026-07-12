# Hermes Agent + Telegram

This integration lets Hermes Agent receive a Telegram message, queue a sports clipping job through MCP, and return completed MP4 files to the same chat.

## 1. Install this repository

```bash
cd ~/ai-sports-clipper
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Verify the new commands:

```bash
clipper-worker --help
```

## 2. Install Hermes Agent

Follow the official Hermes installation instructions, then run:

```bash
hermes setup
hermes gateway setup
```

Select Telegram and provide the BotFather token plus your numeric Telegram user ID.

## 3. Register the MCP server

Add this block to `~/.hermes/config.yaml`, replacing the home path when needed:

```yaml
mcp_servers:
  sports_clipper:
    command: "/home/taqiyudinmiftah/ai-sports-clipper/.venv/bin/clipper-mcp"
    timeout: 330
    env:
      CLIPPER_PROJECT_ROOT: "/home/taqiyudinmiftah/ai-sports-clipper"
      CLIPPER_JOBS_ROOT: "/home/taqiyudinmiftah/ai-sports-clipper/data/jobs"
    tools:
      include:
        - submit_clip_job
        - get_clip_job
        - wait_for_clip_job
        - list_clip_outputs
        - cancel_clip_job
```

The longer timeout permits the bounded wait tool to keep a Telegram turn active while the worker renders clips.

## 4. Install the Hermes skill

```bash
mkdir -p ~/.hermes/skills/media/padel-clipper
cp integrations/hermes/padel-clipper/SKILL.md \
  ~/.hermes/skills/media/padel-clipper/SKILL.md
```

Restart Hermes after changing MCP or skill configuration.

## 5. Start the services

Terminal 1:

```bash
cd ~/ai-sports-clipper
source .venv/bin/activate
clipper-worker
```

Terminal 2:

```bash
hermes gateway
```

Hermes launches `clipper-mcp` automatically as a local stdio MCP server.

## 6. Telegram test

Send this to the configured Hermes Telegram bot:

```text
Create 3 clips, around 20 seconds each, with slow motion at the end.
This is official PPL footage and I confirm I have permission:
https://www.youtube.com/watch?v=VIDEO_ID
```

Hermes should call `submit_clip_job`, return a job ID, wait for the worker, and finally return `MEDIA:/absolute/path.mp4` tags. The Hermes gateway delivers those paths as Telegram attachments.

## Local source example

```text
Create 2 clips from this local match:
/home/taqiyudinmiftah/ai-sports-clipper/data/input/ppl/match.mov
```

## Operations

Run one queued job and exit:

```bash
clipper-worker --once
```

Inspect a job:

```bash
cat data/jobs/hermes-*/job.json
```

Stop a queued job by asking Hermes:

```text
Cancel job hermes-20260712T120000Z-ab12cd34
```

Running jobs use cooperative cancellation and stop at the next pipeline progress boundary.

## Security

- Allowlist only your Telegram numeric user ID during Hermes gateway setup.
- Keep the BotFather token in Hermes configuration; never commit it.
- The MCP server exposes only five clipping tools and no shell execution.
- YouTube jobs require explicit rights confirmation.
- Run Hermes and the clipper worker under a non-root user.
