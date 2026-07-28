from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_xsec_rescue_config_until_parent.sh"


def write_fake_rescue_plan(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    fake = scripts / "v9_xsec_rescue_plan.py"
    fake.write_text(
        "import argparse, json\n"
        "p=argparse.ArgumentParser()\n"
        "p.add_argument('artifact')\n"
        "p.add_argument('--top-k')\n"
        "p.add_argument('--budget-per-seed')\n"
        "p.add_argument('--out-plan')\n"
        "p.add_argument('--out-configs')\n"
        "a=p.parse_args()\n"
        "open(a.out_plan,'w').write(json.dumps({'artifact':a.artifact,'top_k':a.top_k}))\n"
        "open(a.out_configs,'w').write(json.dumps([{'lookback_h':168},{'lookback_h':336}]))\n"
    )


def run_refresh(tmp_path: Path, parent: Path, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--parent-output-json",
            str(parent),
            "--source-artifact",
            "active.progress.jsonl",
            "--out-plan",
            "artifacts/plan.json",
            "--out-configs",
            "artifacts/configs.json",
            "--once",
            *(extra or []),
        ],
        cwd=tmp_path,
        env={**os.environ, "REFRESH_XSEC_RESCUE_SLEEP_SEC": "1"},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_refresh_writes_plan_and_configs_atomically(tmp_path) -> None:
    write_fake_rescue_plan(tmp_path)
    parent = tmp_path / "missing_parent.json"

    result = run_refresh(tmp_path, parent)

    assert result.returncode == 0, result.stderr
    assert "refreshed configs=2 sha1=" in result.stdout
    assert json.loads((tmp_path / "artifacts" / "configs.json").read_text()) == [
        {"lookback_h": 168},
        {"lookback_h": 336},
    ]
    assert json.loads((tmp_path / "artifacts" / "plan.json").read_text())["artifact"] == "active.progress.jsonl"


def test_refresh_stops_without_writing_when_parent_exists(tmp_path) -> None:
    write_fake_rescue_plan(tmp_path)
    parent = tmp_path / "parent.json"
    parent.write_text("{}")

    result = run_refresh(tmp_path, parent)

    assert result.returncode == 0, result.stderr
    assert "parent_exists; stop_refresh" in result.stdout
    assert not (tmp_path / "artifacts" / "configs.json").exists()
