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

while true; do
  now="$(date +%s)"
  elapsed=$((now - START_TS))
  if [[ "$elapsed" -ge "$TIMEOUT_SEC" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) timeout waiting for $OUTPUT_JSON" >&2
    exit 124
  fi

  if [[ -s "$OUTPUT_JSON" && ! -e "$PROGRESS_JSONL" && ! -e "$PROGRESS_META" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ingesting completed artifact: $OUTPUT_JSON"
    exec python3 scripts/v9_ingest_train_only_artifact.py "$@"
  fi

  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) waiting for $OUTPUT_JSON elapsed=${elapsed}s"
  sleep "$POLL_SEC"
done
