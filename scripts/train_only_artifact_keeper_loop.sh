#!/usr/bin/env bash
set -euo pipefail

COMMAND_TIMEOUT_SEC="${TRAIN_ONLY_ARTIFACT_COMMAND_TIMEOUT_SEC:-10800}"
POLL_SEC="${TRAIN_ONLY_ARTIFACT_POLL_SEC:-120}"
MAX_RUNTIME_SEC="${TRAIN_ONLY_ARTIFACT_MAX_RUNTIME_SEC:-43200}"
OUTPUT_JSON=""

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --output-json)
      if [[ "$#" -lt 2 ]]; then
        echo "--output-json requires a value" >&2
        exit 2
      fi
      OUTPUT_JSON="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "unknown argument before --: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$OUTPUT_JSON" ]]; then
  echo "--output-json is required" >&2
  exit 2
fi
if [[ "$#" -lt 1 ]]; then
  echo "a command after -- is required" >&2
  exit 2
fi
if ! [[ "$COMMAND_TIMEOUT_SEC" =~ ^[0-9]+$ ]] || [[ "$COMMAND_TIMEOUT_SEC" -lt 60 ]]; then
  echo "TRAIN_ONLY_ARTIFACT_COMMAND_TIMEOUT_SEC must be an integer >= 60" >&2
  exit 2
fi
if ! [[ "$POLL_SEC" =~ ^[0-9]+$ ]] || [[ "$POLL_SEC" -lt 5 ]]; then
  echo "TRAIN_ONLY_ARTIFACT_POLL_SEC must be an integer >= 5" >&2
  exit 2
fi
if ! [[ "$MAX_RUNTIME_SEC" =~ ^[0-9]+$ ]] || [[ "$MAX_RUNTIME_SEC" -lt 60 ]]; then
  echo "TRAIN_ONLY_ARTIFACT_MAX_RUNTIME_SEC must be an integer >= 60" >&2
  exit 2
fi

START_TS="$(date +%s)"

is_output_running() {
  python3 - "$OUTPUT_JSON" <<'PY'
import subprocess
import sys

target = sys.argv[1]
try:
    rows = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
except Exception:
    sys.exit(1)
for line in rows.splitlines()[1:]:
    line = line.strip()
    if not line:
        continue
    _, _, args = line.partition(" ")
    if "train_only_artifact_keeper_loop.sh" in args:
        continue
    if f"--out-json {target}" in args or f"--out-json={target}" in args:
        print(line.split(None, 1)[0])
        sys.exit(0)
sys.exit(1)
PY
}

while true; do
  if [[ -s "$OUTPUT_JSON" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) artifact complete: $OUTPUT_JSON"
    exit 0
  fi

  now="$(date +%s)"
  elapsed=$((now - START_TS))
  if [[ "$elapsed" -ge "$MAX_RUNTIME_SEC" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) timeout waiting for artifact completion: $OUTPUT_JSON" >&2
    exit 124
  fi

  if running_pid="$(is_output_running)"; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) artifact command already running pid=$running_pid output=$OUTPUT_JSON elapsed=${elapsed}s"
    sleep "$POLL_SEC"
    continue
  fi

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) starting artifact command output=$OUTPUT_JSON elapsed=${elapsed}s timeout=${COMMAND_TIMEOUT_SEC}s"
  set +e
  if command -v timeout >/dev/null 2>&1; then
    timeout "$COMMAND_TIMEOUT_SEC" "$@"
    rc="$?"
  else
    "$@"
    rc="$?"
  fi
  set -e

  if [[ -s "$OUTPUT_JSON" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) artifact complete after command: $OUTPUT_JSON"
    exit 0
  fi
  if [[ "$rc" -eq 0 || "$rc" -eq 124 ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) artifact still incomplete after rc=$rc; will retry/resume"
    sleep "$POLL_SEC"
    continue
  fi
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) artifact command failed rc=$rc output=$OUTPUT_JSON" >&2
  exit "$rc"
done
