#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any


DEFAULT_GRID_VERSIONS = {
    "hq_active_recent_hedged_v1": "4cd1599",
    "hq_fast_breakout_hedged_v1": "65f092f",
}


def active_recent_hedged_v1_configs() -> list[dict[str, Any]]:
    base = {
        "skip_h": 0,
        "n_tranches": 1,
        "drawdown_stop": 0.08,
        "cooldown_h": 72,
        "market_confirm_h": 0,
        "market_drawdown_limit": 0.0,
        "portfolio_mode": "hedged_long",
    }
    configs = []
    for (
        lookback_h,
        rebalance_h,
        k,
        score_mode,
        market_filter_h,
        vol_target_ann,
        hedge_ratio,
    ) in itertools.product(
        [168, 240, 336, 504],
        [48, 72],
        [2, 3],
        ["risk_adj_mom", "vol_breakout"],
        [0, 168, 336],
        [0.04, 0.06],
        [0.25, 0.40],
    ):
        row = dict(base)
        row.update(
            {
                "lookback_h": lookback_h,
                "rebalance_h": rebalance_h,
                "k": k,
                "score_mode": score_mode,
                "market_filter_h": market_filter_h,
                "vol_target_ann": vol_target_ann,
                "hedge_ratio": hedge_ratio,
            }
        )
        configs.append(row)
    return configs


def fast_breakout_hedged_v1_configs() -> list[dict[str, Any]]:
    base = {
        "skip_h": 0,
        "n_tranches": 1,
        "portfolio_mode": "hedged_long",
        "hedge_ratio": 0.25,
        "market_drawdown_limit": 0.25,
    }
    configs = []
    for (
        lookback_h,
        rebalance_h,
        k,
        score_mode,
        market_filter_h,
        vol_target_ann,
        drawdown_stop,
        cooldown_h,
        market_confirm_h,
    ) in itertools.product(
        [72, 120, 168, 240],
        [24, 48],
        [2, 3],
        ["breakout", "vol_breakout"],
        [0, 72, 168],
        [0.03, 0.04],
        [0.05, 0.08],
        [24, 72],
        [0, 24],
    ):
        row = dict(base)
        row.update(
            {
                "lookback_h": lookback_h,
                "rebalance_h": rebalance_h,
                "k": k,
                "score_mode": score_mode,
                "market_filter_h": market_filter_h,
                "vol_target_ann": vol_target_ann,
                "drawdown_stop": drawdown_stop,
                "cooldown_h": cooldown_h,
                "market_confirm_h": market_confirm_h,
                "market_drawdown_limit": 0.0
                if market_filter_h == 0 and market_confirm_h == 0
                else 0.25,
            }
        )
        configs.append(row)

    priority = []
    for row in configs:
        score = 0
        score += 2 if row["rebalance_h"] == 48 else 0
        score += 2 if row["score_mode"] == "vol_breakout" else 1
        score += 2 if row["market_filter_h"] in (0, 72) else 0
        score += 1 if row["market_confirm_h"] == 0 else 0
        score += 1 if row["drawdown_stop"] == 0.08 else 0
        priority.append((score, row))
    priority.sort(
        key=lambda item: (
            -item[0],
            item[1]["lookback_h"],
            item[1]["rebalance_h"],
            item[1]["k"],
            item[1]["score_mode"],
            item[1]["market_filter_h"],
            item[1]["vol_target_ann"],
            item[1]["drawdown_stop"],
            item[1]["cooldown_h"],
            item[1]["market_confirm_h"],
        )
    )
    return [row for _, row in priority[:384]]


def grid_payload(grid: str) -> dict[str, Any]:
    if grid == "hq_active_recent_hedged_v1":
        return {
            "description": (
                "active-recent hedged-long explicit grid after hq_hedged_long v10 "
                "holdout failed due recent inactivity; uses hq_active_recent gates, "
                "no gate relaxation"
            ),
            "configs": active_recent_hedged_v1_configs(),
        }
    if grid == "hq_fast_breakout_hedged_v1":
        return {
            "description": (
                "fast breakout hedged-long active-recent grid; optimized for current "
                "activity and holdout/paper gate, not train-only Sharpe"
            ),
            "configs": fast_breakout_hedged_v1_configs(),
        }
    raise ValueError(f"unknown grid: {grid}")


def grid_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def grid_fingerprint(grid: str, payload: dict[str, Any], evaluation_version: str) -> str:
    salt = f"{grid}_202406_{evaluation_version}_"
    return hashlib.sha1((salt + grid_text(payload)).encode()).hexdigest()


def write_grid(grid: str, out_dir: Path, evaluation_version: str | None = None) -> dict[str, Any]:
    version = evaluation_version or DEFAULT_GRID_VERSIONS[grid]
    payload = grid_payload(grid)
    fingerprint = grid_fingerprint(grid, payload, version)
    short = fingerprint[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{grid}_{short}.json"
    path.write_text(grid_text(payload) + "\n")
    return {
        "grid": grid,
        "evaluation_version": version,
        "fingerprint": fingerprint,
        "short": short,
        "config_count": len(payload["configs"]),
        "path": str(path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate reproducible v9 xsec active research config grids.")
    parser.add_argument(
        "--grid",
        choices=sorted(DEFAULT_GRID_VERSIONS),
        required=True,
        help="Grid name to generate.",
    )
    parser.add_argument(
        "--out-dir",
        default="artifacts/v9/configs",
        help="Directory for the generated config JSON.",
    )
    parser.add_argument(
        "--evaluation-version",
        default=None,
        help="Override the version salt used in the grid fingerprint.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = write_grid(
        grid=args.grid,
        out_dir=Path(args.out_dir),
        evaluation_version=args.evaluation_version,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
