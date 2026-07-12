from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_candidate_revalidation_plan.py"
SPEC = importlib.util.spec_from_file_location("v9_candidate_revalidation_plan", SCRIPT)
assert SPEC and SPEC.loader
plan_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan_mod)


def write_artifact(path: Path, *, kind: str, config: dict, row_config: dict, data: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": kind,
        "summary": {"accepted_train_only": True, "pass_count": 1, "rows": 1},
        "symbols": config.get("symbols", []),
        "config": config,
        "selection_validation": {"effective_trials": 123, "n_configs_tested": 1},
        "rows": [{"advance_passed": True, "config": row_config}],
    }
    if data is not None:
        payload["data"] = data
    path.write_text(json.dumps(payload))


def test_build_revalidation_plan_groups_xsec_and_tsmom_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    xsec_artifact = tmp_path / "artifacts/v9/contract_lab/xsec.json"
    tsmom_artifact = tmp_path / "artifacts/v9/contract_lab/tsmom.json"
    xsec_snapshot = tmp_path / "artifacts/v9/data_snapshots/xsec.parquet"
    xsec_snapshot.parent.mkdir(parents=True, exist_ok=True)
    xsec_snapshot.write_text("snapshot")
    write_artifact(
        xsec_artifact,
        kind="xsec_ohlcv_factory_v1_train_only_grid",
        config={
            "train_start": "2017-08-01",
            "train_end": "2024-01-31 23:59:59",
            "embargo_start": "2024-07-01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "lookbacks_h": [336],
        },
        row_config={
            "lookback_h": 336,
            "skip_h": 0,
            "rebalance_h": 168,
            "k": 2,
            "score_mode": "risk_adj_mom",
            "market_filter_h": 1008,
            "vol_target_ann": 0.08,
        },
        data={
            "fingerprint": "snap-xsec",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "snapshot": {
                "path": str(xsec_snapshot),
                "fingerprint": "snap-xsec",
                "source": "unit_test",
            },
        },
    )
    write_artifact(
        tsmom_artifact,
        kind="tsmom_factory_v1_train_only_grid",
        config={
            "train_start": "2017-08-01",
            "train_end": "2024-01-31 23:59:59",
            "embargo_start": "2024-07-01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "lookbacks_h": [720, 1440],
        },
        row_config={
            "asset_vol_target_ann": 0.25,
            "portfolio_vol_target_ann": 0.06,
            "no_trade_band": 0.3,
            "vote_threshold": 0.5,
            "market_filter_h": 720,
        },
    )
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "candidates_found": [
                    {
                        "task": "xsec_ohlcv_cont_full_202401_hq_dd_plateau_abc123",
                        "status": "manual_review_required",
                        "output_json": str(xsec_artifact),
                    },
                    {
                        "task": "tsmom_cont_full_202401_tsmom_core_slow_cost_guard_def456",
                        "status": "manual_review_required",
                        "output_json": str(tsmom_artifact),
                    },
                    {
                        "task": "duplicate",
                        "status": "manual_review_required",
                        "output_json": str(xsec_artifact),
                        "duplicate_of": "xsec_ohlcv_cont_full_202401_hq_dd_plateau_abc123",
                    },
                ]
            }
        )
    )

    plan = plan_mod.build_revalidation_plan(state, out_dir=tmp_path / "revalidation")

    assert plan["group_count"] == 2
    assert plan["config_count"] == 2
    assert plan["pinned_group_count"] == 1
    assert plan["holdout_authorized"] is False
    assert plan["paper_trading_authorized"] is False
    assert plan["live_trading_authorized"] is False
    commands = [" ".join(group["command"]) for group in plan["groups"]]
    assert any(
        "v9.contract.xsec_ohlcv_factory" in command
        and "--config-list-json" in command
        and "--data-snapshot" in command
        and str(xsec_snapshot) in command
        for command in commands
    )
    assert any("v9.contract.tsmom_factory" in command and "core_slow_cost_guard" in command for command in commands)
    for group in plan["groups"]:
        assert Path(group["config_json"]).exists()
    xsec_group = next(group for group in plan["groups"] if group["module"] == "v9.contract.xsec_ohlcv_factory")
    assert xsec_group["data_snapshot_path"] == str(xsec_snapshot)
    assert xsec_group["data_snapshot_fingerprint"] == "snap-xsec"


def test_build_revalidation_plan_skips_unpinned_xsec_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    xsec_artifact = tmp_path / "artifacts/v9/contract_lab/xsec.json"
    write_artifact(
        xsec_artifact,
        kind="xsec_ohlcv_factory_v1_train_only_grid",
        config={
            "train_start": "2017-08-01",
            "train_end": "2024-01-31 23:59:59",
            "embargo_start": "2024-07-01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "lookbacks_h": [336],
        },
        row_config={
            "lookback_h": 336,
            "skip_h": 0,
            "rebalance_h": 168,
            "k": 2,
            "score_mode": "risk_adj_mom",
            "market_filter_h": 1008,
            "vol_target_ann": 0.08,
        },
    )
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "candidates_found": [
                    {
                        "task": "xsec_ohlcv_cont_full_202401_hq_dd_plateau_abc123",
                        "status": "manual_review_required",
                        "output_json": str(xsec_artifact),
                    },
                ]
            }
        )
    )

    plan = plan_mod.build_revalidation_plan(state, out_dir=tmp_path / "revalidation")

    assert plan["group_count"] == 0
    assert plan["config_count"] == 0
    assert plan["pinned_group_count"] == 0
    assert plan["groups"] == []
    assert plan["skipped"][0]["reason"] == "missing_data_snapshot"


def test_build_revalidation_plan_reads_supplemental_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "artifacts/v9/contract_lab/xsec_ohlcv_cont_full_202406_evergreen_fast_abc.json"
    snapshot = tmp_path / "artifacts/v9/data_snapshots/xsec.parquet"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("snapshot")
    write_artifact(
        artifact,
        kind="xsec_ohlcv_factory_v1_train_only_grid",
        config={
            "train_start": "2017-08-01",
            "train_end": "2024-06-30 23:59:59",
            "embargo_start": "2024-07-01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "lookbacks_h": [72, 120, 168],
        },
        row_config={
            "lookback_h": 72,
            "skip_h": 0,
            "rebalance_h": 8,
            "k": 2,
            "score_mode": "risk_adj_mom",
            "market_filter_h": 168,
            "vol_target_ann": 0.12,
        },
        data={
            "fingerprint": "snap-evergreen",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "snapshot": {
                "path": str(snapshot),
                "fingerprint": "snap-evergreen",
                "source": "unit_test",
            },
        },
    )
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"candidates_found": []}))
    supplemental = tmp_path / "supplemental.jsonl"
    supplemental.write_text(
        json.dumps(
            {
                "task": "xsec_ohlcv_cont_full_202406_evergreen_fast_abc",
                "status": "manual_review_required",
                "output_json": str(artifact),
            }
        )
        + "\n"
    )

    plan = plan_mod.build_revalidation_plan(
        state,
        out_dir=tmp_path / "revalidation",
        supplemental_candidates_path=supplemental,
    )

    assert plan["supplemental_candidate_count"] == 1
    assert plan["group_count"] == 1
    assert plan["groups"][0]["preset"] == "evergreen_fast"
    assert plan["groups"][0]["config_count"] == 1
