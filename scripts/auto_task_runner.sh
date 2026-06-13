#!/bin/bash
# Auto Task Runner - triggered by github watcher when new commits detected
# Runs task checks and any pending automation

cd /root/.openclaw/workspace/kimi-shared-brain

LOG_FILE="/tmp/task_runner.log"
echo "$(date): Task runner triggered" >> "$LOG_FILE"

# Check for assigned tasks
python3 scripts/auto_task_check.py >> "$LOG_FILE" 2>&1

# Pull any latest config changes
git pull origin main --quiet >> "$LOG_FILE" 2>&1

echo "$(date): Task runner completed" >> "$LOG_FILE"
