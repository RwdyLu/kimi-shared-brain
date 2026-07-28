from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_rescue_hit_monitor.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_rescue_hit_monitor", SCRIPT)
assert SPEC and SPEC.loader
monitor_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor_mod)


def sample_row(
    *,
    sharpe20: float,
    sharpe40: float,
    year2022: float,
    max_dd: float = 0.20,
    advance: bool = False,
) -> dict:
    return {
        "advance_passed": advance,
        "advance_checks": {
            "positive_3_of_4_years": year2022 > 0,
            "selection_passed_before_validation": advance,
            "sharpe20_ge_1_2": sharpe20 >= 1.2,
            "sharpe40_ge_1": sharpe40 >= 1.0,
            "max_dd20_le_25pct": max_dd <= 0.25,
        },
        "config": {
            "score_mode": "risk_adj_mom",
            "lookback_h": 168,
            "rebalance_h": 72,
            "market_filter_h": 336,
            "vol_target_ann": 0.06,
            "drawdown_stop": 0.08,
            "hedge_ratio": 0.25,
            "portfolio_mode": "hedged_long",
        },
        "cost20": {
            "sharpe": sharpe20,
            "total_return": 1.1,
            "max_drawdown": max_dd,
            "bootstrap_30d_sharpe_p5": 0.4,
            "yearly": {
                "2021": {"net_return": 0.45},
                "2022": {"net_return": year2022},
                "2023": {"net_return": 0.08},
            },
        },
        "cost40": {
            "sharpe": sharpe40,
            "active_rebalance_event_count": 100,
            "time_in_market_frac": 0.5,
        },
    }


def write_progress(base: Path, rows: list[dict]) -> Path:
    progress = base.with_suffix(".progress.jsonl")
    meta = base.with_suffix(".progress.meta.json")
    progress.write_text("\n".join(json.dumps({"key": str(idx), "row": row}) for idx, row in enumerate(rows)))
    meta.write_text(json.dumps({"completed_rows": len(rows), "total_rows": 5}))
    return progress


def test_rescue_hit_monitor_finds_positive_hostile_year_hit(tmp_path) -> None:
    progress = write_progress(
        tmp_path / "rescue",
        [
            sample_row(sharpe20=1.6, sharpe40=1.1, year2022=0.02),
            sample_row(sharpe20=1.8, sharpe40=1.3, year2022=-0.01),
        ],
    )

    report = monitor_mod.build_report(
        progress,
        hostile_year="2022",
        min_sharpe20=1.5,
        min_year_return20=0.0,
        min_sharpe40=1.0,
        max_drawdown20=0.25,
        top_limit=5,
    )
    text = monitor_mod.format_text(report)

    assert report["completed_rows"] == 2
    assert report["total_rows"] == 5
    assert report["hit_count"] == 1
    assert report["hits"][0]["hostile_year_return20"] == 0.02
    assert report["hits"][0]["sharpe20"] == 1.6
    assert report["safety"]["paper_trading_authorized"] is False
    assert "hit_count=1" in text
    assert "safety=paper:False live:False" in text


def test_rescue_hit_monitor_writes_read_only_report_without_markers(tmp_path) -> None:
    progress = write_progress(tmp_path / "rescue", [sample_row(sharpe20=1.4, sharpe40=1.2, year2022=0.01)])
    out_json = tmp_path / "state" / "hit.json"
    out_text = tmp_path / "state" / "hit.txt"

    code = monitor_mod.main(
        [
            str(progress),
            "--out-json",
            str(out_json),
            "--out-text",
            str(out_text),
        ]
    )

    assert code == 0
    report = json.loads(out_json.read_text())
    assert report["hit_count"] == 0
    assert out_text.exists()
    assert not (tmp_path / "state" / "FOUND_PAPER_READY.txt").exists()
    assert not (tmp_path / "state" / "FOUND_VALIDATED_CANDIDATE.txt").exists()
