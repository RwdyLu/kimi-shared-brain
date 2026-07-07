from __future__ import annotations

import argparse
import itertools
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .report import write_json
from .simulator import utc_ts
from .xsec_momentum import (
    RunConfig,
    XSecConfig,
    XSecRiskConfig,
    load_close_matrix,
    one_step_neighbors,
    sharpe,
    simulate_config,
)


@dataclass(frozen=True)
class RiskProfile:
    name: str
    risk_cfg: XSecRiskConfig


def default_focus_grid(grid_set: str = "selected_neighbors") -> list[XSecConfig]:
    if grid_set == "selected_neighbors":
        full_grid = [
            XSecConfig(l, s, r, k)
            for l, s, r, k in itertools.product((72, 168, 336, 720), (0, 24), (24, 72), (1, 2))
        ]
        selected = XSecConfig(lookback_h=336, skip_h=0, rebalance_h=24, k=2)
        out = [selected]
        out.extend(one_step_neighbors(selected, full_grid))
        return out
    if grid_set == "r72_final":
        return [
            XSecConfig(l, 0, r, 2)
            for l, r in itertools.product((288, 336, 432), (48, 72, 96))
        ]
    raise ValueError(f"unknown grid set: {grid_set}")


def default_profiles(profile_set: str = "base") -> list[RiskProfile]:
    base = [
        RiskProfile("baseline", XSecRiskConfig()),
        RiskProfile("hysteresis1", XSecRiskConfig(hysteresis_buffer=1)),
        RiskProfile(
            "vol20_cap100",
            XSecRiskConfig(vol_target_ann=0.20, vol_lookback_h=720, vol_min_scale=0.25, vol_max_scale=1.0),
        ),
        RiskProfile(
            "hysteresis1_vol20_cap100",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.20,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.0,
            ),
        ),
        RiskProfile(
            "hysteresis1_vol20_cap150",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.20,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.5,
            ),
        ),
    ]
    lowvol = [
        RiskProfile(
            "hysteresis1_vol18_cap100",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.18,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.0,
            ),
        ),
        RiskProfile(
            "hysteresis1_vol16_cap100",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.16,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.0,
            ),
        ),
        RiskProfile(
            "hysteresis1_vol14_cap100",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.14,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.0,
            ),
        ),
        RiskProfile(
            "hysteresis1_vol18_cap150",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.18,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.5,
            ),
        ),
    ]
    r72final = [
        RiskProfile(
            "hysteresis1_vol14_cap100",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.14,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.0,
            ),
        ),
        RiskProfile(
            "hysteresis1_vol16_cap100",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.16,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.0,
            ),
        ),
        RiskProfile(
            "hysteresis1_vol18_cap100",
            XSecRiskConfig(
                hysteresis_buffer=1,
                vol_target_ann=0.18,
                vol_lookback_h=720,
                vol_min_scale=0.25,
                vol_max_scale=1.0,
            ),
        ),
    ]
    if profile_set == "base":
        return base
    if profile_set == "lowvol":
        return lowvol
    if profile_set == "r72final":
        return r72final
    if profile_set == "full":
        return base + lowvol
    raise ValueError(f"unknown profile set: {profile_set}")


def block_bootstrap_sharpe_p5(
    daily_return_rows: list[dict[str, Any]],
    block_days: int = 30,
    iterations: int = 1000,
    seed: int = 20260707,
) -> float:
    values = [float(row["net_return"]) for row in daily_return_rows]
    if len(values) < block_days * 2 or iterations <= 0:
        return 0.0
    rng = random.Random(seed)
    out = []
    max_start = max(1, len(values) - block_days + 1)
    for _ in range(iterations):
        sample: list[float] = []
        while len(sample) < len(values):
            start = rng.randrange(max_start)
            sample.extend(values[start : start + block_days])
        out.append(sharpe(pd.Series(sample[: len(values)]), 365.0))
    out.sort()
    idx = max(0, min(len(out) - 1, int(math.floor(0.05 * (len(out) - 1)))))
    return float(out[idx])


def profile_advance_checks(cost20: dict[str, Any], bootstrap_p5: float, neighbor_median_sharpe20: float) -> dict[str, bool]:
    return {
        "sharpe20_ge_1_2": float(cost20["sharpe"]) >= 1.2,
        "max_dd20_le_25pct": float(cost20["max_drawdown"]) <= 0.25,
        "return_2024h1_gt_minus_2pct": float(cost20["yearly"]["2024H1"]["net_return"]) > -0.02,
        "bootstrap_p5_sharpe_gt_0": bootstrap_p5 > 0.0,
        "long_leg_sharpe_ge_0_4": float(cost20["long_leg_sharpe"]) >= 0.4,
        "top_symbol_share_le_60pct": float(cost20["top_positive_symbol_share"]) <= 0.60,
        "neighbor_median_sharpe20_ge_0_8": neighbor_median_sharpe20 >= 0.8,
    }


def final_r72_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    center_profile = "hysteresis1_vol16_cap100"
    center_config = {"lookback_h": 336, "skip_h": 0, "rebalance_h": 72, "k": 2}
    center = next(
        (
            row
            for row in rows
            if row["profile"] == center_profile and row["config"] == center_config
        ),
        None,
    )
    if center is None:
        return {"evaluated": False, "accepted_train_only": False, "reason": "missing_center"}

    pass_rows = [row for row in rows if row["advance_passed"]]
    non_center_rows = [row for row in rows if row is not center]
    non_center_pass_rows = [row for row in non_center_rows if row["advance_passed"]]
    neighbor_pass_rate = len(non_center_pass_rows) / max(len(non_center_rows), 1)

    def passed(profile: str, lookback_h: int, rebalance_h: int) -> bool:
        return any(
            row["advance_passed"]
            and row["profile"] == profile
            and row["config"]["lookback_h"] == lookback_h
            and row["config"]["rebalance_h"] == rebalance_h
            for row in rows
        )

    connected_axes = {
        "lookback": passed(center_profile, 288, 72) or passed(center_profile, 432, 72),
        "rebalance": passed(center_profile, 336, 48) or passed(center_profile, 336, 96),
        "vol_target": passed("hysteresis1_vol14_cap100", 336, 72)
        or passed("hysteresis1_vol18_cap100", 336, 72),
    }
    center_cost40 = center.get("cost40")
    center_cost40_sharpe = float(center_cost40["sharpe"]) if center_cost40 else 0.0
    checks = {
        "center_passed": bool(center["advance_passed"]),
        "center_bootstrap_p5_ge_0_30": float(center["bootstrap_30d_sharpe_p5_20bps"]) >= 0.30,
        "neighbor_pass_rate_ge_60pct": neighbor_pass_rate >= 0.60,
        "connected_axes_ge_2": sum(1 for value in connected_axes.values() if value) >= 2,
        "center_40bps_sharpe_ge_1": center_cost40_sharpe >= 1.0,
    }
    return {
        "evaluated": True,
        "center_profile": center_profile,
        "center_config": center_config,
        "center_20bps": {
            "sharpe": center["cost20"]["sharpe"],
            "max_drawdown": center["cost20"]["max_drawdown"],
            "return_2024h1": center["cost20"]["yearly"]["2024H1"]["net_return"],
            "bootstrap_30d_sharpe_p5": center["bootstrap_30d_sharpe_p5_20bps"],
        },
        "center_30bps": {
            "sharpe": center["cost30"]["sharpe"],
            "max_drawdown": center["cost30"]["max_drawdown"],
        }
        if center.get("cost30")
        else None,
        "center_40bps": {
            "sharpe": center_cost40_sharpe,
            "max_drawdown": center_cost40["max_drawdown"] if center_cost40 else 0.0,
        }
        if center_cost40
        else None,
        "non_center_pass_count": len(non_center_pass_rows),
        "non_center_count": len(non_center_rows),
        "neighbor_pass_rate": neighbor_pass_rate,
        "connected_axes": connected_axes,
        "checks": checks,
        "accepted_train_only": all(checks.values()),
        "holdout_eligible_when_unlocked": all(checks.values()),
        "holdout_authorized": False,
    }


def _strip_timeseries(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"equity_curve", "daily_returns", "period_returns"}
    }


def stable_seed_offset(profile: str, cfg: XSecConfig) -> int:
    text = f"{profile}:{cfg.lookback_h}:{cfg.skip_h}:{cfg.rebalance_h}:{cfg.k}"
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(text))


def run_risk_grid(
    cfg: RunConfig,
    profile_set: str = "base",
    grid_set: str = "selected_neighbors",
    bootstrap_iterations: int = 1000,
    bootstrap_block_days: int = 30,
    bootstrap_seed: int = 20260707,
) -> dict[str, Any]:
    start = utc_ts(cfg.train_start)
    end = utc_ts(cfg.train_end)
    embargo = utc_ts(cfg.embargo_start)
    closes = load_close_matrix(Path(cfg.cache_dir), cfg.symbols, start, end, embargo)
    grid = default_focus_grid(grid_set)
    profiles = default_profiles(profile_set)
    costs = (10.0, 20.0, 30.0, 40.0) if grid_set == "r72_final" else (10.0, 20.0)
    rows = []

    for profile in profiles:
        profile_results: dict[tuple[int, int, int, int, float], dict[str, Any]] = {}
        for g in grid:
            for cost in costs:
                profile_results[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, cost)] = simulate_config(
                    closes,
                    g,
                    cost,
                    risk_cfg=profile.risk_cfg,
                    include_timeseries=True,
                )
        for g in grid:
            cost10 = profile_results[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, 10.0)]
            cost20 = profile_results[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, 20.0)]
            neighbor_sharpes20 = [
                profile_results[(n.lookback_h, n.skip_h, n.rebalance_h, n.k, 20.0)]["sharpe"]
                for n in one_step_neighbors(g, grid)
                if (n.lookback_h, n.skip_h, n.rebalance_h, n.k, 20.0) in profile_results
            ]
            neighbor_median20 = float(pd.Series(neighbor_sharpes20).median()) if neighbor_sharpes20 else 0.0
            bootstrap_p5 = block_bootstrap_sharpe_p5(
                cost20["daily_returns"],
                block_days=bootstrap_block_days,
                iterations=bootstrap_iterations,
                seed=bootstrap_seed + stable_seed_offset(profile.name, g) % 100000,
            )
            advance_checks = profile_advance_checks(cost20, bootstrap_p5, neighbor_median20)
            rows.append(
                {
                    "profile": profile.name,
                    "config": asdict(g),
                    "risk_config": asdict(profile.risk_cfg),
                    "cost10": _strip_timeseries(cost10),
                    "cost20": _strip_timeseries(cost20),
                    **(
                        {
                            "cost30": _strip_timeseries(
                                profile_results[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, 30.0)]
                            ),
                            "cost40": _strip_timeseries(
                                profile_results[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, 40.0)]
                            ),
                        }
                        if 30.0 in costs and 40.0 in costs
                        else {}
                    ),
                    "neighbor_median_sharpe20": neighbor_median20,
                    "bootstrap_30d_sharpe_p5_20bps": bootstrap_p5,
                    "advance_checks": advance_checks,
                    "advance_passed": all(advance_checks.values()),
                }
            )

    profile_summary = {}
    for profile in profiles:
        profile_rows = [row for row in rows if row["profile"] == profile.name]
        pass_rows = [row for row in profile_rows if row["advance_passed"]]
        selected_passed = any(
            row["advance_passed"]
            and row["config"] == {"lookback_h": 336, "skip_h": 0, "rebalance_h": 24, "k": 2}
            for row in profile_rows
        )
        profile_summary[profile.name] = {
            "rows": len(profile_rows),
            "advance_pass_count": len(pass_rows),
            "selected_passed": selected_passed,
            "accepted_train_only": selected_passed and len(pass_rows) >= 3,
        }

    rows.sort(
        key=lambda row: (
            bool(row["advance_passed"]),
            float(row["cost20"]["sharpe"]),
            -float(row["cost20"]["max_drawdown"]),
        ),
        reverse=True,
    )
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "cross_sectional_momentum_v1_risk_hardening_train_only_grid",
        "train_window": {"start": closes["dt"].iloc[0].isoformat(), "end": closes["dt"].iloc[-1].isoformat()},
        "symbols": list(cfg.symbols),
        "source_candidate": "artifacts/v9/contract_lab/xsec_momentum_selected_train_candidate_v1.json",
        "config": asdict(cfg),
        "profile_set": profile_set,
        "grid_set": grid_set,
        "bootstrap": {
            "block_days": bootstrap_block_days,
            "iterations": bootstrap_iterations,
            "seed": bootstrap_seed,
        },
        "summary": {
            "rows": len(rows),
            "profiles": profile_summary,
            "accepted_profiles": [
                name for name, summary in profile_summary.items() if summary["accepted_train_only"]
            ],
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        },
        "top": rows[:25],
        "rows": rows,
    }
    if profile_set == "r72final" and grid_set == "r72_final":
        payload["summary"]["final_r72"] = final_r72_summary(rows)
    write_json(payload, Path(cfg.out_json))
    if cfg.out_md:
        write_markdown(payload, Path(cfg.out_md))
    return payload


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Cross-Sectional Momentum Risk Hardening v1",
        "",
        f"created_at: `{payload['created_at']}`",
        f"train_window: `{payload['train_window']['start']}` to `{payload['train_window']['end']}`",
        "",
        "This is train-only research. It does not authorize holdout, paper trading, or live trading.",
        "",
        "## Summary",
        "",
    ]
    for profile, summary in payload["summary"]["profiles"].items():
        lines.append(
            f"- `{profile}`: pass `{summary['advance_pass_count']}/{summary['rows']}`, "
            f"selected_passed `{summary['selected_passed']}`, accepted_train_only `{summary['accepted_train_only']}`"
        )
    lines.extend(
        [
            "",
            "## Top Rows",
            "",
            "| profile | cfg | pass | 20bps sharpe | 20bps DD | 2024H1 | boot p5 | turn/day | avg gross | top sym | long sh | neigh sh |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if payload["summary"].get("final_r72"):
        final = payload["summary"]["final_r72"]
        lines.extend(
            [
                "",
                "## Final R72 Rule",
                "",
                f"- accepted_train_only: `{final['accepted_train_only']}`",
                f"- neighbor_pass_rate: `{final['neighbor_pass_rate']:.3f}`",
                f"- connected_axes: `{final['connected_axes']}`",
                f"- center_40bps: `{final['center_40bps']}`",
                f"- holdout_authorized: `{final['holdout_authorized']}`",
            ]
        )
    for row in payload["top"]:
        cfg = row["config"]
        c20 = row["cost20"]
        label = f"L{cfg['lookback_h']}_S{cfg['skip_h']}_R{cfg['rebalance_h']}_K{cfg['k']}"
        lines.append(
            "| `{profile}` | `{label}` | `{passed}` | {sh:.3f} | {dd:.3f} | {ret2024:.3f} | {boot:.3f} | {turn:.3f} | {gross:.3f} | {top:.3f} | {longsh:.3f} | {neigh:.3f} |".format(
                profile=row["profile"],
                label=label,
                passed=row["advance_passed"],
                sh=c20["sharpe"],
                dd=c20["max_drawdown"],
                ret2024=c20["yearly"]["2024H1"]["net_return"],
                boot=row["bootstrap_30d_sharpe_p5_20bps"],
                turn=c20["daily_turnover"],
                gross=c20["avg_gross_exposure"],
                top=c20["top_positive_symbol_share"],
                longsh=c20["long_leg_sharpe"],
                neigh=row["neighbor_median_sharpe20"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Train-only xsec momentum risk-hardening diagnostic")
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--bootstrap-iterations", type=int, default=1000)
    ap.add_argument("--bootstrap-block-days", type=int, default=30)
    ap.add_argument("--bootstrap-seed", type=int, default=20260707)
    ap.add_argument("--profile-set", choices=("base", "lowvol", "r72final", "full"), default="base")
    ap.add_argument("--grid-set", choices=("selected_neighbors", "r72_final"), default="selected_neighbors")
    ap.add_argument("--out-json", default="artifacts/v9/contract_lab/xsec_momentum_risk_hardening_v1.json")
    ap.add_argument("--out-md", default="artifacts/v9/contract_lab/xsec_momentum_risk_hardening_v1.md")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    cfg = RunConfig(
        cache_dir=args.cache_dir,
        train_start=args.train_start,
        train_end=args.train_end,
        embargo_start=args.embargo_start,
        out_json=args.out_json,
        out_md=args.out_md,
    )
    started = time.time()
    payload = run_risk_grid(
        cfg,
        profile_set=args.profile_set,
        grid_set=args.grid_set,
        bootstrap_iterations=args.bootstrap_iterations,
        bootstrap_block_days=args.bootstrap_block_days,
        bootstrap_seed=args.bootstrap_seed,
    )
    print(
        "xsec_momentum_risk_hardening_v1 done "
        f"rows={payload['summary']['rows']} "
        f"accepted_profiles={payload['summary']['accepted_profiles']} "
        f"elapsed_sec={time.time() - started:.2f}"
    )
    print(args.out_json)
    print(args.out_md)


if __name__ == "__main__":
    main()
