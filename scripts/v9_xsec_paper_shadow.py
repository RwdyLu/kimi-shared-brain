#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_paper_readiness_gate import shadow_oos_report, write_json, write_text  # noqa: E402
from v9.contract.simulator import utc_ts  # noqa: E402
from v9.contract.xsec_momentum import load_close_matrix  # noqa: E402


DEFAULT_SYMBOLS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def record_hash(record: dict[str, Any], prev_hash: str) -> str:
    unsigned = {key: value for key, value in record.items() if key != "hash"}
    raw = f"{prev_hash}\n{canonical_json(unsigned)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_ledger_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid ledger JSON on line {line_no}: {exc}") from exc
        records.append(row)
    return records


def ledger_metrics_40bps(state: dict[str, Any]) -> dict[str, Any]:
    metrics = (((state.get("shadow") or {}).get("costs") or {}).get("40bps") or {})
    keep = (
        "sharpe",
        "daily_sharpe",
        "total_return",
        "max_drawdown",
        "rebalance_event_count",
        "daily_turnover",
        "avg_gross_exposure",
        "realized_daily_vol_ann",
    )
    return {key: metrics.get(key) for key in keep if key in metrics}


def ledger_record(
    *,
    state: dict[str, Any],
    seq: int,
    prev_hash: str,
    recorded_at: str,
) -> dict[str, Any]:
    shadow = state.get("shadow") or {}
    candidate = state.get("candidate") or {}
    record = {
        "kind": "xsec_paper_ledger_record_v1",
        "seq": int(seq),
        "recorded_at": recorded_at,
        "prev_hash": prev_hash,
        "status": state.get("status"),
        "source_gate": state.get("source_gate"),
        "candidate_artifact": candidate.get("artifact"),
        "latest_dt": shadow.get("latest_dt"),
        "latest_rebalance_dt": shadow.get("latest_rebalance_dt"),
        "latest_weights": shadow.get("latest_weights") or {},
        "latest_gross_exposure": shadow.get("latest_gross_exposure"),
        "metrics_40bps": ledger_metrics_40bps(state),
        "checks": state.get("checks") or {},
        "paper_trading_authorized": bool(state.get("paper_trading_authorized")),
        "live_trading_authorized": False,
    }
    record["hash"] = record_hash(record, prev_hash)
    return record


def append_ledger(state: dict[str, Any], path: Path, recorded_at: str | None = None) -> dict[str, Any]:
    if not state.get("paper_trading_authorized"):
        return {}
    records = read_ledger_records(path)
    prev_hash = str(records[-1].get("hash") or "") if records else "GENESIS"
    record = ledger_record(
        state=state,
        seq=len(records) + 1,
        prev_hash=prev_hash,
        recorded_at=recorded_at or now_utc(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def append_skip_ledger_marker(
    *,
    path: Path,
    reason: str,
    recorded_at: str | None = None,
    latest_dt: str | None = None,
    candidate_artifact: str | None = None,
    data_freshness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = read_ledger_records(path)
    prev_hash = str(records[-1].get("hash") or "") if records else "GENESIS"
    record = {
        "kind": "xsec_paper_ledger_skip_v1",
        "seq": len(records) + 1,
        "recorded_at": recorded_at or now_utc(),
        "prev_hash": prev_hash,
        "status": reason,
        "latest_dt": latest_dt,
        "candidate_artifact": candidate_artifact,
        "data_freshness": data_freshness or {},
        "paper_trading_authorized": True,
        "live_trading_authorized": False,
    }
    record["hash"] = record_hash(record, prev_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def latest_normal_ledger_record(path: Path) -> dict[str, Any] | None:
    for record in reversed(read_ledger_records(path)):
        if record.get("kind") == "xsec_paper_ledger_record_v1":
            return record
    return None


def latest_dt_is_duplicate(path: Path, latest_dt: str | None) -> bool:
    if not latest_dt:
        return False
    previous = latest_normal_ledger_record(path)
    return bool(previous and previous.get("latest_dt") == latest_dt)


def verify_ledger_chain(path: Path) -> dict[str, Any]:
    try:
        records = read_ledger_records(path)
    except ValueError as exc:
        return {"valid": False, "row_count": 0, "errors": [str(exc)]}
    errors = []
    prev_hash = "GENESIS"
    prev_recorded_at: pd.Timestamp | None = None
    max_gap_sec = 0.0
    first_recorded_at = None
    last_recorded_at = None
    for expected_seq, record in enumerate(records, start=1):
        if int(record.get("seq") or 0) != expected_seq:
            errors.append(f"line {expected_seq}: expected seq {expected_seq}, got {record.get('seq')}")
        if str(record.get("prev_hash") or "") != prev_hash:
            errors.append(f"line {expected_seq}: prev_hash mismatch")
        if str(record.get("hash") or "") != record_hash(record, prev_hash):
            errors.append(f"line {expected_seq}: hash mismatch")
        try:
            recorded_at = to_utc_timestamp(str(record.get("recorded_at")))
        except Exception:
            errors.append(f"line {expected_seq}: invalid recorded_at")
            recorded_at = None
        if recorded_at is not None:
            iso = recorded_at.isoformat()
            first_recorded_at = first_recorded_at or iso
            last_recorded_at = iso
            if prev_recorded_at is not None:
                max_gap_sec = max(max_gap_sec, (recorded_at - prev_recorded_at).total_seconds())
            prev_recorded_at = recorded_at
        prev_hash = str(record.get("hash") or "")
    return {
        "valid": not errors,
        "row_count": len(records),
        "first_recorded_at": first_recorded_at,
        "last_recorded_at": last_recorded_at,
        "max_gap_sec": max_gap_sec,
        "last_hash": prev_hash if records else None,
        "errors": errors,
    }


def resolve_evaluation_end(value: str) -> str:
    if str(value).strip().lower() == "now":
        return now_utc()
    return value


def to_utc_timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def paper_status(
    *,
    evaluation_start: str,
    latest_dt: str,
    metrics_40bps: dict[str, Any],
    min_weeks: int,
    min_rebalances: int,
    max_drawdown: float,
) -> tuple[str, dict[str, bool]]:
    start = to_utc_timestamp(evaluation_start)
    latest = to_utc_timestamp(latest_dt)
    age_days = max(0.0, (latest - start).total_seconds() / 86400.0)
    checks = {
        "paper_age_ge_min_weeks": age_days >= float(min_weeks * 7),
        "paper_rebalances_ge_min": int(metrics_40bps.get("rebalance_event_count") or 0) >= int(min_rebalances),
        "paper_drawdown_le_max": float(metrics_40bps.get("max_drawdown") or 0.0) <= float(max_drawdown),
        "paper_live_not_authorized": True,
    }
    if not checks["paper_drawdown_le_max"]:
        return "paper_stopped_risk_review_required", checks
    if all(checks.values()):
        return "paper_complete_live_manual_review_required", checks
    return "paper_running", checks


def signal_rows(shadow: dict[str, Any]) -> list[dict[str, Any]]:
    latest_dt = shadow.get("latest_dt")
    rows = []
    for symbol, weight in (shadow.get("latest_weights") or {}).items():
        pair = symbol[:-4] + "/USDT" if symbol.endswith("USDT") else symbol
        rows.append(
            {
                "date": latest_dt,
                "pair": pair,
                "symbol": symbol,
                "target_weight": float(weight),
                "enter_long": 1 if float(weight) > 0.0 else 0,
                "exit_long": 1 if float(weight) == 0.0 else 0,
            }
        )
    return rows


def format_signals_csv(rows: list[dict[str, Any]]) -> str:
    lines = ["date,pair,symbol,target_weight,enter_long,exit_long"]
    for row in rows:
        lines.append(
            f"{row['date']},{row['pair']},{row['symbol']},"
            f"{row['target_weight']:.10f},{row['enter_long']},{row['exit_long']}"
        )
    return "\n".join(lines) + "\n"


def build_shadow_state(
    *,
    gate_state_path: Path,
    cache_dir: Path,
    evaluation_end: str,
    costs_bps: tuple[float, ...],
) -> dict[str, Any]:
    gate = read_json(gate_state_path)
    if not gate.get("paper_trading_authorized"):
        return {
            "kind": "xsec_paper_shadow_state_v1",
            "updated_at": now_utc(),
            "status": "blocked",
            "reason": "paper_readiness_gate_not_authorized",
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "source_gate": str(gate_state_path),
        }
    candidate = gate["candidate"]
    config = dict(candidate["config"])
    data = gate.get("data") or {}
    warmup_start = str(data.get("warmup_start") or "2024-07-01")
    evaluation_start = str(data.get("evaluation_start") or "2026-06-01")
    symbols = tuple(((gate.get("holdout_40bps") or {}).get("symbols") or DEFAULT_SYMBOLS))
    closes = load_close_matrix(cache_dir, symbols, utc_ts(warmup_start), utc_ts(evaluation_end), utc_ts("2100-01-01"))
    shadow = shadow_oos_report(
        closes=closes,
        config=config,
        evaluation_start=utc_ts(evaluation_start),
        costs_bps=costs_bps,
    )
    metrics_40 = (shadow.get("costs") or {}).get("40bps") or {}
    paper_gate = gate.get("paper_gate") or {}
    status, checks = paper_status(
        evaluation_start=evaluation_start,
        latest_dt=str(shadow.get("latest_dt")),
        metrics_40bps=metrics_40,
        min_weeks=int(paper_gate.get("minimum_duration_weeks") or 12),
        min_rebalances=int(paper_gate.get("minimum_rebalance_events") or 9),
        max_drawdown=float(paper_gate.get("max_paper_drawdown") or 0.15),
    )
    rows = signal_rows(shadow)
    return {
        "kind": "xsec_paper_shadow_state_v1",
        "updated_at": now_utc(),
        "status": status,
        "checks": checks,
        "paper_trading_authorized": True,
        "live_trading_authorized": False,
        "source_gate": str(gate_state_path),
        "candidate": candidate,
        "data": {
            "warmup_start": warmup_start,
            "evaluation_start": evaluation_start,
            "evaluation_end": evaluation_end,
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
        },
        "shadow": shadow,
        "signals": rows,
        "note": "Paper shadow only. It writes target weights/signals and never authorizes live trading.",
    }


def format_text(state: dict[str, Any]) -> str:
    metrics = (((state.get("shadow") or {}).get("costs") or {}).get("40bps") or {})
    freshness = state.get("data_freshness") or {}
    lines = [
        f"status={state.get('status')}",
        f"safety=paper:{state.get('paper_trading_authorized')} live:{state.get('live_trading_authorized')}",
        f"source_gate={state.get('source_gate')}",
        "paper_40bps="
        f"sharpe:{fmt(metrics.get('sharpe'))} "
        f"return:{fmt(metrics.get('total_return'))} "
        f"dd:{fmt(metrics.get('max_drawdown'))} "
        f"rebalances:{fmt(metrics.get('rebalance_event_count'), 0)}",
        f"latest_dt={(state.get('shadow') or {}).get('latest_dt')}",
        f"latest_weights={json.dumps((state.get('shadow') or {}).get('latest_weights') or {}, sort_keys=True)}",
        f"data_fresh={freshness.get('data_fresh')}",
        "checks=" + ",".join(f"{key}:{value}" for key, value in (state.get("checks") or {}).items()),
    ]
    return "\n".join(lines)


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    costs = tuple(float(item.strip()) for item in args.costs_bps.split(",") if item.strip())
    ledger_path = Path(args.ledger_jsonl)
    data_freshness = None
    if not args.skip_data_freshness:
        from scripts.v9_xsec_data_freshness_watchdog import (  # noqa: PLC0415
            append_history,
            build_status,
            parse_symbols,
            write_json as write_watchdog_json,
        )

        freshness_status_path = Path(args.data_freshness_status_json)
        data_freshness = build_status(
            cache_dir=Path(args.cache_dir),
            symbols=parse_symbols(args.data_freshness_symbols),
            timeframe=args.data_freshness_timeframe,
            ledger_path=ledger_path,
            previous_status_path=freshness_status_path,
            max_cache_age_hours=args.max_cache_age_hours,
            min_symbol_coverage=args.min_symbol_coverage,
            max_unchanged_runs=args.max_unchanged_runs,
        )
        append_history(data_freshness, Path(args.data_freshness_history_jsonl))
        write_watchdog_json(data_freshness, freshness_status_path)
        if not data_freshness.get("data_fresh"):
            gate = read_json(Path(args.gate_state))
            state = {
                "kind": "xsec_paper_shadow_state_v1",
                "updated_at": now_utc(),
                "status": "paper_skipped_stale_data",
                "reason": "data_freshness_failed",
                "paper_trading_authorized": bool(gate.get("paper_trading_authorized")),
                "live_trading_authorized": False,
                "source_gate": args.gate_state,
                "data_freshness": data_freshness,
                "signals": [],
                "note": "Paper shadow skipped normal ledger/cost evidence because data freshness failed.",
            }
            if state["paper_trading_authorized"]:
                skipped = append_skip_ledger_marker(
                    path=ledger_path,
                    reason="SKIPPED_STALE_DATA",
                    data_freshness=data_freshness,
                    latest_dt=data_freshness.get("max_latest_dt"),
                    candidate_artifact=((gate.get("candidate") or {}).get("artifact")),
                )
                state["paper_ledger"] = {
                    "path": args.ledger_jsonl,
                    "seq": skipped["seq"],
                    "hash": skipped["hash"],
                    "kind": skipped["kind"],
                }
            write_json(state, Path(args.out_json))
            write_text(format_text(state), Path(args.out_text))
            write_text(format_signals_csv([]), Path(args.signals_csv))
            return state
    state = build_shadow_state(
        gate_state_path=Path(args.gate_state),
        cache_dir=Path(args.cache_dir),
        evaluation_end=resolve_evaluation_end(args.evaluation_end),
        costs_bps=costs,
    )
    if data_freshness is not None:
        state["data_freshness"] = data_freshness
    latest_dt = (state.get("shadow") or {}).get("latest_dt")
    if latest_dt_is_duplicate(ledger_path, str(latest_dt) if latest_dt else None):
        skipped = append_skip_ledger_marker(
            path=ledger_path,
            reason="SKIPPED_DUPLICATE_LATEST_DT",
            data_freshness=data_freshness,
            latest_dt=str(latest_dt),
            candidate_artifact=((state.get("candidate") or {}).get("artifact")),
        )
        state["paper_ledger"] = {
            "path": args.ledger_jsonl,
            "seq": skipped["seq"],
            "hash": skipped["hash"],
            "kind": skipped["kind"],
        }
        state["ledger_skip_reason"] = "duplicate_latest_dt"
        ledger_record_written = {}
    else:
        ledger_record_written = append_ledger(state, ledger_path)
    if ledger_record_written:
        state["paper_ledger"] = {
            "path": args.ledger_jsonl,
            "seq": ledger_record_written["seq"],
            "hash": ledger_record_written["hash"],
            "kind": ledger_record_written["kind"],
        }
        if not args.skip_cost_evidence:
            try:
                from scripts.v9_xsec_cost_evidence import append_cost_evidence  # noqa: PLC0415

                state["cost_evidence"] = append_cost_evidence(
                    state=state,
                    ledger_path=Path(args.ledger_jsonl),
                    out_csv=Path(args.cost_evidence_csv),
                    recorded_at=str(ledger_record_written["recorded_at"]),
                )
            except Exception as exc:  # pragma: no cover - public data should not stop shadow.
                state["cost_evidence"] = {
                    "rows_written": 0,
                    "path": args.cost_evidence_csv,
                    "error": str(exc),
                }
    write_json(state, Path(args.out_json))
    write_text(format_text(state), Path(args.out_text))
    write_text(format_signals_csv(state.get("signals") or []), Path(args.signals_csv))
    if state.get("status") == "paper_complete_live_manual_review_required":
        marker = Path(args.marker_dir) / "FOUND_LIVE_CANARY_REVIEW_REQUIRED.txt"
        write_text(
            "FOUND_LIVE_CANARY_REVIEW_REQUIRED "
            f"{now_utc()} artifact={state['candidate']['artifact']} "
            "live_trading_authorized=False\n",
            marker,
        )
    return state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XSEC paper shadow runner for paper-ready candidates")
    parser.add_argument("--gate-state", default="state/xsec_paper_readiness_gate_state.json")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--evaluation-end", default="now")
    parser.add_argument("--costs-bps", default="20,40,60,80")
    parser.add_argument("--out-json", default="state/xsec_paper_shadow_state.json")
    parser.add_argument("--out-text", default="state/xsec_paper_shadow_state.txt")
    parser.add_argument("--signals-csv", default="artifacts/v9/paper/xsec_paper_shadow_signals.csv")
    parser.add_argument("--ledger-jsonl", default="state/xsec_paper_ledger.jsonl")
    parser.add_argument("--cost-evidence-csv", default="artifacts/v9/paper/xsec_cost_evidence.csv")
    parser.add_argument("--skip-cost-evidence", action="store_true")
    parser.add_argument("--skip-data-freshness", action="store_true")
    parser.add_argument("--data-freshness-status-json", default="artifacts/v9/watchdog/data_freshness_status.json")
    parser.add_argument("--data-freshness-history-jsonl", default="artifacts/v9/watchdog/data_freshness_history.jsonl")
    parser.add_argument("--data-freshness-symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--data-freshness-timeframe", default="1h")
    parser.add_argument("--max-cache-age-hours", type=float, default=6.0)
    parser.add_argument("--min-symbol-coverage", type=float, default=0.90)
    parser.add_argument("--max-unchanged-runs", type=int, default=4)
    parser.add_argument("--marker-dir", default="state")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=3600.0)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    while True:
        state = run_once(args)
        if args.format == "json":
            print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
        else:
            print(format_text(state), flush=True)
        if not args.loop:
            return
        time.sleep(max(1.0, float(args.sleep_sec)))


if __name__ == "__main__":
    main()
