#!/usr/bin/env python3
"""Freeze a decorrelated candidate family before spending holdout data.

The script reads train-qualified search rows, re-evaluates them on a fixed
train-only scenario set, then selects the earliest deterministic family whose
common-scenario alpha/return vectors are below a preregistered correlation cap.
It must not read holdout files.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lunar_genome_crypto_lab_v7_robust as v7  # noqa: E402
import lunar_genome_symbol_validate_v7 as sv  # noqa: E402


_V8_MODULE: Any | None = None


def load_v8_module() -> Any:
    """Load the legacy evaluator only for CLI paths that re-evaluate genomes."""
    global _V8_MODULE
    if _V8_MODULE is not None:
        return _V8_MODULE
    try:
        _V8_MODULE = importlib.import_module("lunar_genome_symbol_local_search_v8_cvar_tailrisk")
    except ModuleNotFoundError as exc:
        if exc.name == "lunar_genome_symbol_local_search_v8_cvar_tailrisk":
            raise SystemExit(
                "missing legacy evaluator: scripts/lunar_genome_symbol_local_search_v8_cvar_tailrisk.py"
            ) from exc
        raise
    return _V8_MODULE


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Freeze a train-only decorrelated candidate family")
    ap.add_argument(
        "--state",
        default="state/lunar_genome_symbol_local_search_v8_cvar_tailrisk_lowfreq1h_core8_train201708_202406_evolve1000.json",
    )
    ap.add_argument("--out", default="results/frozen/v9_decorrelated_family_dryrun_20260706.json")
    ap.add_argument("--md", default="results/frozen/v9_decorrelated_family_dryrun_20260706.md")
    ap.add_argument("--batch-id", default="v9_decorrelated_family_dryrun_20260706")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT"])
    ap.add_argument("--family-size", type=int, default=3)
    ap.add_argument("--rho-cap", type=float, default=0.70)
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--start", default="2017-08")
    ap.add_argument("--end", default="2024-06")
    ap.add_argument("--scenarios", type=int, default=24)
    ap.add_argument("--scenario-costs", default="20,30,50")
    ap.add_argument("--months-per-symbol", type=int, default=4)
    ap.add_argument("--window-bars", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20260706)
    ap.add_argument("--data-manifest-dir", default="data/manifests/lowfreq1h_core8")
    ap.add_argument("--data-cache-dir", default="data/binance_public_cache")
    ap.add_argument("--max-candidates", type=int, default=200)
    ap.add_argument("--max-per-symbol", type=int, default=50)
    ap.add_argument("--min-trades", type=int, default=10)
    ap.add_argument("--max-trades", type=int, default=720)
    ap.add_argument("--max-drawdown", type=float, default=0.20)
    ap.add_argument("--require-common-gate", action="store_true")
    ap.add_argument("--regime-report", default="", help="train-only artifacts/v9/regime_report.json")
    ap.add_argument("--regime-gates-report-only", action="store_true")
    ap.add_argument("--enforce-regime-gates", action="store_true")
    ap.add_argument("--regime-max-share", type=float, default=0.60)
    ap.add_argument("--regime-min-coverage", type=int, default=2)
    ap.add_argument("--regime-min-days", type=int, default=21)
    ap.add_argument("--embargo-start", default="2024-07-01")
    return ap.parse_args()


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def genome_hash(genome_dict: dict[str, Any]) -> str:
    payload = json.dumps(genome_dict, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0.0 or vy <= 0.0:
        return 1.0 if xs == ys else None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def build_eval_args(args: argparse.Namespace, symbol: str) -> SimpleNamespace:
    return SimpleNamespace(
        symbols=[symbol],
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        months_per_symbol=args.months_per_symbol,
        window_bars=args.window_bars,
        scenarios=args.scenarios,
        scenario_costs=args.scenario_costs,
        data_manifest_dir=args.data_manifest_dir,
        data_audit_summary_hash="",
        data_cache_dir=args.data_cache_dir,
        initial_cash=10000.0,
        cost_bps=20.0,
        lot_step=0.0001,
        lot_min=0.0001,
        min_notional=10.0,
        drawdown_penalty=1.0,
        max_drawdown=args.max_drawdown,
        max_trades=args.max_trades,
        min_trades=args.min_trades,
        min_positive_alpha_frac=1.0,
        min_survival_rate=1.0,
        min_alpha=0.0,
        min_return=0.0,
        signal_delay_bars=0,
        prune_after=0,
        prune_min_alpha=-999.0,
        prune_max_failures=999999,
        tail_cvar_frac=0.25,
        tail_cvar_min_rows=3,
        tail_cvar_alpha_weight=700000.0,
        tail_worst_alpha_weight=200000.0,
        tail_avg_alpha_weight=30000.0,
        tail_cvar_dd_soft_limit=0.15,
        tail_cvar_dd_weight=500000.0,
    )


def load_source_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    state = json.loads(Path(args.state).read_text())
    rows = []
    per_symbol: dict[str, int] = {s: 0 for s in args.symbols}
    seen: set[tuple[str, str]] = set()
    qualified_rows = state.get("qualified") or []
    qualified_rows.sort(key=lambda r: (int(r.get("epoch", 10**9)), -float(r.get("score", 0.0))))
    for row in qualified_rows:
        symbol = row.get("symbol")
        genome = row.get("genome") or {}
        if symbol not in per_symbol or not genome:
            continue
        gh = genome_hash(genome)
        key = (symbol, gh)
        if key in seen:
            continue
        if per_symbol[symbol] >= args.max_per_symbol:
            continue
        seen.add(key)
        per_symbol[symbol] += 1
        rows.append(row)
        if len(rows) >= args.max_candidates:
            break
    return rows


def cvar(values: list[float], frac: float = 0.25) -> float:
    if not values:
        return 0.0
    n = max(1, int(math.ceil(len(values) * frac)))
    return sum(sorted(values)[:n]) / n


def common_gate_pass(metrics: dict[str, Any], args: argparse.Namespace) -> bool:
    return bool(
        float(metrics.get("survival_rate", 0.0)) >= 1.0
        and float(metrics.get("min_alpha", -9.0)) > 0.0
        and float(metrics.get("cvar_alpha", -9.0)) > 0.0
        and float(metrics.get("max_drawdown", 9.0)) <= args.max_drawdown
        and float(metrics.get("avg_trades_per_scenario", 0.0)) >= args.min_trades
        and float(metrics.get("max_trades_per_scenario", 0.0)) <= args.max_trades
    )


def parse_month_start(month: str) -> pd.Timestamp:
    return pd.Timestamp(month + "-01", tz="UTC")


def load_regime_context(report_path: str, embargo_start: str) -> dict[str, Any] | None:
    if not report_path:
        return None
    report = json.loads(Path(report_path).read_text())
    embargo = pd.Timestamp(embargo_start, tz="UTC")
    labels: dict[str, dict[str, Any]] = {}
    for symbol, path in (report.get("outputs", {}).get("labels") or {}).items():
        df = pd.read_parquet(path)
        if "dt" not in df.columns or "regime_id" not in df.columns:
            raise SystemExit(f"regime label file missing dt/regime_id: {path}")
        df = df.copy()
        df["dt"] = pd.to_datetime(df["dt"], utc=True, errors="coerce")
        if (df["dt"] >= embargo).any():
            bad = df.loc[df["dt"] >= embargo, "dt"].min()
            raise SystemExit(f"regime label embargo guard failed for {symbol}: {bad} >= {embargo}")
        df = df.dropna(subset=["dt", "regime_id"])
        df["month"] = df["dt"].dt.strftime("%Y-%m")
        month_counts: dict[str, dict[str, int]] = {}
        for (month, regime), count in df.groupby(["month", "regime_id"]).size().items():
            month_counts.setdefault(str(month), {})[str(regime)] = int(count)
        labels[symbol] = {"path": path, "month_counts": month_counts}
    return {
        "report": report_path,
        "config_sha256": report.get("config_sha256"),
        "embargo_start": str(embargo),
        "labels": labels,
    }


def add_counts(left: dict[str, float], right: dict[str, int | float], scale: float = 1.0) -> None:
    for key, value in right.items():
        left[key] = left.get(key, 0.0) + float(value) * scale


def selected_months(sc: dict[str, Any], symbol: str) -> list[str]:
    selected = sc.get("selected") or {}
    months = selected.get(symbol) or selected.get(symbol.replace("USDT", "")) or []
    return [str(m) for m in months]


def scenario_regime_counts(symbol: str, months: list[str], regime_ctx: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    label_info = (regime_ctx.get("labels") or {}).get(symbol)
    if not label_info:
        return {}, [f"missing_regime_labels:{symbol}"]
    month_counts = label_info.get("month_counts") or {}
    counts: dict[str, int] = {}
    missing: list[str] = []
    embargo = pd.Timestamp(regime_ctx["embargo_start"])
    for month in months:
        if parse_month_start(month) >= embargo:
            raise SystemExit(f"scenario selected embargo/holdout month {month} for {symbol}")
        mc = month_counts.get(month)
        if not mc:
            missing.append(month)
            continue
        for regime, count in mc.items():
            counts[regime] = counts.get(regime, 0) + int(count)
    return counts, missing


def regime_share(counts: dict[str, int | float]) -> dict[str, float]:
    total = sum(float(v) for v in counts.values())
    if total <= 0:
        return {}
    return {k: float(v) / total for k, v in sorted(counts.items())}


def compute_candidate_regime_report(
    candidate: dict[str, Any],
    symbol_manifest: list[dict[str, Any]],
    regime_ctx: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    symbol = candidate["symbol"]
    manifest_by_scenario: dict[int, dict[str, Any]] = {}
    for sc in symbol_manifest:
        sid = int(sc.get("scenario", 0))
        manifest_by_scenario.setdefault(sid, sc)

    exposure_counts: dict[str, float] = {}
    scenario_reports: list[dict[str, Any]] = []
    missing_months: dict[int, list[str]] = {}
    scenario_counts_cache: dict[int, dict[str, int]] = {}
    for sid, sc in sorted(manifest_by_scenario.items()):
        months = selected_months(sc, symbol)
        counts, missing = scenario_regime_counts(symbol, months, regime_ctx)
        if missing:
            missing_months[sid] = missing
        scenario_counts_cache[sid] = counts
        add_counts(exposure_counts, counts)
        scenario_reports.append(
            {
                "scenario": sid,
                "selected_months": months,
                "regime_days": counts,
                "regime_share": regime_share(counts),
                "missing_months": missing,
            }
        )

    shares = regime_share(exposure_counts)
    max_share = max(shares.values(), default=0.0)
    hhi = sum(v * v for v in shares.values())
    coverage = sum(1 for v in exposure_counts.values() if v > 0)

    alpha_weight_sum: dict[str, float] = {}
    return_weight_sum: dict[str, float] = {}
    weight_sum: dict[str, float] = {}
    for detail in candidate.get("scenario_details") or []:
        sid = int(detail.get("scenario", 0))
        counts = scenario_counts_cache.get(sid) or {}
        shares_for_scenario = regime_share(counts)
        alpha = float(detail.get("alpha", 0.0))
        ret = float(detail.get("return", 0.0))
        for regime, share in shares_for_scenario.items():
            alpha_weight_sum[regime] = alpha_weight_sum.get(regime, 0.0) + alpha * share
            return_weight_sum[regime] = return_weight_sum.get(regime, 0.0) + ret * share
            weight_sum[regime] = weight_sum.get(regime, 0.0) + share

    weighted_alpha: dict[str, float] = {}
    weighted_return: dict[str, float] = {}
    computable_regimes: list[str] = []
    for regime, weight in weight_sum.items():
        if weight <= 0:
            continue
        weighted_alpha[regime] = alpha_weight_sum[regime] / weight
        weighted_return[regime] = return_weight_sum[regime] / weight
        if exposure_counts.get(regime, 0.0) >= args.regime_min_days:
            computable_regimes.append(regime)
    computed_alphas = [weighted_alpha[r] for r in computable_regimes if r in weighted_alpha]
    worst_alpha = min(computed_alphas) if computed_alphas else None

    gates = {
        "has_regime_context": bool(exposure_counts),
        "max_regime_share_lte_limit": max_share <= args.regime_max_share,
        "regime_coverage_gte_min": coverage >= args.regime_min_coverage,
        "weighted_alpha_computable_for_min_regimes": len(computable_regimes) >= args.regime_min_coverage,
        "worst_weighted_regime_alpha_gt_0": (worst_alpha is not None and worst_alpha > 0.0),
        "no_missing_regime_months": not any(missing_months.values()),
    }
    passed = all(gates.values())
    return {
        "method": "train_only_scenario_window_regime_screen_v1",
        "note": "Scenario-window regime exposure only; this is not per-trade regime attribution or regime CVaR.",
        "config_sha256": regime_ctx.get("config_sha256"),
        "max_regime_share": max_share,
        "regime_hhi": hhi,
        "regime_coverage": coverage,
        "regime_share": shares,
        "regime_days": {k: int(v) for k, v in exposure_counts.items()},
        "regime_weighted_alpha": weighted_alpha,
        "regime_weighted_return": weighted_return,
        "computable_regimes": sorted(computable_regimes),
        "worst_weighted_regime_alpha": worst_alpha,
        "missing_months_by_scenario": missing_months,
        "gates": gates,
        "passed": passed,
        "report_only": bool(args.regime_gates_report_only),
        "enforced": bool(args.enforce_regime_gates),
        "scenario_reports": scenario_reports,
    }


def evaluate_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    v8 = load_v8_module()
    rng = random.Random(args.seed)
    scenario_cache: dict[str, list[dict[str, Any]]] = {}
    scenario_manifest: dict[str, list[dict[str, Any]]] = {}
    for symbol in args.symbols:
        ea = build_eval_args(args, symbol)
        scenarios = sv.make_symbol_scenarios(ea, rng, symbol)
        scenario_cache[symbol] = scenarios
        scenario_manifest[symbol] = [
            {
                "scenario": sc.get("scenario"),
                "cost_bps": sc.get("cost_bps"),
                "selected": sc.get("selected"),
                "eval_seed": sc.get("eval_seed"),
            }
            for sc in scenarios
        ]

    evaluated = []
    for idx, row in enumerate(rows, 1):
        symbol = row["symbol"]
        genome_dict = row["genome"]
        genome = v7.dict_to_genome(genome_dict)
        if genome is None:
            continue
        ea = build_eval_args(args, symbol)
        score, qualified, metrics = v8.eval_symbol(genome, symbol, scenario_cache[symbol], ea)
        details = sorted(metrics.get("details") or [], key=lambda d: (int(d.get("scenario", 0)), float(d.get("cost_bps", 0.0))))
        alpha_vec = [float(d.get("alpha", 0.0)) for d in details]
        return_vec = [float(d.get("return", 0.0)) for d in details]
        scenario_details = [
            {
                "scenario": int(d.get("scenario", 0)),
                "cost_bps": float(d.get("cost_bps", 0.0)),
                "alpha": float(d.get("alpha", 0.0)),
                "return": float(d.get("return", 0.0)),
                "max_drawdown": float(d.get("max_drawdown", 0.0)),
                "trades": int(d.get("trades", 0)),
                "qualified": bool(d.get("qualified", False)),
            }
            for d in details
        ]
        source_metrics = row.get("metrics") or {}
        gh = genome_hash(genome_dict)
        common_ok = bool(qualified) and common_gate_pass(metrics, args)
        evaluated.append(
            {
                "candidate_id": f"c{idx}_e{row.get('epoch')}_{symbol}_g{row.get('genome_index')}_{gh}",
                "source_rank": idx,
                "epoch": int(row.get("epoch", 0)),
                "genome_index": int(row.get("genome_index", 0)),
                "symbol": symbol,
                "score": float(row.get("score", 0.0)),
                "genome_hash": gh,
                "genome": genome_dict,
                "source_metrics": source_metrics,
                "common_score": float(score),
                "common_qualified": bool(qualified),
                "common_gate_passed": common_ok,
                "common_metrics": {
                    k: metrics.get(k)
                    for k in [
                        "survival_rate",
                        "min_alpha",
                        "avg_alpha",
                        "cvar_alpha",
                        "worst_alpha",
                        "max_drawdown",
                        "avg_trades_per_scenario",
                        "max_trades_per_scenario",
                    ]
                },
                "alpha_vector": alpha_vec,
                "return_vector": return_vec,
                "scenario_details": scenario_details,
            }
        )
    return evaluated, scenario_manifest


def pair_stats(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    alpha_rho = pearson(left["alpha_vector"], right["alpha_vector"])
    return_rho = pearson(left["return_vector"], right["return_vector"])
    return {
        "left": left["candidate_id"],
        "right": right["candidate_id"],
        "alpha_rho": alpha_rho,
        "return_rho": return_rho,
        "max_rho": None if alpha_rho is None or return_rho is None else max(alpha_rho, return_rho),
    }


def select_family(candidates: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_genomes: set[str] = set()
    for cand in candidates:
        if cand["genome_hash"] in seen_genomes:
            rejected.append({"candidate_id": cand["candidate_id"], "reason": "duplicate_genome"})
            continue
        if args.require_common_gate and not cand["common_gate_passed"]:
            rejected.append({"candidate_id": cand["candidate_id"], "reason": "common_train_gate_failed"})
            continue
        if args.enforce_regime_gates and not (cand.get("regime_gate_report") or {}).get("passed", False):
            rejected.append(
                {
                    "candidate_id": cand["candidate_id"],
                    "reason": "regime_gate_failed",
                    "regime_gates": (cand.get("regime_gate_report") or {}).get("gates", {}),
                }
            )
            continue
        pair_checks = [pair_stats(cand, chosen) for chosen in selected]
        bad = [p for p in pair_checks if p["max_rho"] is None or p["max_rho"] > args.rho_cap]
        if bad:
            rejected.append({"candidate_id": cand["candidate_id"], "reason": "correlation_cap_failed", "pairs": bad})
            continue
        selected.append(cand)
        seen_genomes.add(cand["genome_hash"])
        if len(selected) >= args.family_size:
            break
    return selected, rejected


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    selected = payload["selected_candidates"]
    regime_enabled = bool(payload.get("regime_gate"))
    lines = [
        "# Decorrelated Candidate Freeze Report",
        "",
        f"created_at: {payload['created_at']}",
        f"batch_id: {payload['batch_id']}",
        f"family_frozen: `{payload['family_frozen']}`",
        f"selected: {len(selected)}/{payload['family_size']}",
        f"rho_cap: {payload['rho_cap']}",
        f"require_common_gate: `{payload['require_common_gate']}`",
        f"regime_gate_enabled: `{regime_enabled}`",
        "",
        "Regime metrics are scenario-window train-only exposure metrics. They are not per-trade regime attribution and not regime CVaR.",
        "",
        "## Selected Candidates",
        "",
        "| Candidate | Symbol | Epoch | Source score | Common avg alpha | Common min alpha | Common CVaR alpha | Common max DD | Regime pass | Max regime share | Coverage | Worst weighted alpha |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if selected:
        for c in selected:
            m = c["common_metrics"]
            rg = c.get("regime_gate_report") or {}
            worst = rg.get("worst_weighted_regime_alpha")
            worst_txt = "" if worst is None else f"{float(worst):.6f}"
            lines.append(
                "| {cid} | {sym} | {epoch} | {score:.3f} | {avg:.6f} | {mn:.6f} | {cv:.6f} | {dd:.4f} | {rpass} | {max_share:.3f} | {coverage} | {worst} |".format(
                    cid=c["candidate_id"],
                    sym=c["symbol"],
                    epoch=c["epoch"],
                    score=c["score"],
                    avg=float(m.get("avg_alpha", 0.0)),
                    mn=float(m.get("min_alpha", 0.0)),
                    cv=float(m.get("cvar_alpha", 0.0)),
                    dd=float(m.get("max_drawdown", 0.0)),
                    rpass=str(rg.get("passed", "")),
                    max_share=float(rg.get("max_regime_share", 0.0)),
                    coverage=rg.get("regime_coverage", ""),
                    worst=worst_txt,
                )
            )
    else:
        lines.append("| none | | | | | | | | | | | | |")
    lines.extend(
        [
            "",
            "## Selection Pair Checks",
            "",
            "| Left | Right | Alpha rho | Return rho | Max rho |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for p in payload["selected_pair_checks"]:
        lines.append(
            "| {left} | {right} | {alpha:.4f} | {ret:.4f} | {mx:.4f} |".format(
                left=p["left"],
                right=p["right"],
                alpha=float(p["alpha_rho"]),
                ret=float(p["return_rho"]),
                mx=float(p["max_rho"]),
            )
        )
    lines.extend(
        [
            "",
            "## Evaluated Candidate Summary",
            "",
            "| Candidate | Symbol | Epoch | Common gate | Regime gate | Max regime share | Coverage | Worst weighted alpha | Common avg alpha | Common min alpha | Common CVaR alpha | Common max DD |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for c in payload["evaluated_candidates"]:
        m = c["common_metrics"]
        rg = c.get("regime_gate_report") or {}
        worst = rg.get("worst_weighted_regime_alpha")
        worst_txt = "" if worst is None else f"{float(worst):.6f}"
        lines.append(
            "| {cid} | {sym} | {epoch} | {gate} | {rgate} | {max_share:.3f} | {coverage} | {worst} | {avg:.6f} | {mn:.6f} | {cv:.6f} | {dd:.4f} |".format(
                cid=c["candidate_id"],
                sym=c["symbol"],
                epoch=c["epoch"],
                gate=str(c["common_gate_passed"]),
                rgate=str(rg.get("passed", "")),
                max_share=float(rg.get("max_regime_share", 0.0)),
                coverage=rg.get("regime_coverage", ""),
                worst=worst_txt,
                avg=float(m.get("avg_alpha", 0.0)),
                mn=float(m.get("min_alpha", 0.0)),
                cv=float(m.get("cvar_alpha", 0.0)),
                dd=float(m.get("max_drawdown", 0.0)),
            )
        )
    if regime_enabled:
        lines.extend(["", "## Regime Gate Details", ""])
        rgconf = payload["regime_gate"]
        lines.append(f"- report: `{rgconf.get('report')}`")
        lines.append(f"- config_sha256: `{rgconf.get('config_sha256')}`")
        lines.append(f"- report_only: `{rgconf.get('report_only')}`")
        lines.append(f"- enforced: `{rgconf.get('enforced')}`")
        lines.append(f"- max_share_limit: `{rgconf.get('max_share_limit')}`")
        lines.append(f"- min_coverage: `{rgconf.get('min_coverage')}`")
        lines.append(f"- min_days: `{rgconf.get('min_days')}`")
    lines.extend(
        [
            "",
            "## Rejection Summary",
            "",
        ]
    )
    counts: dict[str, int] = {}
    for r in payload["rejected_candidates"]:
        counts[r["reason"]] = counts.get(r["reason"], 0) + 1
    if counts:
        for reason, count in sorted(counts.items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def strip_vectors(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean = []
    for c in candidates:
        item = dict(c)
        item.pop("alpha_vector", None)
        item.pop("return_vector", None)
        clean.append(item)
    return clean


def main() -> int:
    args = parse_args()
    started = time.time()
    source_rows = load_source_rows(args)
    evaluated, scenario_manifest = evaluate_rows(source_rows, args)
    regime_ctx = load_regime_context(args.regime_report, args.embargo_start)
    if args.enforce_regime_gates and not regime_ctx:
        raise SystemExit("--enforce-regime-gates requires --regime-report")
    if regime_ctx:
        for cand in evaluated:
            cand["regime_gate_report"] = compute_candidate_regime_report(
                cand,
                scenario_manifest.get(cand["symbol"], []),
                regime_ctx,
                args,
            )
    selected, rejected = select_family(evaluated, args)
    selected_pair_checks = []
    for i, left in enumerate(selected):
        for j in range(i + 1, len(selected)):
            selected_pair_checks.append(pair_stats(left, selected[j]))

    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": round(time.time() - started, 3),
        "batch_id": args.batch_id,
        "source_state": args.state,
        "source_state_sha256": sha256_file(Path(args.state)),
        "freeze_policy": "deterministic_order_epoch_then_score; select first family passing train-only decorrelation gate",
        "family_size": args.family_size,
        "rho_cap": args.rho_cap,
        "require_common_gate": bool(args.require_common_gate),
        "regime_gate": (
            {
                "report": args.regime_report,
                "config_sha256": regime_ctx.get("config_sha256"),
                "report_only": bool(args.regime_gates_report_only),
                "enforced": bool(args.enforce_regime_gates),
                "max_share_limit": args.regime_max_share,
                "min_coverage": args.regime_min_coverage,
                "min_days": args.regime_min_days,
                "embargo_start": args.embargo_start,
            }
            if regime_ctx
            else None
        ),
        "train_window": {"start": args.start, "end": args.end},
        "symbols": args.symbols,
        "args": vars(args),
        "source_candidate_count": len(source_rows),
        "evaluated_candidate_count": len(evaluated),
        "selected_count": len(selected),
        "family_frozen": len(selected) >= args.family_size,
        "selected_pair_checks": selected_pair_checks,
        "selected_candidates": strip_vectors(selected),
        "evaluated_candidates": strip_vectors(evaluated),
        "rejected_candidates": rejected,
        "scenario_manifest": scenario_manifest,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=v7.to_jsonable))
    write_markdown(payload, Path(args.md))
    print(json.dumps({
        "out": args.out,
        "md": args.md,
        "family_frozen": payload["family_frozen"],
        "selected_count": payload["selected_count"],
        "evaluated_candidate_count": payload["evaluated_candidate_count"],
        "elapsed_sec": payload["elapsed_sec"],
    }, indent=2, sort_keys=True))
    return 0 if payload["family_frozen"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
