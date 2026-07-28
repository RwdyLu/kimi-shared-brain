#!/usr/bin/env bash
set -euo pipefail

POLL_SEC="${WATCH_TRAIN_ONLY_INGEST_POLL_SEC:-60}"
TIMEOUT_SEC="${WATCH_TRAIN_ONLY_INGEST_TIMEOUT_SEC:-21600}"

if [[ "$#" -lt 1 ]]; then
  echo "usage: $0 <v9_ingest_train_only_artifact.py args...>" >&2
  exit 2
fi

if ! [[ "$POLL_SEC" =~ ^[0-9]+$ ]] || [[ "$POLL_SEC" -lt 1 ]]; then
  echo "WATCH_TRAIN_ONLY_INGEST_POLL_SEC must be an integer >= 1" >&2
  exit 2
fi
if ! [[ "$TIMEOUT_SEC" =~ ^[0-9]+$ ]] || [[ "$TIMEOUT_SEC" -lt 1 ]]; then
  echo "WATCH_TRAIN_ONLY_INGEST_TIMEOUT_SEC must be an integer >= 1" >&2
  exit 2
fi

OUTPUT_JSON=""
prev=""
for arg in "$@"; do
  if [[ "$prev" == "--output-json" ]]; then
    OUTPUT_JSON="$arg"
    break
  fi
  prev="$arg"
done
if [[ -z "$OUTPUT_JSON" ]]; then
  echo "--output-json is required in ingest args" >&2
  exit 2
fi

PROGRESS_JSONL="${OUTPUT_JSON%.json}.progress.jsonl"
PROGRESS_META="${OUTPUT_JSON%.json}.progress.meta.json"
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
    if "watch_train_only_artifact_ingest.sh" in args:
        continue
    if f"--out-json {target}" in args or f"--out-json={target}" in args:
        print(line.split(None, 1)[0])
        sys.exit(0)
sys.exit(1)
PY
}

output_json_is_valid() {
  python3 - "$OUTPUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text())
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(payload, dict) else 1)
PY
}

while true; do
  now="$(date +%s)"
  elapsed=$((now - START_TS))
  if [[ "$elapsed" -ge "$TIMEOUT_SEC" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) timeout waiting for $OUTPUT_JSON" >&2
    exit 124
  fi

  if [[ -s "$OUTPUT_JSON" ]] && output_json_is_valid; then
    if [[ ! -e "$PROGRESS_JSONL" && ! -e "$PROGRESS_META" ]]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ingesting completed artifact: $OUTPUT_JSON"
      exec python3 scripts/v9_ingest_train_only_artifact.py "$@"
    fi
    if ! is_output_running >/dev/null 2>&1; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ingesting completed artifact with stale progress files: $OUTPUT_JSON"
      exec python3 scripts/v9_ingest_train_only_artifact.py "$@"
    fi
  fi

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) waiting for $OUTPUT_JSON elapsed=${elapsed}s"
  sleep "$POLL_SEC"
done
