#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
SKILL_DIR="${HERMES_HOME}/skills/media/padel-clipper"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Missing virtual environment at ${VENV_DIR}" >&2
  echo "Create it with: python3 -m venv ${VENV_DIR}" >&2
  exit 1
fi

"${VENV_DIR}/bin/python" -m pip install -e "${PROJECT_ROOT}[hermes]"

mkdir -p "${SKILL_DIR}"
cp "${SCRIPT_DIR}/padel-clipper/SKILL.md" "${SKILL_DIR}/SKILL.md"

cat <<EOF

Hermes clipper integration installed.

1. Merge this block into ${HERMES_HOME}/config.yaml:

mcp_servers:
  sports_clipper:
    command: "${VENV_DIR}/bin/clipper-mcp"
    env:
      CLIPPER_PROJECT_ROOT: "${PROJECT_ROOT}"
      CLIPPER_JOBS_ROOT: "${PROJECT_ROOT}/data/jobs"
    tools:
      include:
        - submit_clip_job
        - get_clip_job
        - list_clip_outputs
        - cancel_clip_job

2. Start the worker in one terminal:

   ${VENV_DIR}/bin/clipper-worker

3. Configure Telegram once:

   hermes gateway setup

4. Start Hermes messaging:

   hermes gateway

Skill installed at: ${SKILL_DIR}/SKILL.md
EOF
