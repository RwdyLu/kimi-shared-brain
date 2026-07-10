from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LIVE_SCRIPT = ROOT / "scripts" / "v9_xsec_live_canary_readiness_gate.py"
LIVE_SPEC = importlib.util.spec_from_file_location("v9_xsec_live_canary_readiness_gate", LIVE_SCRIPT)
assert LIVE_SPEC and LIVE_SPEC.loader
live_mod = importlib.util.module_from_spec(LIVE_SPEC)
LIVE_SPEC.loader.exec_module(live_mod)

SHADOW_SCRIPT = ROOT / "scripts" / "v9_xsec_paper_shadow.py"
SHADOW_SPEC = importlib.util.spec_from_file_location("v9_xsec_paper_shadow", SHADOW_SCRIPT)
assert SHADOW_SPEC and SHADOW_SPEC.loader
shadow_mod = importlib.util.module_from_spec(SHADOW_SPEC)
SHADOW_SPEC.loader.exec_module(shadow_mod)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def write_ready_inputs(tmp_path: Path) -> dict[str, Path]:
    paper_gate = tmp_path / "paper_gate.json"
    shadow_state = tmp_path / "shadow.json"
    ledger = tmp_path / "ledger.jsonl"
    cost_csv = tmp_path / "cost.csv"
    data_status = tmp_path / "data_freshness.json"
    approval = tmp_path / "approval.json"
    artifact = "candidate.json"
    write_json(
        paper_gate,
        {
            "paper_trading_authorized": True,
            "source_holdout_batch": "state/v9_holdout_protocol_state.json",
            "candidate": {"artifact": artifact},
        },
    )
    write_json(
        shadow_state,
        {
            "status": "paper_complete_live_manual_review_required",
            "source_gate": "state/xsec_paper_readiness_gate_state.json",
            "live_trading_authorized": False,
            "shadow": {"costs": {"40bps": {"max_drawdown": 0.05}}},
        },
    )
    weights = [0.0, 0.10, 0.20]
    for idx, weight in enumerate(weights):
        shadow_mod.append_ledger(
            {
                "status": "paper_running",
                "source_gate": "state/xsec_paper_readiness_gate_state.json",
                "paper_trading_authorized": True,
                "candidate": {"artifact": artifact},
                "shadow": {
                    "latest_dt": f"2026-07-{10 + idx:02d}T00:00:00+00:00",
                    "latest_rebalance_dt": f"2026-07-{10 + idx:02d}T00:00:00+00:00",
                    "latest_weights": {"BTCUSDT": weight},
                    "costs": {"40bps": {"max_drawdown": 0.05, "rebalance_event_count": idx}},
                },
            },
            ledger,
            recorded_at=f"2026-07-{10 + idx:02d}T00:00:00+00:00",
        )
    cost_csv.write_text(
        "recorded_at,latest_dt,symbol,bid,ask,mid,spread_bps,quote_volume_24h,"
        "target_weight,previous_weight,target_weight_delta,observed_cost_bps\n"
        "2026-07-11T00:00:00+00:00,2026-07-11T00:00:00+00:00,BTCUSDT,99,101,100,2,100000,0.1,0,0.1,2\n"
        "2026-07-12T00:00:00+00:00,2026-07-12T00:00:00+00:00,BTCUSDT,99,101,100,3,100000,0.2,0.1,0.1,3\n"
    )
    write_json(
        data_status,
        {
            "data_fresh": True,
            "updated_at": live_mod.now_utc(),
            "checks": {"cache_age_le_max": True},
            "duplicate_latest_dt_records": 0,
        },
    )
    return {
        "paper_gate": paper_gate,
        "shadow_state": shadow_state,
        "ledger": ledger,
        "cost_csv": cost_csv,
        "data_status": data_status,
        "approval": approval,
    }


def build_report(paths: dict[str, Path]) -> dict:
    return live_mod.build_report(
        paper_gate_state_path=paths["paper_gate"],
        shadow_state_path=paths["shadow_state"],
        ledger_path=paths["ledger"],
        cost_evidence_csv=paths["cost_csv"],
        data_freshness_status_path=paths["data_status"],
        approval_path=paths["approval"],
        min_wall_clock_weeks=0,
        min_rebalance_events=2,
        max_ledger_gap_hours=48.0,
        max_paper_drawdown=0.15,
        assumed_cost_bps=40.0,
        cost_percentile=0.90,
        min_abs_weight_delta=1e-9,
        max_data_freshness_status_age_hours=2.0,
        max_duplicate_latest_dt_records=0,
    )


def test_live_canary_gate_requires_manual_approval_even_when_evidence_passes(tmp_path) -> None:
    paths = write_ready_inputs(tmp_path)

    report = build_report(paths)

    assert report["decision"] == "live_canary_manual_approval_required"
    assert report["checks"]["manual_approval_present"] is False
    assert report["live_canary_ready"] is False
    assert report["live_trading_authorized"] is False


def test_live_canary_gate_accepts_matching_manual_approval_but_never_authorizes_live(tmp_path) -> None:
    paths = write_ready_inputs(tmp_path)
    pending = build_report(paths)
    write_json(
        paths["approval"],
        {
            "approved_unsigned_report_sha256": pending["unsigned_report_sha256"],
            "candidate_artifact": "candidate.json",
        },
    )

    report = build_report(paths)

    assert report["decision"] == "live_canary_ready_manual_execution_required"
    assert report["checks"]["manual_approval_present"] is True
    assert report["live_canary_ready"] is True
    assert report["live_trading_authorized"] is False


def test_live_canary_gate_blocks_tampered_ledger(tmp_path) -> None:
    paths = write_ready_inputs(tmp_path)
    paths["ledger"].write_text(paths["ledger"].read_text().replace("0.2", "0.9"))

    report = build_report(paths)

    assert report["decision"] == "live_canary_blocked"
    assert report["checks"]["ledger_chain_valid"] is False


def test_live_canary_gate_blocks_stale_data_freshness_status(tmp_path) -> None:
    paths = write_ready_inputs(tmp_path)
    write_json(
        paths["data_status"],
        {
            "data_fresh": False,
            "updated_at": live_mod.now_utc(),
            "checks": {"cache_age_le_max": False},
        },
    )

    report = build_report(paths)

    assert report["decision"] == "live_canary_blocked"
    assert report["checks"]["data_fresh"] is False
