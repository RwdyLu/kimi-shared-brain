#!/usr/bin/env python3
"""
System Health Reporter
系統健康回報器

Generates health check reports and sends to Discord webhook.
Supports both PM2 and nohup (.monitor.pid) scheduler detection.
"""

import os
import sys
import json
import time
import psutil
import subprocess
import requests
from pathlib import Path
from datetime import datetime, timedelta

# Paths
PROJECT_ROOT = Path("/root/.openclaw/workspace/kimi-shared-brain")
STATE_DIR = PROJECT_ROOT / "state"
LOGS_DIR = PROJECT_ROOT / "logs"
PID_FILE = STATE_DIR / ".monitor.pid"
WEBHOOK_CONFIG = PROJECT_ROOT / "config" / "channel_config.json"


def get_webhook_url() -> str:
    """Read Discord webhook URL from config."""
    try:
        with open(WEBHOOK_CONFIG, "r") as f:
            config = json.load(f)
        return config.get("webhook_url", "")
    except Exception:
        return os.environ.get("DISCORD_WEBHOOK_URL", "")


def check_scheduler_status() -> dict:
    """
    Check scheduler status using multiple methods:
    1. PM2 process list
    2. .monitor.pid file + os.kill(pid, 0)
    3. Recent log activity
    """
    result = {
        "running": False,
        "method": None,
        "pid": None,
        "status_text": "Stopped / 已停止",
        "last_run": None,
        "error": None,
    }

    # Method 1: Check PM2
    try:
        pm2_result = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if pm2_result.returncode == 0:
            pm2_data = json.loads(pm2_result.stdout)
            for proc in pm2_data:
                name = proc.get("name", "")
                if "scheduler" in name.lower() or "trading" in name.lower():
                    status = proc.get("pm2_env", {}).get("status", "")
                    if status == "online":
                        result["running"] = True
                        result["method"] = "PM2"
                        result["pid"] = proc.get("pid")
                        result["status_text"] = f"Running (PM2, PID {proc.get('pid')})"
                        return result
    except Exception as e:
        result["error"] = f"PM2 check failed: {e}"

    # Method 2: Check .monitor.pid file
    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                pid_str = f.read().strip()
            pid = int(pid_str)
            os.kill(pid, 0)  # Check if process exists
            result["running"] = True
            result["method"] = "nohup"
            result["pid"] = pid
            result["status_text"] = f"Running (nohup, PID {pid})"
            return result
        except (OSError, ValueError, ProcessLookupError):
            pass  # PID file stale or invalid

    # Method 3: Check recent log activity (fallback)
    log_file = LOGS_DIR / "scheduler.log"
    if log_file.exists():
        try:
            stat = log_file.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)
            minutes_ago = (datetime.now() - mtime).total_seconds() / 60
            if minutes_ago < 10:
                result["running"] = True
                result["method"] = "log"
                result["status_text"] = f"Running (log activity {int(minutes_ago)}m ago)"
                return result
        except Exception:
            pass

    return result


def get_system_metrics() -> dict:
    """Get basic system metrics."""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory()._asdict(),
        "disk": psutil.disk_usage("/")._asdict(),
        "uptime": timedelta(seconds=int(time.time() - psutil.boot_time())),
    }


def get_last_scheduler_run() -> dict:
    """Get info about last scheduler run from log."""
    log_file = LOGS_DIR / "scheduler.log"
    result = {"run_id": None, "timestamp": None, "signals": 0, "duration": None}

    if not log_file.exists():
        return result

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Find last completed run
        for line in reversed(lines[-2000:]):
            if "Run #" in line and "completed" in line:
                import re
                match = re.search(r"Run #(\d+)", line)
                if match:
                    result["run_id"] = int(match.group(1))
                ts_match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
                if ts_match:
                    result["timestamp"] = ts_match.group(1)
                break
    except Exception:
        pass

    return result


def build_report() -> dict:
    """Build full health report."""
    scheduler = check_scheduler_status()
    metrics = get_system_metrics()
    last_run = get_last_scheduler_run()

    memory = metrics["memory"]
    disk = metrics["disk"]
    uptime = metrics["uptime"]

    # Determine overall status
    overall = "✅ 健康"
    alerts = []

    if not scheduler["running"]:
        overall = "🚨 告警"
        alerts.append("Scheduler is stopped")

    if memory["percent"] > 90:
        overall = "🚨 告警"
        alerts.append(f"Memory usage critical: {memory['percent']}%")
    elif memory["percent"] > 80:
        if overall == "✅ 健康":
            overall = "⚠️ 注意"
        alerts.append(f"Memory usage high: {memory['percent']}%")

    if disk["percent"] > 90:
        overall = "🚨 告警"
        alerts.append(f"Disk usage critical: {disk['percent']}%")

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S CST"),
        "overall": overall,
        "system": {
            "uptime": str(uptime),
            "cpu": f"{metrics['cpu_percent']:.1f}%",
            "memory": f"{memory['used'] / 1024**3:.1f}G / {memory['total'] / 1024**3:.1f}G ({memory['percent']}%)",
            "disk": f"{disk['used'] / 1024**3:.1f}G / {disk['total'] / 1024**3:.1f}G ({disk['percent']}%)",
        },
        "scheduler": {
            "status": scheduler["status_text"],
            "running": scheduler["running"],
            "method": scheduler["method"],
            "pid": scheduler["pid"],
        },
        "last_run": last_run,
        "alerts": alerts,
    }

    return report


def format_discord_message(report: dict) -> dict:
    """Format report for Discord webhook embed."""
    color = 0x00FF00 if report["overall"] == "✅ 健康" else 0xFFA500 if "⚠️" in report["overall"] else 0xFF0000

    fields = [
        {"name": "System", "value": f"Uptime: {report['system']['uptime']}\nCPU: {report['system']['cpu']}\nMemory: {report['system']['memory']}\nDisk: {report['system']['disk']}", "inline": False},
        {"name": "Scheduler", "value": report["scheduler"]["status"], "inline": True},
    ]

    if report["last_run"]["run_id"]:
        fields.append({
            "name": "Last Run",
            "value": f"Run #{report['last_run']['run_id']} at {report['last_run']['timestamp']}",
            "inline": True,
        })

    if report["alerts"]:
        fields.append({
            "name": "Alerts",
            "value": "\n".join(f"• {a}" for a in report["alerts"]),
            "inline": False,
        })

    return {
        "embeds": [{
            "title": f"📊 System Health Report - {report['timestamp']}",
            "color": color,
            "fields": fields,
        }]
    }


def send_to_discord(payload: dict) -> bool:
    """Send report to Discord webhook."""
    webhook_url = get_webhook_url()
    if not webhook_url:
        print("❌ No Discord webhook URL configured")
        return False

    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        print(f"✅ Discord notification sent (status {resp.status_code})")
        return True
    except Exception as e:
        print(f"❌ Failed to send Discord notification: {e}")
        return False


def main():
    """Main entry point."""
    print("=" * 50)
    print("System Health Reporter")
    print("=" * 50)

    report = build_report()

    # Print to console
    print(f"\nTimestamp: {report['timestamp']}")
    print(f"Overall: {report['overall']}")
    print(f"\nScheduler: {report['scheduler']['status']}")
    print(f"  Running: {report['scheduler']['running']}")
    print(f"  Method: {report['scheduler']['method']}")
    print(f"  PID: {report['scheduler']['pid']}")
    print(f"\nSystem:")
    for k, v in report["system"].items():
        print(f"  {k}: {v}")
    if report["alerts"]:
        print(f"\nAlerts:")
        for alert in report["alerts"]:
            print(f"  ⚠️ {alert}")

    # Send to Discord
    discord_payload = format_discord_message(report)
    send_to_discord(discord_payload)

    # Save report to file
    report_file = PROJECT_ROOT / f"healthcheck_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md"
    with open(report_file, "w") as f:
        f.write(f"# Health Report - {report['timestamp']}\n\n")
        f.write(f"**Overall**: {report['overall']}\n\n")
        f.write(f"## Scheduler\n")
        f.write(f"- Status: {report['scheduler']['status']}\n")
        f.write(f"- Running: {report['scheduler']['running']}\n")
        f.write(f"- Method: {report['scheduler']['method']}\n")
        f.write(f"- PID: {report['scheduler']['pid']}\n\n")
        f.write(f"## System\n")
        for k, v in report["system"].items():
            f.write(f"- {k}: {v}\n")
        if report["alerts"]:
            f.write(f"\n## Alerts\n")
            for alert in report["alerts"]:
                f.write(f"- ⚠️ {alert}\n")

    print(f"\n📄 Report saved to: {report_file}")

    # Exit with error code if scheduler is stopped
    if not report["scheduler"]["running"]:
        print("\n🚨 Scheduler is not running!")
        sys.exit(1)

    print("\n✅ All checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
