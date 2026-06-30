#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lunar_genome_crypto_lab_v7_robust as v7
import lunar_genome_symbol_validate_v7 as sv
import lunar_genome_symbol_walkforward_v7 as wf

BASE = Path("/root/.openclaw/workspace/kimi-shared-brain")
STATE = BASE / "state"
ADVERSARIAL_BANK = STATE / "adversarial_scenario_bank_v7.jsonl"
HOLDOUT_MANIFEST = STATE / "locked_holdout_manifest_v7.json"


def save_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=v7.to_jsonable))
    tmp.replace(p)


def parse_ints(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def parse_costs(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def costs_to_arg(costs: list[float]) -> str:
    return ",".join(str(int(c)) if float(c).is_integer() else str(c) for c in costs)


def genome_hash(genome: dict[str, Any]) -> str:
    raw = json.dumps(genome, sort_keys=True, separators=(",", ":"), default=v7.to_jsonable)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def candidate_key(row: dict[str, Any]) -> str:
    return f"{row.get('symbol')}:{genome_hash(row.get('genome') or {})}"


def load_candidates(path: str, limit: int, symbols: set[str]) -> list[dict[str, Any]]:
    obj = json.loads(Path(path).read_text())
    rows = (obj.get("qualified") or []) + (obj.get("top") or [])
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        symbol = row.get("symbol")
        genome = row.get("genome")
        if not symbol or not genome or symbol not in symbols:
            continue
        key = candidate_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def make_args(base: argparse.Namespace, symbol: str, seed: int, scenario_costs: str, scenarios: int | None = None, signal_delay_bars: int = 0):
    one = SimpleNamespace(**vars(base))
    one.symbols = [symbol]
    one.seed = seed
    one.scenario_costs = scenario_costs
    one.scenarios = scenarios if scenarios is not None else base.scenarios
    one.signal_delay_bars = signal_delay_bars
    return one


def make_scenarios(base: argparse.Namespace, symbol: str, seed: int, scenario_costs: str, scenarios: int | None = None):
    args = make_args(base, symbol, seed, scenario_costs, scenarios)
    return v7.build_scenarios(args, random.Random(seed), 1)


def symbol_metrics(genome, scenarios: list[dict[str, Any]], args) -> tuple[float, dict[str, Any]]:
    score, metrics = v7.robust_evaluate(genome, scenarios, args)
    return score, sv.symbol_metrics_from_rows(metrics.get("rows") or [])


def strict_ok(metrics: dict[str, Any], args) -> bool:
    return bool(
        metrics.get("survival_rate", 0.0) >= args.min_survival_rate
        and metrics.get("min_alpha", -999.0) >= args.min_alpha
        and metrics.get("min_return", -999.0) >= args.min_return
        and metrics.get("avg_alpha", -999.0) > 0
        and metrics.get("max_drawdown", 999.0) <= args.max_drawdown
        and metrics.get("avg_trades_per_scenario", metrics.get("trades", 0.0)) >= args.min_trades
        and metrics.get("max_trades_per_scenario", metrics.get("trades", 0.0)) <= args.max_trades
    )


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "qualified_rows",
        "scenario_count",
        "survival_rate",
        "min_alpha",
        "avg_alpha",
        "min_return",
        "avg_return",
        "max_drawdown",
        "avg_trades_per_scenario",
        "max_trades_per_scenario",
        "dominant_regime",
        "router_active_frac",
        "regime_trade_distribution",
    ]
    return {k: metrics.get(k) for k in keys if k in metrics}


def deterministic_audit(genome, symbol: str, args, seed: int) -> dict[str, Any]:
    scenarios = make_scenarios(args, symbol, seed, args.scenario_costs, args.scenarios)
    eval_args = make_args(args, symbol, seed, args.scenario_costs)
    _, first = symbol_metrics(genome, copy.deepcopy(scenarios), eval_args)
    _, second = symbol_metrics(genome, copy.deepcopy(scenarios), eval_args)
    fields = ["qualified_rows", "scenario_count", "min_alpha", "avg_alpha", "min_return", "avg_return", "max_drawdown", "trade_total"]
    diffs = {}
    for field in fields:
        a = first.get(field)
        b = second.get(field)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            diff = abs(float(a) - float(b))
            if diff > 1e-12:
                diffs[field] = diff
        elif a != b:
            diffs[field] = [a, b]
    return {
        "passed": not diffs,
        "diffs": diffs,
        "metrics": compact_metrics(first),
        "replay_hashes": {
            "same_metrics_hash": not diffs,
            "same_signal_hash": None,
            "same_trade_hash": None,
            "same_equity_curve_hash": None,
            "same_benchmark_hash": None,
            "unavailable_reason": "current evaluator does not emit signal/trade/equity/benchmark tables",
        },
    }


def validation_seed_checks(genome, symbol: str, args, seeds: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks = []
    failures = []
    for seed in seeds:
        scenarios = make_scenarios(args, symbol, seed, args.scenario_costs, args.scenarios)
        eval_args = make_args(args, symbol, seed, args.scenario_costs)
        _, metrics = symbol_metrics(genome, scenarios, eval_args)
        ok = strict_ok(metrics, args)
        row = {"seed": seed, "passed": ok, "metrics": compact_metrics(metrics)}
        checks.append(row)
        if not ok:
            failures.extend(failing_details(symbol, seed, "independent_validation", scenarios, metrics))
    return checks, failures


def cost_stress_checks(genome, symbol: str, args, seed: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    costs = parse_costs(args.stress_costs)
    scenarios = make_scenarios(args, symbol, seed, costs_to_arg(costs), args.stress_scenarios)
    eval_args = make_args(args, symbol, seed, costs_to_arg(costs), args.stress_scenarios)
    _, metrics = symbol_metrics(genome, scenarios, eval_args)
    ok = strict_ok(metrics, args)
    failures = [] if ok else failing_details(symbol, seed, "cost_stress", scenarios, metrics)
    return {"seed": seed, "costs": costs, "passed": ok, "metrics": compact_metrics(metrics)}, failures


def signal_delay_check(genome, symbol: str, args, seed: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scenarios = make_scenarios(args, symbol, seed, args.scenario_costs, args.delay_scenarios)
    eval_args = make_args(args, symbol, seed, args.scenario_costs, args.delay_scenarios, signal_delay_bars=args.signal_delay_bars)
    _, metrics = symbol_metrics(genome, scenarios, eval_args)
    ok = bool(
        metrics.get("survival_rate", 0.0) >= args.delay_min_survival_rate
        and metrics.get("min_alpha", -999.0) >= args.delay_min_alpha
        and metrics.get("max_drawdown", 999.0) <= args.max_drawdown
    )
    failures = [] if ok else failing_details(symbol, seed, "signal_delay", scenarios, metrics)
    return {"seed": seed, "delay_bars": args.signal_delay_bars, "passed": ok, "metrics": compact_metrics(metrics)}, failures


def jitter_checks(genome, symbol: str, args, seed: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rng = random.Random(seed)
    passed = 0
    runs = []
    failures = []
    for idx in range(args.jitter_count):
        jittered = v7.lab.mutate_genome(genome, rng, prob=args.jitter_prob, scale=args.jitter_scale)
        scenarios = make_scenarios(args, symbol, seed + idx + 1, args.scenario_costs, args.jitter_scenarios)
        eval_args = make_args(args, symbol, seed + idx + 1, args.scenario_costs, args.jitter_scenarios)
        _, metrics = symbol_metrics(jittered, scenarios, eval_args)
        ok = strict_ok(metrics, args)
        passed += 1 if ok else 0
        runs.append({"index": idx + 1, "passed": ok, "metrics": compact_metrics(metrics)})
        if not ok:
            failures.extend(failing_details(symbol, seed + idx + 1, "parameter_jitter", scenarios, metrics))
    pass_rate = passed / max(1, args.jitter_count)
    return {"passed": pass_rate >= args.jitter_min_pass_rate, "pass_rate": pass_rate, "runs": runs}, failures


def random_control_checks(symbol: str, args, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    accidental_passes = []
    for idx in range(args.random_control_count):
        genome = v7.lab.random_genome(rng)
        scenarios = make_scenarios(args, symbol, seed + idx + 1, args.scenario_costs, args.random_control_scenarios)
        eval_args = make_args(args, symbol, seed + idx + 1, args.scenario_costs, args.random_control_scenarios)
        _, metrics = symbol_metrics(genome, scenarios, eval_args)
        if strict_ok(metrics, args):
            accidental_passes.append({"index": idx + 1, "metrics": compact_metrics(metrics)})
    return {"passed": not accidental_passes, "accidental_passes": accidental_passes, "count": args.random_control_count}


def is_data_gate_rejection(exc: SystemExit) -> bool:
    return str(exc).startswith("data_health_gate_rejected_all_symbols")


def walkforward_check(genome_dict: dict[str, Any], symbol: str, args, seed: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    genome = v7.dict_to_genome(genome_dict)
    wf_windows = wf.windows(args.start, args.end, args.walkforward_window_months, args.walkforward_step_months)
    windows = []
    failures = []
    passed = 0
    tested = 0
    skipped = 0
    for idx, (ws, we) in enumerate(wf_windows, 1):
        wf_args = SimpleNamespace(**vars(args))
        wf_args.scenarios = args.walkforward_scenarios
        wf_args.scenario_costs = args.scenario_costs
        try:
            scenarios = wf.make_symbol_window_scenarios(wf_args, symbol, ws, we, seed + idx)
        except SystemExit as exc:
            if not is_data_gate_rejection(exc):
                raise
            skipped += 1
            windows.append({"window": f"{ws}..{we}", "skipped": True, "skip_reason": str(exc)})
            continue
        eval_args = make_args(args, symbol, seed + idx, args.scenario_costs, args.walkforward_scenarios)
        _, metrics = symbol_metrics(genome, scenarios, eval_args)
        ok = strict_ok(metrics, args)
        tested += 1
        passed += 1 if ok else 0
        windows.append({"window": f"{ws}..{we}", "passed": ok, "metrics": compact_metrics(metrics)})
        if not ok:
            failures.extend(failing_details(symbol, seed + idx, f"walkforward:{ws}..{we}", scenarios, metrics))
    return {
        "passed": bool(tested >= args.min_walkforward_windows and passed == tested),
        "passed_windows": passed,
        "tested_windows": tested,
        "skipped_windows": skipped,
        "window_count": len(wf_windows),
        "min_required_tested_windows": args.min_walkforward_windows,
        "windows": windows,
    }, failures


def monte_carlo_check(validation_checks: list[dict[str, Any]], args, seed: int) -> dict[str, Any]:
    alpha_values = []
    return_values = []
    for check in validation_checks:
        metrics = check.get("metrics") or {}
        if metrics.get("min_alpha") is not None:
            alpha_values.append(float(metrics["min_alpha"]))
        if metrics.get("min_return") is not None:
            return_values.append(float(metrics["min_return"]))
    if not alpha_values or not return_values:
        return {"passed": False, "reason": "no_validation_distribution"}
    rng = random.Random(seed)
    means_alpha = []
    means_return = []
    busts = 0
    n = len(alpha_values)
    for _ in range(args.monte_carlo_sims):
        sample_alpha = [rng.choice(alpha_values) for _ in range(n)]
        sample_return = [rng.choice(return_values) for _ in range(n)]
        means_alpha.append(sum(sample_alpha) / n)
        means_return.append(sum(sample_return) / n)
        if min(sample_return) < args.monte_carlo_bust_return:
            busts += 1
    means_alpha.sort()
    means_return.sort()
    p05_alpha = means_alpha[max(0, int(0.05 * (len(means_alpha) - 1)))]
    p05_return = means_return[max(0, int(0.05 * (len(means_return) - 1)))]
    bust_prob = busts / max(1, args.monte_carlo_sims)
    return {
        "passed": p05_alpha > args.min_alpha and p05_return > args.min_return and bust_prob <= args.monte_carlo_max_bust_prob,
        "p05_mean_alpha": p05_alpha,
        "p05_mean_return": p05_return,
        "bust_probability": bust_prob,
        "sims": args.monte_carlo_sims,
    }


def holdout_manifest(args) -> dict[str, Any]:
    if HOLDOUT_MANIFEST.exists():
        return json.loads(HOLDOUT_MANIFEST.read_text())
    seeds = [args.holdout_seed_base + i for i in range(args.holdout_seed_count)]
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Locked holdout for final approval only. Do not use these seeds in GA search or adversarial training.",
        "pollution_policy": "private_holdout_failures_are_not_written_to_adversarial_bank_until_holdout_version_is_retired",
        "seeds": seeds,
        "scenario_count": args.holdout_scenarios,
        "scenario_costs": args.scenario_costs,
    }
    save_json(HOLDOUT_MANIFEST, payload)
    return payload


def holdout_check(genome, symbol: str, args) -> dict[str, Any]:
    manifest = holdout_manifest(args)
    checks = []
    all_passed = True
    for seed in manifest["seeds"]:
        scenarios = make_scenarios(args, symbol, int(seed), manifest["scenario_costs"], int(manifest["scenario_count"]))
        eval_args = make_args(args, symbol, int(seed), manifest["scenario_costs"], int(manifest["scenario_count"]))
        _, metrics = symbol_metrics(genome, scenarios, eval_args)
        ok = strict_ok(metrics, args)
        all_passed = all_passed and ok
        checks.append({"seed": seed, "passed": ok, "metrics": compact_metrics(metrics)})
    return {"passed": all_passed, "manifest": manifest, "checks": checks}


def failing_details(symbol: str, seed: int, source: str, scenarios: list[dict[str, Any]], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    details = metrics.get("details") or []
    out = []
    for scenario, detail in zip(scenarios, details):
        if detail.get("qualified"):
            continue
        out.append({
            "source": source,
            "seed": seed,
            "symbol": symbol,
            "scenario": detail.get("scenario"),
            "cost_bps": detail.get("cost_bps"),
            "selected": scenario.get("selected"),
            "alpha": detail.get("alpha"),
            "return": detail.get("return"),
            "max_drawdown": detail.get("max_drawdown"),
            "trades": detail.get("trades"),
            "failure_tags": failure_tags(detail),
        })
    return out


def failure_tags(detail: dict[str, Any]) -> list[str]:
    tags = []
    if float(detail.get("alpha", 0.0)) < 0:
        tags.append("negative_alpha")
    if float(detail.get("return", 0.0)) < 0:
        tags.append("negative_return")
    if float(detail.get("max_drawdown", 0.0)) > 0.20:
        tags.append("drawdown")
    if int(detail.get("trades", 0)) <= 0:
        tags.append("no_trades")
    return tags


def append_adversarial(candidate_id: str, failures: list[dict[str, Any]], max_rows: int) -> int:
    if not failures:
        return 0
    ADVERSARIAL_BANK.parent.mkdir(exist_ok=True)
    written = 0
    with ADVERSARIAL_BANK.open("a") as fh:
        for row in failures[:max_rows]:
            payload = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "candidate_id": candidate_id, **row}
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=v7.to_jsonable) + "\n")
            written += 1
    return written


def approve_candidate(row: dict[str, Any], args, seeds: list[int]) -> dict[str, Any]:
    symbol = row["symbol"]
    genome_dict = row["genome"]
    genome = v7.dict_to_genome(genome_dict)
    cid = candidate_key(row)
    failures: list[dict[str, Any]] = []
    deterministic = deterministic_audit(genome, symbol, args, seeds[0])
    validation, validation_failures = validation_seed_checks(genome, symbol, args, seeds)
    failures.extend(validation_failures)
    independent_pass = deterministic["passed"] and all(x["passed"] for x in validation)
    random_controls = random_control_checks(symbol, args, args.random_control_seed)
    validated = independent_pass and random_controls["passed"]

    stress, stress_failures = cost_stress_checks(genome, symbol, args, args.stress_seed)
    delay, delay_failures = signal_delay_check(genome, symbol, args, args.delay_seed)
    jitter, jitter_failures = jitter_checks(genome, symbol, args, args.jitter_seed)
    wf_result, wf_failures = walkforward_check(genome_dict, symbol, args, args.walkforward_seed)
    failures.extend(stress_failures)
    failures.extend(delay_failures)
    failures.extend(jitter_failures)
    failures.extend(wf_failures)
    mc = monte_carlo_check(validation, args, args.monte_carlo_seed)
    holdout = holdout_check(genome, symbol, args) if validated and stress["passed"] and delay["passed"] and jitter["passed"] and wf_result["passed"] and mc["passed"] else {"passed": False, "skipped": True}
    paper_ready = bool(validated and stress["passed"] and delay["passed"] and jitter["passed"] and wf_result["passed"] and mc["passed"] and holdout["passed"])
    adversarial_rows = 0 if paper_ready else append_adversarial(cid, failures, args.max_adversarial_rows_per_candidate)
    return {
        "candidate_id": cid,
        "symbol": symbol,
        "genome_hash": genome_hash(genome_dict),
        "internal_metrics": compact_metrics(row.get("metrics") or {}),
        "validated": validated,
        "paper_ready": paper_ready,
        "deterministic_audit": deterministic,
        "independent_validation": validation,
        "random_controls": random_controls,
        "cost_stress": stress,
        "signal_delay": delay,
        "parameter_jitter": jitter,
        "walkforward": wf_result,
        "monte_carlo": mc,
        "holdout": holdout,
        "holdout_pollution_policy": {
            "private_holdout_failures_written_to_adversarial_bank": False,
            "public_validation_failures_written_to_adversarial_bank": not paper_ready and bool(failures),
            "retirement_required_before_holdout_reuse": True,
        },
        "adversarial_rows_written": adversarial_rows,
        "genome": genome_dict,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Terminal approval gate for v7 strategy candidates")
    ap.add_argument("--archive", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT"])
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--start", default="2017-08")
    ap.add_argument("--end", default="2026-05")
    ap.add_argument("--months-per-symbol", type=int, default=12)
    ap.add_argument("--window-bars", type=int, default=3000)
    ap.add_argument("--scenarios", type=int, default=24)
    ap.add_argument("--scenario-costs", default="20,30,50")
    ap.add_argument("--validation-seeds", default="930777,930778,930779")
    ap.add_argument("--data-manifest-dir", default="")
    ap.add_argument("--data-audit-summary-hash", default="")
    ap.add_argument("--initial-cash", type=float, default=10000.0)
    ap.add_argument("--lot-step", type=float, default=0.0001)
    ap.add_argument("--lot-min", type=float, default=0.0001)
    ap.add_argument("--min-notional", type=float, default=10.0)
    ap.add_argument("--drawdown-penalty", type=float, default=18.0)
    ap.add_argument("--max-drawdown", type=float, default=0.20)
    ap.add_argument("--max-trades", type=int, default=216)
    ap.add_argument("--min-trades", type=int, default=14)
    ap.add_argument("--min-positive-alpha-frac", type=float, default=1.0)
    ap.add_argument("--min-alpha", type=float, default=0.0)
    ap.add_argument("--min-return", type=float, default=0.0)
    ap.add_argument("--min-survival-rate", type=float, default=1.0)
    ap.add_argument("--stress-costs", default="20,30,50,75,100")
    ap.add_argument("--stress-seed", type=int, default=931777)
    ap.add_argument("--stress-scenarios", type=int, default=24)
    ap.add_argument("--signal-delay-bars", type=int, default=1)
    ap.add_argument("--delay-seed", type=int, default=932777)
    ap.add_argument("--delay-scenarios", type=int, default=12)
    ap.add_argument("--delay-min-survival-rate", type=float, default=0.95)
    ap.add_argument("--delay-min-alpha", type=float, default=-0.01)
    ap.add_argument("--jitter-seed", type=int, default=933777)
    ap.add_argument("--jitter-count", type=int, default=5)
    ap.add_argument("--jitter-scenarios", type=int, default=8)
    ap.add_argument("--jitter-prob", type=float, default=0.35)
    ap.add_argument("--jitter-scale", type=float, default=0.25)
    ap.add_argument("--jitter-min-pass-rate", type=float, default=0.80)
    ap.add_argument("--random-control-seed", type=int, default=934777)
    ap.add_argument("--random-control-count", type=int, default=8)
    ap.add_argument("--random-control-scenarios", type=int, default=6)
    ap.add_argument("--walkforward-seed", type=int, default=935777)
    ap.add_argument("--walkforward-window-months", type=int, default=18)
    ap.add_argument("--walkforward-step-months", type=int, default=9)
    ap.add_argument("--walkforward-scenarios", type=int, default=6)
    ap.add_argument("--min-walkforward-windows", type=int, default=3)
    ap.add_argument("--monte-carlo-seed", type=int, default=936777)
    ap.add_argument("--monte-carlo-sims", type=int, default=1000)
    ap.add_argument("--monte-carlo-bust-return", type=float, default=-0.05)
    ap.add_argument("--monte-carlo-max-bust-prob", type=float, default=0.05)
    ap.add_argument("--holdout-seed-base", type=int, default=990001)
    ap.add_argument("--holdout-seed-count", type=int, default=2)
    ap.add_argument("--holdout-scenarios", type=int, default=24)
    ap.add_argument("--max-adversarial-rows-per-candidate", type=int, default=200)
    args = ap.parse_args()

    started = time.time()
    seeds = parse_ints(args.validation_seeds)
    candidates = load_candidates(args.archive, args.limit, set(args.symbols))
    results = []
    for idx, row in enumerate(candidates, 1):
        result = approve_candidate(row, args, seeds)
        results.append(result)
        print(
            "APPROVAL",
            idx,
            result["symbol"],
            "validated",
            result["validated"],
            "paper_ready",
            result["paper_ready"],
            "adv",
            result["adversarial_rows_written"],
            flush=True,
        )
    validated = [r for r in results if r["validated"]]
    paper_ready = [r for r in results if r["paper_ready"]]
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "args": vars(args),
        "elapsed_sec": round(time.time() - started, 3),
        "candidate_count": len(candidates),
        "validated_count": len(validated),
        "paper_ready_count": len(paper_ready),
        "validated": validated,
        "paper_ready": paper_ready,
        "top": results,
        "adversarial_bank": str(ADVERSARIAL_BANK),
        "holdout_manifest": str(HOLDOUT_MANIFEST),
    }
    save_json(args.out, payload)
    print(
        "DONE",
        json.dumps(
            {
                "out": args.out,
                "candidate_count": len(candidates),
                "validated_count": len(validated),
                "paper_ready_count": len(paper_ready),
                "elapsed_sec": payload["elapsed_sec"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
