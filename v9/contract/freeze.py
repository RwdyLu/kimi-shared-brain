from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .report import write_json
from .schema import ContractCandidate
from .simulator import attach_regimes, load_regime_labels, load_symbol_1h, simulate_candidate, utc_ts


@dataclass(frozen=True)
class FreezeConfig:
    min_trades: int = 150
    min_cost_retention: float = 0.50
    min_fold_share: float = 0.10
    max_top5_profit_share: float = 0.40
    max_non_up_normal_loss_frac: float = 0.10
    max_single_regime_loss_frac: float = 0.15
    min_cvar5_r: float = -1.20
    max_underwater_days: int = 730
    corr_threshold: float = 0.60
    jaccard_threshold: float = 0.50
    max_selected: int = 3
    bootstrap_iterations: int = 2000
    bootstrap_block: int = 10
    bootstrap_seed: int = 20260706
    min_search_samples_for_freeze: int = 300


def to_ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC") if ts.tzinfo else pd.Timestamp(value, tz="UTC")


def cvar(values: list[float], frac: float = 0.05) -> float:
    xs = sorted(v for v in values if math.isfinite(v))
    if not xs:
        return 0.0
    n = max(1, int(math.ceil(len(xs) * frac)))
    return float(sum(xs[:n]) / n)


def longest_loss_streak(values: list[float]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def max_underwater_days(equity_curve: list[dict[str, Any]]) -> int:
    if not equity_curve:
        return 0
    points = [(to_ts(row["dt"]), float(row["equity"])) for row in equity_curve]
    points.sort(key=lambda x: x[0])
    peak = points[0][1]
    underwater_start: pd.Timestamp | None = None
    worst = 0
    for ts, equity in points:
        if equity >= peak:
            peak = equity
            if underwater_start is not None:
                worst = max(worst, int((ts - underwater_start).days))
                underwater_start = None
        elif underwater_start is None:
            underwater_start = ts
    if underwater_start is not None:
        worst = max(worst, int((points[-1][0] - underwater_start).days))
    return worst


def bootstrap_net_pnl_p5(
    trades: list[dict[str, Any]],
    iterations: int = 2000,
    block: int = 10,
    seed: int = 20260706,
) -> float:
    pnls = [float(t["net_pnl"]) for t in sorted(trades, key=lambda t: str(t["entry_time"]))]
    if not pnls:
        return 0.0
    rng = random.Random(seed)
    n = len(pnls)
    block = max(1, min(block, n))
    totals: list[float] = []
    for _ in range(iterations):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randrange(0, n - block + 1)
            sample.extend(pnls[start : start + block])
        totals.append(float(sum(sample[:n])))
    totals.sort()
    pos = int(math.floor(0.05 * (len(totals) - 1)))
    return float(totals[pos])


def daily_realized_returns(
    trades: list[dict[str, Any]],
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    initial_equity: float,
) -> pd.Series:
    idx = pd.date_range(train_start.floor("D"), train_end.floor("D"), freq="1D", tz="UTC")
    values = pd.Series(0.0, index=idx)
    if initial_equity <= 0:
        return values
    for trade in trades:
        day = to_ts(trade["exit_time"]).floor("D")
        if day in values.index:
            values.loc[day] += float(trade["net_pnl"]) / initial_equity
    return values


def in_market_days(trades: list[dict[str, Any]]) -> set[str]:
    days: set[str] = set()
    for trade in trades:
        start = to_ts(trade["entry_time"]).floor("D")
        end = to_ts(trade["exit_time"]).floor("D")
        for day in pd.date_range(start, end, freq="1D", tz="UTC"):
            days.add(day.strftime("%Y-%m-%d"))
    return days


def pearson_corr(left: pd.Series, right: pd.Series) -> float:
    merged = pd.concat([left, right], axis=1).fillna(0.0)
    a = merged.iloc[:, 0]
    b = merged.iloc[:, 1]
    a_std = float(a.std())
    b_std = float(b.std())
    if a_std == 0.0 and b_std == 0.0:
        return 1.0 if a.equals(b) else 0.0
    if a_std == 0.0 or b_std == 0.0:
        return 0.0
    value = a.corr(b)
    return 0.0 if value is None or not math.isfinite(float(value)) else float(value)


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return float(len(left & right) / len(union))


def profit_factor(pnls: list[float]) -> float | None:
    gains = sum(x for x in pnls if x > 0)
    losses = -sum(x for x in pnls if x < 0)
    if losses == 0:
        return None if gains == 0 else float("inf")
    return float(gains / losses)


def trade_stats(trades: list[dict[str, Any]], equity_curve: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [float(t["net_pnl"]) for t in trades]
    rs = [float(t["r_multiple"]) for t in trades]
    positive = sorted((p for p in pnls if p > 0), reverse=True)
    total = sum(pnls)
    by_regime: dict[str, dict[str, Any]] = {}
    by_exit: dict[str, dict[str, Any]] = {}
    for trade in trades:
        for key_name, out in [("entry_regime", by_regime), ("exit_reason", by_exit)]:
            key = str(trade.get(key_name, "unknown"))
            row = out.setdefault(key, {"trades": 0, "net_pnl": 0.0, "r_sum": 0.0})
            row["trades"] += 1
            row["net_pnl"] += float(trade["net_pnl"])
            row["r_sum"] += float(trade["r_multiple"])
    for out in [by_regime, by_exit]:
        for row in out.values():
            row["avg_r"] = row["r_sum"] / row["trades"] if row["trades"] else 0.0
            del row["r_sum"]
    return {
        "trades": len(trades),
        "net_pnl": float(total),
        "mean_r": float(sum(rs) / len(rs)) if rs else 0.0,
        "median_r": float(pd.Series(rs).median()) if rs else 0.0,
        "std_r": float(pd.Series(rs).std(ddof=1)) if len(rs) > 1 else 0.0,
        "skew_r": float(pd.Series(rs).skew()) if len(rs) > 2 else 0.0,
        "win_rate": float(sum(1 for p in pnls if p > 0) / len(pnls)) if pnls else 0.0,
        "profit_factor": profit_factor(pnls),
        "cvar5_r": cvar(rs, 0.05),
        "longest_loss_streak": longest_loss_streak(pnls),
        "top5_profit_share": float(sum(positive[:5]) / total) if total > 0 else float("inf"),
        "max_underwater_days": max_underwater_days(equity_curve),
        "by_regime": by_regime,
        "by_exit_reason": by_exit,
    }


def fold_share(summary: dict[str, Any]) -> float:
    total = float(summary.get("net_pnl", 0.0))
    folds = summary.get("folds", [])
    if total <= 0 or not folds:
        return -1.0
    return float(min(float(f["net_pnl"]) for f in folds) / total)


def integrity_checks(trades: list[dict[str, Any]], train_end: pd.Timestamp, base_net: float, cost2_net: float) -> dict[str, bool]:
    signal_before_entry = all(to_ts(t["entry_time"]) > to_ts(t["signal_time"]) for t in trades)
    cutoff_ok = all(to_ts(t["exit_time"]) <= train_end and to_ts(t["entry_time"]) <= train_end for t in trades)
    cost_order_ok = cost2_net <= base_net + 1e-9
    return {
        "signal_before_entry": signal_before_entry,
        "cutoff_ok": cutoff_ok,
        "cost2_lte_base": cost_order_ok,
    }


def freeze_gate(
    base: dict[str, Any],
    cost2: dict[str, Any],
    cost3: dict[str, Any],
    cost2_stats: dict[str, Any],
    bootstrap_p5: float,
    train_end: pd.Timestamp,
    cfg: FreezeConfig,
) -> dict[str, Any]:
    base_net = float(base["net_pnl"])
    cost2_net = float(cost2["net_pnl"])
    retention = cost2_net / base_net if base_net > 0 else -1.0
    min_fold_share = fold_share(cost2)
    by_regime = cost2_stats["by_regime"]
    non_up_normal = sum(float(v["net_pnl"]) for k, v in by_regime.items() if k != "up_normal")
    worst_regime = min((float(v["net_pnl"]) for v in by_regime.values()), default=0.0)
    integrity = integrity_checks(cost2.get("trades", []), train_end, base_net, cost2_net)
    checks = {
        "min_trades": int(cost2["trade_count"]) >= cfg.min_trades,
        "cost2_net_positive": cost2_net > 0,
        "cost_retention": retention >= cfg.min_cost_retention,
        "folds_all_positive": all(float(f["net_pnl"]) > 0 for f in cost2.get("folds", [])),
        "min_fold_share": min_fold_share >= cfg.min_fold_share,
        "bootstrap_p5_positive": bootstrap_p5 > 0,
        "top5_profit_share": float(cost2_stats["top5_profit_share"]) <= cfg.max_top5_profit_share,
        "non_up_normal_loss": non_up_normal >= -cost2_net * cfg.max_non_up_normal_loss_frac,
        "single_regime_loss": worst_regime >= -cost2_net * cfg.max_single_regime_loss_frac,
        "cvar5_r": float(cost2_stats["cvar5_r"]) >= cfg.min_cvar5_r,
        "max_underwater_days": int(cost2_stats["max_underwater_days"]) <= cfg.max_underwater_days,
        **integrity,
    }
    failures = [k for k, passed in checks.items() if not passed]
    return {
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "derived": {
            "cost_retention": float(retention),
            "min_fold_share": float(min_fold_share),
            "non_up_normal_pnl": float(non_up_normal),
            "worst_regime_pnl": float(worst_regime),
            "bootstrap_cost2_net_pnl_p5": float(bootstrap_p5),
            "cost3_net_pnl": float(cost3["net_pnl"]),
        },
    }


def pairwise_matrix(rows: list[dict[str, Any]], cfg: FreezeConfig) -> list[dict[str, Any]]:
    pairs = []
    for i, left in enumerate(rows):
        for right in rows[i + 1 :]:
            corr = pearson_corr(left["daily_returns"], right["daily_returns"])
            overlap = jaccard(left["in_market_days"], right["in_market_days"])
            pairs.append(
                {
                    "left": left["candidate_id"],
                    "right": right["candidate_id"],
                    "daily_return_corr": corr,
                    "in_market_jaccard": overlap,
                    "decorrelated": corr < cfg.corr_threshold and overlap < cfg.jaccard_threshold,
                }
            )
    return pairs


def select_candidates(rows: list[dict[str, Any]], pairs: list[dict[str, Any]], cfg: FreezeConfig) -> list[str]:
    pair_lookup = {(p["left"], p["right"]): p for p in pairs}
    pair_lookup.update({(p["right"], p["left"]): p for p in pairs})
    eligible = [r for r in rows if r["freeze_gate"]["passed"]]
    eligible.sort(
        key=lambda r: (
            float(r["freeze_gate"]["derived"]["bootstrap_cost2_net_pnl_p5"]),
            float(r["freeze_gate"]["derived"]["min_fold_share"]),
            -float(r["base"]["exposure_bar_ratio"]),
        ),
        reverse=True,
    )
    selected: list[str] = []
    for row in eligible:
        cid = row["candidate_id"]
        if all(pair_lookup.get((cid, prev), {"decorrelated": True})["decorrelated"] for prev in selected):
            selected.append(cid)
            if len(selected) >= cfg.max_selected:
                break
    return selected


def strip_heavy(row: dict[str, Any]) -> dict[str, Any]:
    clean = dict(row)
    clean.pop("daily_returns", None)
    clean.pop("in_market_days", None)
    for key in ["base", "cost2", "cost3"]:
        if key in clean:
            clean[key] = {k: v for k, v in clean[key].items() if k not in {"trades", "equity_curve"}}
    return clean


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Contract Candidate Freeze Audit v9",
        "",
        f"created_at: `{payload['created_at']}`",
        f"search_input: `{payload['search_input']}`",
        f"train_window: `{payload['train_window']['start']}` to `{payload['train_window']['end']}`",
        f"candidate_count: `{payload['summary']['candidate_count']}`",
        f"freeze_gate_passed: `{payload['summary']['freeze_gate_passed']}`",
        f"selected_preview: `{', '.join(payload['selection']['selected_preview']) or 'none'}`",
        f"family_frozen: `{payload['selection']['family_frozen']}`",
        f"freeze_block_reason: `{payload['selection']['freeze_block_reason']}`",
        "",
        "This is train-only research. It does not authorize holdout, paper trading, or live trading.",
        "",
        "## Candidates",
        "",
        "| id | gate | p5 2x pnl | 2x pnl | 3x pnl | retention | min fold | top5 share | underwater days | failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["candidates"]:
        gate = row["freeze_gate"]
        derived = gate["derived"]
        stats = row["cost2_stats"]
        failures = ",".join(gate["failures"]) if gate["failures"] else "none"
        lines.append(
            "| {cid} | `{passed}` | {p5:.2f} | {net2:.2f} | {net3:.2f} | {ret:.3f} | {fold:.3f} | {top5:.3f} | {uw} | {failures} |".format(
                cid=row["candidate_id"],
                passed=gate["passed"],
                p5=derived["bootstrap_cost2_net_pnl_p5"],
                net2=row["cost2"]["net_pnl"],
                net3=derived["cost3_net_pnl"],
                ret=derived["cost_retention"],
                fold=derived["min_fold_share"],
                top5=stats["top5_profit_share"],
                uw=stats["max_underwater_days"],
                failures=failures,
            )
        )
    lines.extend(["", "## Pairwise Decorrelation", "", "| left | right | corr | jaccard | decorrelated |", "|---|---|---:|---:|---:|"])
    for pair in payload["pairwise"]:
        lines.append(
            f"| {pair['left']} | {pair['right']} | {pair['daily_return_corr']:.3f} | {pair['in_market_jaccard']:.3f} | `{pair['decorrelated']}` |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def run_freeze_audit(args: argparse.Namespace) -> dict[str, Any]:
    cfg = FreezeConfig(
        bootstrap_iterations=args.bootstrap_iterations,
        min_search_samples_for_freeze=args.min_search_samples_for_freeze,
    )
    search_path = Path(args.search)
    search = json.loads(search_path.read_text())
    symbol = str(search["symbol"]).upper()
    train_start = utc_ts(search["train_window"]["start"])
    train_end = utc_ts(search["train_window"]["end"])
    embargo_start = utc_ts(search["embargo_start"])
    bars = load_symbol_1h(Path(args.cache_dir), symbol, train_start, train_end, embargo_start)
    labels = load_regime_labels(Path(args.regime_labels_dir) / f"regime_labels_{symbol}.parquet", embargo_start)
    bars = attach_regimes(bars, labels)

    source_rows = [r for r in search["candidates"] if r.get("gates", {}).get("passed")]
    if args.limit:
        source_rows = source_rows[: args.limit]
    candidate_rows: list[dict[str, Any]] = []
    for source in source_rows:
        candidate = ContractCandidate.from_dict(source["candidate"])
        base = simulate_candidate(bars, candidate, cost_multiplier=1.0, include_trades=True)
        cost2 = simulate_candidate(bars, candidate, cost_multiplier=2.0, include_trades=True)
        cost3 = simulate_candidate(bars, candidate, cost_multiplier=3.0, include_trades=True)
        cost2_stats = trade_stats(cost2["trades"], cost2["equity_curve"])
        bootstrap_p5 = bootstrap_net_pnl_p5(
            cost2["trades"],
            iterations=cfg.bootstrap_iterations,
            block=cfg.bootstrap_block,
            seed=cfg.bootstrap_seed,
        )
        gate = freeze_gate(base, cost2, cost3, cost2_stats, bootstrap_p5, train_end, cfg)
        candidate_rows.append(
            {
                "candidate_id": candidate.candidate_id(),
                "candidate": candidate.to_dict(),
                "base": base,
                "cost2": cost2,
                "cost3": cost3,
                "cost2_stats": cost2_stats,
                "freeze_gate": gate,
                "daily_returns": daily_realized_returns(cost2["trades"], train_start, train_end, candidate.initial_equity),
                "in_market_days": in_market_days(cost2["trades"]),
            }
        )

    pairs = pairwise_matrix(candidate_rows, cfg)
    selected_preview = select_candidates(candidate_rows, pairs, cfg)
    sampled = int(search.get("summary", {}).get("sampled", 0))
    family_frozen = bool(selected_preview and sampled >= cfg.min_search_samples_for_freeze)
    freeze_block_reason = "none" if family_frozen else (
        f"search_samples_lt_{cfg.min_search_samples_for_freeze}" if selected_preview else "no_decorrelated_gate_pass_candidates"
    )
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "contract_candidate_freeze_audit_v9_train_only",
        "search_input": str(search_path),
        "train_window": search["train_window"],
        "embargo_start": search["embargo_start"],
        "config": cfg.__dict__,
        "summary": {
            "candidate_count": len(candidate_rows),
            "freeze_gate_passed": sum(1 for r in candidate_rows if r["freeze_gate"]["passed"]),
            "source_search_sampled": sampled,
            "failure_counts": dict(Counter(f for r in candidate_rows for f in r["freeze_gate"]["failures"])),
        },
        "selection": {
            "selected_preview": selected_preview,
            "family_frozen": family_frozen,
            "freeze_block_reason": freeze_block_reason,
        },
        "pairwise": pairs,
        "candidates": [strip_heavy(r) for r in candidate_rows],
    }
    write_json(payload, Path(args.out))
    if args.md:
        write_markdown(payload, Path(args.md))
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Train-only freeze/decorrelation audit for v9 contract candidates")
    ap.add_argument("--search", required=True)
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--regime-labels-dir", default="artifacts/v9")
    ap.add_argument("--out", default="artifacts/v9/contract_lab/contract_freeze_audit.json")
    ap.add_argument("--md", default="artifacts/v9/contract_lab/contract_freeze_audit.md")
    ap.add_argument("--bootstrap-iterations", type=int, default=2000)
    ap.add_argument("--min-search-samples-for-freeze", type=int, default=300)
    ap.add_argument("--limit", type=int, default=0)
    return ap


def main() -> None:
    payload = run_freeze_audit(build_arg_parser().parse_args())
    print(
        "contract_freeze_audit_v9 done "
        f"candidates={payload['summary']['candidate_count']} "
        f"gate_passed={payload['summary']['freeze_gate_passed']} "
        f"selected_preview={len(payload['selection']['selected_preview'])} "
        f"family_frozen={payload['selection']['family_frozen']}"
    )
    print(payload["selection"]["freeze_block_reason"])


if __name__ == "__main__":
    main()
