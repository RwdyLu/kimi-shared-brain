#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lunar_genome_crypto_lab_v7_robust as v7
import lunar_genome_symbol_validate_v7 as sv


def month_range(start: str, end: str) -> list[str]:
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y += 1
            m = 1
    return out


def add_months(month: str, delta: int) -> str:
    y, m = map(int, month.split("-"))
    m += delta
    while m > 12:
        y += 1
        m -= 12
    while m < 1:
        y -= 1
        m += 12
    return f"{y:04d}-{m:02d}"


def windows(start: str, end: str, window_months: int, step_months: int) -> list[tuple[str, str]]:
    months = month_range(start, end)
    out = []
    for i in range(0, max(0, len(months) - window_months + 1), step_months):
        ws = months[i]
        we = add_months(ws, window_months - 1)
        if we <= end:
            out.append((ws, we))
    return out


def save_json(path: str, payload: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=v7.to_jsonable))
    tmp.replace(p)


def strict_ok(metrics: dict, args) -> bool:
    return bool(
        metrics["survival_rate"] >= args.min_survival_rate
        and metrics["min_alpha"] >= args.min_alpha
        and metrics["min_return"] >= args.min_return
        and metrics["avg_alpha"] > 0
        and metrics["max_drawdown"] <= args.max_drawdown
        and metrics["trades"] >= args.min_trades
        and metrics["trades"] <= args.max_trades
    )


def symbol_metrics(rows: list[dict]) -> dict:
    usable = [row for row in rows if row.get("per_symbol")]
    if not usable:
        return {
            "qualified_rows": 0,
            "scenario_count": max(1, len(rows)),
            "survival_rate": 0.0,
            "min_alpha": -999.0,
            "avg_alpha": -999.0,
            "min_return": -999.0,
            "avg_return": -999.0,
            "max_drawdown": 999.0,
            "trades": 0,
            "details": [],
        }
    return sv.symbol_metrics_from_rows(usable)


def make_symbol_window_scenarios(args, symbol: str, start: str, end: str, seed: int):
    one = SimpleNamespace(**vars(args))
    one.symbols = [symbol]
    one.start = start
    one.end = end
    one.months_per_symbol = min(args.months_per_symbol, len(month_range(start, end)))
    rng = random.Random(seed)
    return v7.build_scenarios(one, rng, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Walk-forward terminal validation for v7 symbol genomes")
    ap.add_argument("--archive", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--seed", type=int, default=940000)
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--timeframe", default="1m")
    ap.add_argument("--start", default="2017-08")
    ap.add_argument("--end", default="2026-05")
    ap.add_argument("--window-months", type=int, default=18)
    ap.add_argument("--step-months", type=int, default=9)
    ap.add_argument("--months-per-symbol", type=int, default=4)
    ap.add_argument("--window-bars", type=int, default=12000)
    ap.add_argument("--scenarios", type=int, default=6)
    ap.add_argument("--scenario-costs", default="20,30,50")
    ap.add_argument("--initial-cash", type=float, default=10000.0)
    ap.add_argument("--lot-step", type=float, default=0.0001)
    ap.add_argument("--lot-min", type=float, default=0.0001)
    ap.add_argument("--min-notional", type=float, default=10.0)
    ap.add_argument("--drawdown-penalty", type=float, default=18.0)
    ap.add_argument("--max-drawdown", type=float, default=0.20)
    ap.add_argument("--max-trades", type=int, default=2400)
    ap.add_argument("--min-trades", type=int, default=120)
    ap.add_argument("--min-positive-alpha-frac", type=float, default=1.0)
    ap.add_argument("--min-alpha", type=float, default=0.0)
    ap.add_argument("--min-return", type=float, default=0.0)
    ap.add_argument("--min-survival-rate", type=float, default=1.0)
    args = ap.parse_args()

    started = time.time()
    archive = json.loads(Path(args.archive).read_text())
    candidate_rows = (archive.get("qualified") or []) + (archive.get("top") or [])
    seen = set()
    candidates = []
    for row in candidate_rows:
        symbol = row.get("symbol")
        genome = row.get("genome")
        if symbol not in args.symbols or not genome:
            continue
        key = json.dumps([symbol, genome], sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(row)
        if len(candidates) >= args.limit:
            break

    wf_windows = windows(args.start, args.end, args.window_months, args.step_months)
    results = []
    for ci, row in enumerate(candidates, 1):
        symbol = row["symbol"]
        genome = v7.dict_to_genome(row["genome"])
        if not genome:
            continue
        window_rows = []
        passed = 0
        for wi, (ws, we) in enumerate(wf_windows, 1):
            scenarios = make_symbol_window_scenarios(args, symbol, ws, we, args.seed + ci * 1000 + wi)
            score, metrics = v7.robust_evaluate(genome, scenarios, args)
            sm = symbol_metrics(metrics.get("rows") or [])
            ok = strict_ok(sm, args)
            passed += 1 if ok else 0
            window_rows.append({
                "window": f"{ws}..{we}",
                "score": score,
                "qualified": ok,
                "metrics": sm,
            })
        min_alpha = min((float(w["metrics"]["min_alpha"]) for w in window_rows), default=-999.0)
        avg_alpha = sum(float(w["metrics"]["avg_alpha"]) for w in window_rows) / max(1, len(window_rows))
        min_return = min((float(w["metrics"]["min_return"]) for w in window_rows), default=-999.0)
        avg_return = sum(float(w["metrics"]["avg_return"]) for w in window_rows) / max(1, len(window_rows))
        max_dd = max((float(w["metrics"]["max_drawdown"]) for w in window_rows), default=999.0)
        trades = sum(int(w["metrics"]["trades"]) for w in window_rows)
        qualified = bool(
            window_rows
            and passed == len(window_rows)
            and min_alpha >= args.min_alpha
            and min_return >= args.min_return
            and max_dd <= args.max_drawdown
            and trades <= args.max_trades
        )
        wf_score = (
            passed * 10000.0
            + min_alpha * 600000.0
            + min_return * 220000.0
            + avg_alpha * 1000.0
            + avg_return * 500.0
            - max_dd * 1000.0
        )
        results.append({
            "candidate_index": ci,
            "symbol": symbol,
            "score": wf_score,
            "qualified": qualified,
            "passed_windows": passed,
            "window_count": len(window_rows),
            "min_alpha": min_alpha,
            "avg_alpha": avg_alpha,
            "min_return": min_return,
            "avg_return": avg_return,
            "max_drawdown": max_dd,
            "trades": trades,
            "windows": window_rows,
            "genome": row["genome"],
        })
        best = max(results, key=lambda r: r["score"])
        print(
            "WF",
            ci,
            "best",
            best["symbol"],
            f"{best['passed_windows']}/{best['window_count']}",
            "min",
            round(best["min_alpha"], 6),
            "avg",
            round(best["avg_alpha"], 6),
            "q",
            best["qualified"],
            flush=True,
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    qualified = [r for r in results if r["qualified"]]
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "args": vars(args),
        "elapsed_sec": round(time.time() - started, 3),
        "candidate_count": len(candidates),
        "window_count": len(wf_windows),
        "qualified_count": len(qualified),
        "qualified": qualified[:20],
        "top": results[:50],
    }
    save_json(args.out, payload)
    print(
        "DONE",
        json.dumps(
            {
                "out": args.out,
                "candidate_count": len(candidates),
                "window_count": len(wf_windows),
                "qualified_count": len(qualified),
                "best": results[0] if results else None,
            },
            ensure_ascii=False,
            default=v7.to_jsonable,
        )[:2000],
        flush=True,
    )


if __name__ == "__main__":
    main()
