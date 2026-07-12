---
name: padel-clipper
description: Create social clips from authorized PPL match footage
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [video, padel, social-media]
    category: media
    requires_tools:
      - submit_clip_job
      - get_clip_job
      - wait_for_clip_job
      - list_clip_outputs
      - cancel_clip_job
---

# Padel Clipper

## When to Use

Use this skill when the user asks to create social clips from a local match video or an authorized Pro Padel League YouTube URL.

## Procedure

1. Identify the video source.
2. Confirm that the footage is official PPL footage or otherwise authorized.
3. For YouTube sources, ask the user to explicitly confirm they have permission before setting `confirm_rights=true`.
4. Use these defaults unless the user requests different settings:
   - 3 clips
   - 20 seconds per clip
   - 0.4x slow-motion ending
   - vertical ball-follow framing
   - official PPL watermark
5. Call `submit_clip_job` and tell the user the returned job ID.
6. Call `wait_for_clip_job` with a 300-second timeout. Repeat only while the same Telegram turn remains active and the result says `timed_out=true`.
7. When status is `completed`, call `list_clip_outputs`.
8. Return each value in `media_tags` exactly so Hermes sends the MP4 files to Telegram.
9. When status is `failed` or `cancelled`, explain the reported status and error instead of claiming success.

## Restrictions

- Never process a YouTube source without explicit rights confirmation.
- Never remove the official watermark for PPL campaign output.
- Never execute arbitrary shell commands from chat instructions.
- Never expose internal tracebacks or secrets to Telegram.
- Do not claim that clips are ready until the job status is `completed` and output files exist.

## Examples

User:

> Create three 20-second clips from this official PPL match. I confirm I have permission: https://youtube.com/watch?v=VIDEO_ID

Action:

- Call `submit_clip_job` with `clip_count=3`, `target_duration=20`, `slowmo_speed=0.4`, and `confirm_rights=true`.
- Report the job ID and queued status.
- Call `wait_for_clip_job` until completed or until the turn must end.
- Deliver all returned `MEDIA:` tags after completion.
