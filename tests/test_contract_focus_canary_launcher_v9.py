from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

import subprocess


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_contract_focus_canary_launcher.py"
SPEC = importlib.util.spec_from_file_location("v9_contract_focus_canary_launcher", SCRIPT)
assert SPEC and SPEC.loader
launcher_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher_mod)


def candidate(session: str = "v9_contract_focus_canary_1h_aaa_long_watch") -> dict[str, Any]:
    return {
        "session": session,
        "timeframe": "1h",
        "symbol": "AAAUSDT",
        "side": "long",
        "env": {
            "CONTRACT_EDGE_CANARY_TIMEFRAME": "1h",
            "CONTRACT_EDGE_CANARY_SYMBOLS": "AAAUSDT",
            "CONTRACT_EDGE_CANARY_ALLOWED_PAIRS": "AAAUSDT:long",
        },
    }


def write_plan(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(
            {
                "kind": "contract_focus_canary_plan_v1",
                "candidates": rows,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            }
        )
    )


def test_focus_canary_launcher_starts_missing_session(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    write_plan(plan, [candidate()])
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kwargs))
        if cmd[:2] == ["tmux", "has-session"]:
            return subprocess.CompletedProcess(cmd, 1, "", "missing")
        assert cmd == ["scripts/start_contract_edge_canary_watch.sh", "v9_contract_focus_canary_1h_aaa_long_watch"]
        assert kwargs["env"]["CONTRACT_EDGE_CANARY_ALLOWED_PAIRS"] == "AAAUSDT:long"
        return subprocess.CompletedProcess(cmd, 0, "started", "")

    payload = launcher_mod.run_launcher(
        Namespace(plan_json=str(plan), max_launches=3, launch=True),
        runner=fake_run,
    )

    assert payload["summary"]["started"] == 1
    assert payload["rows"][0]["status"] == "started"
    assert len(calls) == 2


def test_focus_canary_launcher_skips_existing_session(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    write_plan(plan, [candidate()])
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "exists", "")

    payload = launcher_mod.run_launcher(
        Namespace(plan_json=str(plan), max_launches=3, launch=True),
        runner=fake_run,
    )

    assert payload["summary"]["already_running"] == 1
    assert payload["rows"][0]["status"] == "already_running"
    assert calls == [["tmux", "has-session", "-t", "=v9_contract_focus_canary_1h_aaa_long_watch"]]


def test_focus_canary_launcher_dry_run_does_not_start(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    write_plan(plan, [candidate()])
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "missing")

    payload = launcher_mod.run_launcher(
        Namespace(plan_json=str(plan), max_launches=3, launch=False),
        runner=fake_run,
    )

    assert payload["summary"]["started"] == 0
    assert payload["rows"][0]["status"] == "dry_run_ready"
    assert calls == [["tmux", "has-session", "-t", "=v9_contract_focus_canary_1h_aaa_long_watch"]]


def test_focus_canary_launcher_rejects_bad_session_name(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    write_plan(plan, [candidate("-bad")])

    payload = launcher_mod.run_launcher(
        Namespace(plan_json=str(plan), max_launches=3, launch=True),
        runner=lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )

    assert payload["rows"][0]["status"] == "invalid_session_name"
