from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_gate_feasibility_audit.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_gate_feasibility_audit", SCRIPT)
assert SPEC and SPEC.loader
audit_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_mod)


def synthetic_closes() -> pd.DataFrame:
    dt = pd.date_range("2021-01-01", "2024-06-30 23:00:00", freq="h", tz="UTC")
    rows = len(dt)
    btc = []
    eth = []
    btc_price = 100.0
    eth_price = 80.0
    for ts in dt:
        if ts.year == 2022:
            btc_ret = -0.00008
            eth_ret = -0.00010
        elif ts.year == 2024:
            btc_ret = -0.00002
            eth_ret = -0.00003
        else:
            btc_ret = 0.00005
            eth_ret = 0.00004
        btc_price *= 1.0 + btc_ret
        eth_price *= 1.0 + eth_ret
        btc.append(btc_price)
        eth.append(eth_price)
    assert rows == len(btc)
    return pd.DataFrame({"dt": dt, "BTCUSDT": btc, "ETHUSDT": eth})


def test_gate_feasibility_report_is_train_only_and_has_reference_failures() -> None:
    report = audit_mod.build_report_from_closes(
        synthetic_closes(),
        train_start="2021-01-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        symbols=("BTCUSDT", "ETHUSDT"),
        rebalance_h=240,
        prior_trials=100,
        n_trials=2,
        bootstrap_iterations=0,
        null_trials=3,
        null_seed=7,
    )

    assert report["kind"] == "v9_xsec_gate_feasibility_audit_v1"
    assert report["holdout_authorized"] is False
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert {row["name"] for row in report["references"]} == {"equal_weight_8_hold", "btc_buy_and_hold"}
    for row in report["references"]:
        assert "positive_3_of_4_years" in row["checks"]
        assert isinstance(row["failed_checks"], list)
    assert report["null_summary"]["trials"] == 3


def test_gate_feasibility_markdown_keeps_safety_warning() -> None:
    report = audit_mod.build_report_from_closes(
        synthetic_closes(),
        train_start="2021-01-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        symbols=("BTCUSDT", "ETHUSDT"),
        rebalance_h=240,
        prior_trials=0,
        n_trials=2,
        bootstrap_iterations=0,
        null_trials=1,
        null_seed=9,
    )

    text = audit_mod.format_markdown(report)

    assert "This is train-only research" in text
    assert "does not authorize holdout, paper trading, or live trading" in text
    assert "equal_weight_8_hold" in text
    assert "btc_buy_and_hold" in text
