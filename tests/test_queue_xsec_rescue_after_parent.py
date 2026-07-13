from __future__ import annotations

import json
import os
import subprocess
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "queue_xsec_rescue_after_parent.sh"


def write_fake_scripts(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    keeper = scripts / "train_only_artifact_keeper_loop.sh"
    keeper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "OUT=''\n"
        "while [[ $# -gt 0 ]]; do\n"
        "  case \"$1\" in\n"
        "    --output-json) OUT=\"$2\"; shift 2 ;;\n"
        "    --) shift; break ;;\n"
        "    *) shift ;;\n"
        "  esac\n"
        "done\n"
        "echo keeper_ran > keeper.txt\n"
        "mkdir -p \"$(dirname \"$OUT\")\"\n"
        "printf '{\"summary\":{\"accepted_train_only\":false},\"rows\":[]}' > \"$OUT\"\n"
    )
    keeper.chmod(0o755)
    ingest = scripts / "v9_ingest_train_only_artifact.py"
    ingest.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path('ingest.txt').write_text(' '.join(sys.argv[1:]))\n"
    )
    rescue = scripts / "v9_xsec_rescue_plan.py"
    rescue.write_text(
        "import argparse, json\n"
        "p=argparse.ArgumentParser()\n"
        "p.add_argument('artifact')\n"
        "p.add_argument('--top-k')\n"
        "p.add_argument('--budget-per-seed')\n"
        "p.add_argument('--out-plan')\n"
        "p.add_argument('--out-configs')\n"
        "a=p.parse_args()\n"
        "open(a.out_plan,'w').write(json.dumps({'artifact':a.artifact,'top_k':a.top_k}))\n"
        "open(a.out_configs,'w').write(json.dumps([{'refreshed':True,'budget':a.budget_per_seed}]))\n"
    )


def run_queue(
    tmp_path: Path,
    parent: Path,
    *,
    fingerprint: str = "abc123",
    prior_trials: str = "10",
    extra: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "QUEUE_XSEC_RESCUE_POLL_SEC": "1",
        "QUEUE_XSEC_RESCUE_SLOT_POLL_SEC": "1",
    }
    return subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--parent-output-json",
            str(parent),
            "--output-json",
            "artifacts/out.json",
            "--output-md",
            "artifacts/out.md",
            "--report-json",
            "state/report.json",
            "--config-list-json",
            "configs.json",
            "--data-snapshot",
            "snapshot.parquet",
            "--task-name",
            "rescue_task",
            "--preset",
            "hq_active_recent",
            "--fingerprint",
            fingerprint,
            "--prior-trials",
            prior_trials,
            "--max-parallel-factory",
            "999",
            *(extra or []),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_queue_skips_rescue_when_parent_accepted(tmp_path) -> None:
    write_fake_scripts(tmp_path)
    parent = tmp_path / "parent.json"
    parent.write_text(json.dumps({"summary": {"accepted_train_only": True}}))

    result = run_queue(tmp_path, parent)

    assert result.returncode == 0, result.stderr
    assert "parent accepted; skipping rescue" in result.stdout
    assert not (tmp_path / "keeper.txt").exists()
    assert not (tmp_path / "ingest.txt").exists()


def test_queue_runs_rescue_and_ingest_when_parent_rejected(tmp_path) -> None:
    write_fake_scripts(tmp_path)
    parent = tmp_path / "parent.json"
    parent.write_text(json.dumps({"summary": {"accepted_train_only": False}}))

    result = run_queue(tmp_path, parent)

    assert result.returncode == 0, result.stderr
    assert "parent did not accept; queueing rescue" in result.stdout
    assert (tmp_path / "keeper.txt").read_text().strip() == "keeper_ran"
    assert "rescue_task" in (tmp_path / "ingest.txt").read_text()


def test_queue_auto_fingerprint_uses_config_list_sha1(tmp_path) -> None:
    write_fake_scripts(tmp_path)
    parent = tmp_path / "parent.json"
    parent.write_text(json.dumps({"summary": {"accepted_train_only": False}}))
    config = tmp_path / "configs.json"
    config.write_text(json.dumps([{"lookback_h": 168, "score_mode": "risk_adj_mom"}], sort_keys=True))
    expected = hashlib.sha1(config.read_bytes()).hexdigest()

    result = run_queue(tmp_path, parent, fingerprint="auto")

    assert result.returncode == 0, result.stderr
    assert f"rescue_fingerprint={expected}" in result.stdout
    assert f"--fingerprint {expected}" in (tmp_path / "ingest.txt").read_text()


def test_queue_refreshes_rescue_configs_from_parent_before_run(tmp_path) -> None:
    write_fake_scripts(tmp_path)
    parent = tmp_path / "parent.json"
    parent.write_text(json.dumps({"summary": {"accepted_train_only": False}, "rows": []}))
    (tmp_path / "configs.json").write_text(json.dumps([{"stale": True}]))

    result = run_queue(
        tmp_path,
        parent,
        extra=[
            "--refresh-before-run",
            "--refresh-plan-json",
            "artifacts/refresh_plan.json",
            "--refresh-top-k",
            "7",
            "--refresh-budget-per-seed",
            "9",
        ],
    )

    assert result.returncode == 0, result.stderr
    assert "refreshed_rescue_from_parent configs=configs.json plan=artifacts/refresh_plan.json" in result.stdout
    assert json.loads((tmp_path / "configs.json").read_text()) == [{"refreshed": True, "budget": "9"}]
    assert json.loads((tmp_path / "artifacts" / "refresh_plan.json").read_text())["top_k"] == "7"


def test_queue_auto_prior_trials_uses_parent_effective_trials(tmp_path) -> None:
    write_fake_scripts(tmp_path)
    parent = tmp_path / "parent.json"
    parent.write_text(
        json.dumps(
            {
                "summary": {"accepted_train_only": False},
                "selection_validation": {
                    "prior_trials": 100,
                    "n_configs_tested": 25,
                    "effective_trials": 4321,
                },
            }
        )
    )

    result = run_queue(tmp_path, parent, prior_trials="auto")

    assert result.returncode == 0, result.stderr
    assert "rescue_prior_trials=4321" in result.stdout
    assert "--prior-trials 4321" in (tmp_path / "ingest.txt").read_text()


def test_queue_auto_prior_trials_falls_back_to_parent_prior_plus_rows(tmp_path) -> None:
    write_fake_scripts(tmp_path)
    parent = tmp_path / "parent.json"
    parent.write_text(
        json.dumps(
            {
                "summary": {"accepted_train_only": False, "rows": 12},
                "selection_validation": {"prior_trials": 200},
            }
        )
    )

    result = run_queue(tmp_path, parent, prior_trials="auto")

    assert result.returncode == 0, result.stderr
    assert "rescue_prior_trials=212" in result.stdout
    assert "--prior-trials 212" in (tmp_path / "ingest.txt").read_text()
