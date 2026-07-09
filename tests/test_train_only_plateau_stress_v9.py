from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_plateau_stress.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_plateau_stress", SCRIPT)
assert SPEC and SPEC.loader
stress_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stress_mod)


def close_matrix(periods: int = 1200) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "dt": dt,
            "AAA": [100 + idx * 0.20 for idx in range(periods)],
            "BBB": [100 + idx * 0.15 for idx in range(periods)],
            "CCC": [100 + idx * 0.10 for idx in range(periods)],
            "DDD": [100 - idx * 0.01 for idx in range(periods)],
        }
    )


def config(**overrides: Any) -> dict[str, Any]:
    base = {
        "k": 2,
        "lookback_h": 24,
        "market_filter_h": 0,
        "n_tranches": 1,
        "rebalance_h": 24,
        "score_mode": "mom",
        "skip_h": 0,
        "vol_target_ann": 0.0,
    }
    base.update(overrides)
    return base


def write_artifact(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"advance_passed": True, "config": config()},
        {"advance_passed": True, "config": config(lookback_h=48)},
    ]
    path.write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "symbols": ["AAA", "BBB", "CCC", "DDD"],
                "config": {
                    "symbols": ["AAA", "BBB", "CCC", "DDD"],
                    "cache_dir": "unused",
                    "train_start": "2020-01-01",
                    "train_end": "2020-02-20 23:00:00",
                    "embargo_start": "2020-03-01",
                },
                "summary": {
                    "accepted_train_only": True,
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                    "pass_count": 2,
                    "rows": 2,
                },
                "data": {"symbols": ["AAA", "BBB", "CCC", "DDD"]},
                "top": rows,
            }
        )
    )


def write_triage(path: Path, artifact: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": "v9_train_only_candidate_triage_v1",
                "ranked_candidates": [
                    {
                        "decision": "shortlist_plateau_candidate",
                        "artifact": str(artifact),
                        "config": config(),
                    }
                ],
            }
        )
    )


def test_plateau_stress_builds_train_only_report_from_triage(tmp_path, monkeypatch) -> None:
    artifact = tmp_path / "artifacts/v9/contract_lab/plateau.json"
    triage = tmp_path / "artifacts/v9/reviews/triage.json"
    write_artifact(artifact)
    write_triage(triage, artifact)
    monkeypatch.setattr(stress_mod, "load_close_matrix", lambda *args, **kwargs: close_matrix())

    report = stress_mod.build_stress(
        artifact,
        tmp_path,
        triage_path=triage,
        limit=4,
        phase_step_h=12,
        min_phase_sharpe=-99.0,
        max_phase_range_to_median=999.0,
        cost15_min_sharpe=-99.0,
        cost15_min_wf_q25=-99.0,
        cost20_min_sharpe=-99.0,
        cost20_min_loso_sharpe=-99.0,
    )
    markdown = stress_mod.format_markdown(report)

    assert report["holdout_accessed"] is False
    assert report["holdout_authorized"] is False
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["pass_count"] == 1
    candidate = report["candidates"][0]
    assert [row["offset_h"] for row in candidate["phase_stress"]["variants"]] == [0, 12]
    assert [row["multiplier"] for row in candidate["cost_stress"]] == [1.5, 2.0]
    assert candidate["verdict"]["decision"] == "train_only_plateau_stress_pass"
    assert "holdout_accessed: `False`" in markdown
    assert "does not authorize holdout" in markdown
