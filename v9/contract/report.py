from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload["summary"]
    lines = [
        "# Contract Lab v9 Train-Only Search",
        "",
        f"created_at: `{payload['created_at']}`",
        f"symbol: `{payload['symbol']}`",
        f"train_window: `{payload['train_window']['start']}` to `{payload['train_window']['end']}`",
        f"embargo_start: `{payload['embargo_start']}`",
        f"ranking_mode: `{payload.get('config', {}).get('ranking_mode', 'train_gate')}`",
        f"sampling_profile: `{payload.get('config', {}).get('sampling_profile', 'standard')}`",
        "",
        "## Summary",
        "",
        f"- sampled: `{summary['sampled']}`",
        f"- attempts: `{summary.get('attempts')}`",
        f"- accepted_rate: `{summary.get('accepted_rate')}`",
        f"- gate_passed: `{summary['gate_passed']}`",
        f"- best_score: `{summary['best_score']}`",
        f"- best_ranking_score: `{summary.get('best_ranking_score')}`",
        f"- best_candidate_id: `{summary['best_candidate_id']}`",
        "",
        "This is train-only research. It does not authorize holdout, paper trading, or live trading.",
        "",
        "## Top Candidates",
        "",
        "| rank | id | passed | rank score | gate score | signals | trades | net pnl | 2x net pnl | win | avg R | CVaR5 R | DD | proxy | failures |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for idx, row in enumerate(payload["top"], start=1):
        base = row["base"]
        cost2 = row["cost2"]
        gates = row["gates"]
        failures = ",".join(gates["failures"]) if gates["failures"] else "none"
        signals = row.get("signal_prescreen", {}).get("signal_count", "na")
        proxy = row.get("freeze_proxy")
        proxy_text = "none"
        if proxy:
            proxy_text = "uw={uw};top5={top5:.2f};fold={fold:.2f};p5={p5:.0f}".format(
                uw=proxy["max_underwater_days"],
                top5=proxy["top5_profit_share"],
                fold=proxy["min_fold_share"],
                p5=proxy["p5_proxy_net_pnl"],
            )
        lines.append(
            "| {rank} | `{cid}` | `{passed}` | {rank_score:.4f} | {score:.4f} | {signals} | {trades} | {net:.2f} | {net2:.2f} | {win:.3f} | {avgr:.3f} | {cvar:.3f} | {dd:.3f} | {proxy} | {failures} |".format(
                rank=idx,
                cid=row["candidate_id"],
                passed=gates["passed"],
                rank_score=row.get("ranking_score", gates["score"]),
                score=gates["score"],
                signals=signals,
                trades=base["trade_count"],
                net=base["net_pnl"],
                net2=cost2["net_pnl"],
                win=base["win_rate"],
                avgr=base["avg_r"],
                cvar=base["cvar5_r"],
                dd=base["max_drawdown"],
                proxy=proxy_text,
                failures=failures,
            )
        )
    lines.extend(
        [
            "",
            "## Gate Counts",
            "",
            "| gate | failures |",
            "|---|---:|",
        ]
    )
    for gate, count in sorted(summary["failure_counts"].items()):
        lines.append(f"| {gate} | {count} |")
    if summary.get("rejection_counts"):
        lines.extend(
            [
                "",
                "## Rejection Counts",
                "",
                "| reason | count |",
                "|---|---:|",
            ]
        )
        for reason, count in sorted(summary["rejection_counts"].items()):
            lines.append(f"| {reason} | {count} |")
    lines.append("")
    path.write_text("\n".join(lines))
