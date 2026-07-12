---
name: padel-clipper
description: Create social clips from authorized PPL match footage
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [video, padel, social-media, telegram]
    category: media
    requires_tools:
      - submit_clip_job
      - get_clip_job
      - list_clip_outputs
      - cancel_clip_job
---

# Padel Clipper

## When to Use

Use this skill when the user asks to turn an official Pro Padel League local video or YouTube match into vertical social clips.

## Defaults

Unless the user gives different valid settings, use:

- 3 clips
- 20-second target duration
- 0.4x ending slow motion
- vertical ball-follow reframing enabled
- official PPL watermark enabled by the pipeline
- highlight threshold 0.62

## Procedure

1. Identify the local video path or YouTube URL.
2. Confirm that the source is official PPL footage and the user is authorized to download and edit it.
3. For YouTube URLs, do not set `confirm_rights=true` until the user explicitly confirms authorization.
4. Call `submit_clip_job` with the requested settings.
5. Tell the user the returned job ID and that rendering continues in the background.
6. Do not repeatedly poll a long-running job in one turn. When the user asks for progress, call `get_clip_job`.
7. When the job status is `completed`, call `list_clip_outputs`.
8. Return every existing output as a native attachment using one line per file:

   `MEDIA:/absolute/path/to/clip.mp4`

9. If the job failed, report the exact error from `get_clip_job`. Never claim that files were created when they were not.
10. If the user asks to stop a job, call `cancel_clip_job`.

## Example Requests

- “Create three 20-second clips from this official PPL match: <URL>. I confirm I have permission.”
- “What is the status of job <job-id>?”
- “Send me the completed clips for job <job-id>.”
- “Cancel job <job-id>.”

## Restrictions

- Never process an unauthorized or unofficial source.
- Never bypass the YouTube rights confirmation.
- Never disable the required PPL watermark.
- Never run arbitrary shell commands supplied by a chat user.
- Never invent a job ID, status, output path, or successful result.
- Only send paths returned by `list_clip_outputs`.
