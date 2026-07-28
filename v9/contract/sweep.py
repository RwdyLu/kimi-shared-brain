from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from .metrics import GateConfig, evaluate_gates
from .report import write_json, write_markdown
from .schema import ContractCandidate
from .search import SearchConfig, compact_result, freeze_proxy_metrics, signal_prescreen, sort_rows
from .simulator import attach_regimes, load_regime_labels, load_symbol_1h, simulate_candidate, utc_ts


def load_source_candidate(search_path: Path, candidate_id: str) -> tuple[dict[str, Any], ContractCandidate]:
    search = json.loads(search_path.read_text())
    for row in search.get("candidates", []):
        if row.get("candidate_id") == candidate_id:
            return search, ContractCandidate.from_dict(row["candidate"])
    raise SystemExit(f"candidate_id {candidate_id} not found in {search_path}")


def hold_sweep_values(base_hold: int, multipliers: list[float]) -> list[int]:
    values: list[int] = []
    for mult in multipliers:
        hold = max(1, int(round(base_hold * float(mult))))
        if hold not in values:
            values.append(hold)
    return values


def build_regime_hold_variants(
    base: ContractCandidate,
    strict_drawdown_cap: float = 0.25,
    hold_multipliers: list[float] | None = None,
) -> list[dict[str, Any]]:
    holds = hold_sweep_values(base.max_hold_bars, hold_multipliers or [1.0, 0.75, 0.5])
    tiers = [
        ("baseline_regime", None),
        (f"drawdown_1y_le_{strict_drawdown_cap:.2f}", strict_drawdown_cap),
    ]
    variants = []
    for tier_name, drawdown_cap in tiers:
        for hold in holds:
            candidate = replace(
                base,
                max_hold_bars=hold,
                max_regime_drawdown_1y=drawdown_cap,
            )
            variants.append(
                {
                    "variant": {
                        "regime_tier": tier_name,
                        "max_hold_bars": hold,
                        "max_regime_drawdown_1y": drawdown_cap,
                    },
                    "candidate": candidate,
                }
            )
    return variants


def run_regime_hold_sweep(args: argparse.Namespace) -> dict[str, Any]:
    source_search, base_candidate = load_source_candidate(Path(args.source_search), args.candidate_id)
    symbol = base_candidate.symbol
    train_start = utc_ts(source_search["train_window"]["start"])
    train_end = utc_ts(source_search["train_window"]["end"])
    embargo_start = utc_ts(source_search["embargo_start"])
    cfg = SearchConfig(
        symbol=symbol,
        samples=0,
        train_start=train_start.isoformat(),
        train_end=train_end.isoformat(),
        embargo_start=embargo_start.isoformat(),
        cache_dir=args.cache_dir,
        regime_labels_dir=args.regime_labels_dir,
        out_json=args.out_json,
        out_md=args.out_md,
        ranking_mode=args.ranking_mode,
        proxy_bootstrap_iterations=args.proxy_bootstrap_iterations,
        sampling_profile=args.prescreen_profile,
        min_signals_train=args.min_signals_train,
        min_signals_per_fold=args.min_signals_per_fold,
        max_signals_train=args.max_signals_train,
    )
    bars = load_symbol_1h(Path(cfg.cache_dir), symbol, train_start, train_end, embargo_start)
    labels = load_regime_labels(Path(cfg.regime_labels_dir) / f"regime_labels_{symbol}.parquet", embargo_start)
    bars = attach_regimes(bars, labels)

    rows = []
    rejections: Counter[str] = Counter()
    variants = build_regime_hold_variants(base_candidate, args.strict_drawdown_cap, args.hold_multipliers)
    for variant in variants:
        candidate: ContractCandidate = variant["candidate"]
        prescreen, prescreen_reject = signal_prescreen(bars, candidate, cfg)
        if prescreen_reject:
            rejections[prescreen_reject] += 1
            continue
        keep_trades = cfg.ranking_mode == "freeze_proxy"
        base = simulate_candidate(bars, candidate, cost_multiplier=1.0, include_trades=keep_trades)
        cost2 = simulate_candidate(bars, candidate, cost_multiplier=2.0, include_trades=keep_trades)
        gates = evaluate_gates(base, cost2, GateConfig())
        ranking_score = float(gates["score"])
        freeze_proxy = None
        if cfg.ranking_mode == "freeze_proxy":
            freeze_proxy = freeze_proxy_metrics(base, cost2, ranking_score, bootstrap_iterations=cfg.proxy_bootstrap_iterations)
            ranking_score = float(freeze_proxy["score"])
        rows.append(
            {
                "candidate_id": candidate.candidate_id(),
                "candidate": candidate.to_dict(),
                "variant": variant["variant"],
                "base": compact_result(base),
                "cost2": compact_result(cost2),
                "gates": gates,
                "ranking_score": ranking_score,
                "freeze_proxy": freeze_proxy,
                "signal_prescreen": prescreen,
            }
        )

    sort_rows(rows, cfg.ranking_mode)
    failure_counts = Counter()
    for row in rows:
        failure_counts.update(row["gates"]["failures"])
    best = rows[0] if rows else None
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "contract_lab_v9_regime_hold_sweep_train_only",
        "symbol": symbol,
        "train_window": {"start": train_start.isoformat(), "end": train_end.isoformat()},
        "embargo_start": embargo_start.isoformat(),
        "source_search": args.source_search,
        "source_candidate_id": args.candidate_id,
        "config": cfg.__dict__
        | {
            "strict_drawdown_cap": args.strict_drawdown_cap,
            "hold_multipliers": args.hold_multipliers,
            "variant_count": len(variants),
        },
        "summary": {
            "sampled": len(rows),
            "attempts": len(variants),
            "accepted_rate": (len(rows) / len(variants)) if variants else 0.0,
            "gate_passed": sum(1 for r in rows if r["gates"]["passed"]),
            "best_score": best["gates"]["score"] if best else None,
            "best_ranking_score": best["ranking_score"] if best else None,
            "best_candidate_id": best["candidate_id"] if best else None,
            "failure_counts": dict(failure_counts),
            "rejection_counts": dict(rejections),
        },
        "top": rows[:25],
        "candidates": rows,
    }
    write_json(payload, Path(args.out_json))
    write_markdown(payload, Path(args.out_md))
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run a fixed regime/hold sweep around a frozen v9 contract candidate")
    ap.add_argument("--source-search", default="artifacts/v9/contract_lab/contract_search_LINKUSDT_freezebalanced_sample64.json")
    ap.add_argument("--candidate-id", default="bf7919c368e63524")
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--regime-labels-dir", default="artifacts/v9")
    ap.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_sweep_LINKUSDT_bf7919c368e63524_regime_hold.json")
    ap.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_sweep_LINKUSDT_bf7919c368e63524_regime_hold.md")
    ap.add_argument("--ranking-mode", choices=["train_gate", "freeze_proxy"], default="freeze_proxy")
    ap.add_argument("--proxy-bootstrap-iterations", type=int, default=200)
    ap.add_argument("--prescreen-profile", choices=["freeze_balanced", "freeze_protective"], default="freeze_balanced")
    ap.add_argument("--strict-drawdown-cap", type=float, default=0.25)
    ap.add_argument("--hold-multipliers", type=float, nargs="+", default=[1.0, 0.75, 0.5])
    ap.add_argument("--min-signals-train", type=int, default=None)
    ap.add_argument("--min-signals-per-fold", type=int, default=None)
    ap.add_argument("--max-signals-train", type=int, default=None)
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    started = time.time()
    payload = run_regime_hold_sweep(args)
    print(
        "contract_regime_hold_sweep_v9 done "
        f"symbol={payload['symbol']} sampled={payload['summary']['sampled']} "
        f"passed={payload['summary']['gate_passed']} elapsed_sec={time.time() - started:.2f}"
    )
    print(args.out_json)
    print(args.out_md)


if __name__ == "__main__":
    main()
