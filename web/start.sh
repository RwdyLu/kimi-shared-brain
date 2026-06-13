#!/bin/bash
cd /root/.openclaw/workspace/kimi-shared-brain
python3 web/server.py > logs/web_server.log 2>&1 &
echo $! > web/server.pid
echo "Web server started on PID $(cat web/server.pid)"
