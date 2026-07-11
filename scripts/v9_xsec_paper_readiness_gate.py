#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.simulator import utc_ts  # noqa: E402
from v9.contract.xsec_momentum import load_close_matrix, sharpe  # noqa: E402
from v9.contract.xsec_ohlcv_factory import (  # noqa: E402
    ACTIVE_EXPOSURE_THRESHOLD,
    data_fingerprint,
    exposure_scale,
    long_only_weights,
    market_filter,
    max_drawdown_from_returns,
    ohlcv_config_from_dict,
    score_matrix,
)


DEFAULT_SYMBOLS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            return float(value)
    return None


def number_or(value: Any, default: float) -> float:
    found = first_number(value)
    return default if found is None else found


def paper_candidate_from_batch(batch: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for row in batch.get("holdout_results", [])
        if row.get("promotion_decision") == "paper_candidate_manual_review_required"
    ]
    if not rows:
        raise ValueError("holdout batch has no paper_candidate_manual_review_required row")
    rows.sort(
        key=lambda row: (
            -float(((row.get("promotion_evidence") or {}).get("holdout_sharpe_decay_ratio") or -999.0)),
            str(row.get("artifact")),
        )
    )
    return rows[0]


def paper_gate_payload() -> dict[str, Any]:
    return {
        "minimum_duration_weeks": 12,
        "minimum_rebalance_events": 9,
        "max_paper_drawdown": 0.15,
        "required_shadow_signal_match": 1.0,
        "max_realized_cost_bps": 40.0,
        "note": "Paper readiness only. Live canary requires paper gate completion, execution controls, reconciliation, kill switch, and explicit live authorization.",
    }


def shadow_oos_report(
    *,
    closes: pd.DataFrame,
    config: dict[str, Any],
    evaluation_start: pd.Timestamp,
    costs_bps: tuple[float, ...],
) -> dict[str, Any]:
    cfg = ohlcv_config_from_dict(config)
    symbols = [col for col in closes.columns if col != "dt"]
    scores = score_matrix(closes, cfg)
    allowed = market_filter(closes, cfg)
    returns = closes[symbols].pct_change().shift(-1)
    eval_returns = returns.iloc[: len(closes) - 1].copy()
    eval_returns.index = pd.to_datetime(closes["dt"].iloc[: len(closes) - 1])
    eval_equal_weight = eval_returns.mean(axis=1).fillna(0.0)
    eval_equal_weight = eval_equal_weight[eval_equal_weight.index >= evaluation_start]

    def run_path(cost_bps: float) -> dict[str, Any]:
        weights = {sym: 0.0 for sym in symbols}
        tranche_weights = [{sym: 0.0 for sym in symbols} for _ in range(cfg.n_tranches)]
        tranche_offsets = [
            int((idx * cfg.rebalance_h) // cfg.n_tranches) % cfg.rebalance_h
            for idx in range(cfg.n_tranches)
        ]
        rows = []
        rebalances = []
        past_net_returns: list[float] = []
        latest_rebalance_dt: str | None = None
        equity = 1.0
        peak_equity = 1.0
        risk_off_until = -1
        risk_off_event_count = 0
        risk_stop_exit_cost = 0.0
        risk_stop_exit_turnover = 0.0

        for idx in range(len(closes) - 1):
            ts = pd.Timestamp(closes["dt"].iloc[idx])
            current_drawdown = 1.0 - equity / peak_equity if peak_equity > 0.0 else 0.0
            stop_triggered = (
                cfg.drawdown_stop > 0.0
                and idx >= risk_off_until
                and current_drawdown >= cfg.drawdown_stop
            )
            if stop_triggered:
                risk_off_until = idx + max(1, int(cfg.cooldown_h))
                risk_off_event_count += 1
            risk_off = idx < risk_off_until
            old_weights = dict(weights)
            due_rebalance = False
            if stop_triggered:
                tranche_weights = [{sym: 0.0 for sym in symbols} for _ in range(cfg.n_tranches)]
                due_rebalance = True
            else:
                for tranche_idx, offset in enumerate(tranche_offsets):
                    if idx < offset or (idx - offset) % cfg.rebalance_h != 0:
                        continue
                    due_rebalance = True
                    target = (
                        {sym: 0.0 for sym in symbols}
                        if risk_off
                        else long_only_weights(scores.iloc[idx], cfg, bool(allowed.iloc[idx]))
                    )
                    if target is not None:
                        scale = exposure_scale(past_net_returns, cfg.vol_target_ann)
                        tranche_weights[tranche_idx] = {
                            sym: target[sym] * scale / cfg.n_tranches for sym in symbols
                        }
            if due_rebalance:
                weights = {sym: sum(tranche[sym] for tranche in tranche_weights) for sym in symbols}
                turnover = sum(abs(weights[sym] - old_weights[sym]) for sym in symbols)
                cost = turnover * float(cost_bps) / 10000.0
                if stop_triggered:
                    risk_stop_exit_cost += cost
                    risk_stop_exit_turnover += turnover
                rebalances.append(
                    {
                        "dt": ts,
                        "turnover": turnover,
                        "cost": cost,
                        "gross_exposure": sum(abs(value) for value in weights.values()),
                        "reason": "risk_stop" if stop_triggered else ("risk_off" if risk_off else "rebalance"),
                    }
                )
                latest_rebalance_dt = ts.isoformat()
            else:
                cost = 0.0
            row_rets = returns.iloc[idx].fillna(0.0)
            gross = sum(weights[sym] * float(row_rets[sym]) for sym in symbols)
            net = gross - cost
            equity *= 1.0 + net
            peak_equity = max(peak_equity, equity)
            rows.append(
                {
                    "dt": ts,
                    "gross_return": gross,
                    "net_return": net,
                    "cost": cost,
                    "gross_exposure": sum(abs(value) for value in weights.values()),
                    "risk_off": bool(risk_off),
                    "stop_triggered": bool(stop_triggered),
                }
            )
            past_net_returns.append(net)

        ret = pd.DataFrame(rows).set_index("dt")
        reb = (
            pd.DataFrame(rebalances).set_index("dt")
            if rebalances
            else pd.DataFrame(columns=["turnover", "cost", "gross_exposure", "reason"])
        )
        return {
            "ret": ret,
            "reb": reb,
            "latest_rebalance_dt": latest_rebalance_dt,
            "latest_weights": {symbol: float(weight) for symbol, weight in sorted(weights.items())},
            "latest_gross_exposure": float(sum(abs(value) for value in weights.values())),
            "risk_off_event_count": int(risk_off_event_count),
            "risk_off_hours": int(ret["risk_off"].sum()) if len(ret) else 0,
            "time_in_risk_off_frac": float(ret["risk_off"].mean()) if len(ret) else 0.0,
            "risk_stop_exit_cost": float(risk_stop_exit_cost),
            "risk_stop_exit_turnover": float(risk_stop_exit_turnover),
        }

    reference_cost = 40.0 if 40.0 in costs_bps else float(costs_bps[0])
    reference_path: dict[str, Any] | None = None
    costs: dict[str, dict[str, Any]] = {}
    for cost_bps in costs_bps:
        path = run_path(float(cost_bps))
        if float(cost_bps) == reference_cost:
            reference_path = path
        ret = path["ret"]
        reb = path["reb"]
        eval_ret = ret[ret.index >= evaluation_start].copy()
        eval_reb = reb[reb.index >= evaluation_start].copy() if len(reb) else reb
        active_exposure = eval_ret["gross_exposure"] > ACTIVE_EXPOSURE_THRESHOLD
        active_rebalances = (
            eval_reb["gross_exposure"] > ACTIVE_EXPOSURE_THRESHOLD
            if len(eval_reb)
            else pd.Series(dtype=bool)
        )
        hourly = eval_ret["net_return"]
        period = (1.0 + hourly).resample(f"{cfg.rebalance_h}h").prod() - 1.0
        daily = (1.0 + hourly).resample("1D").prod() - 1.0
        ew_period = (1.0 + eval_equal_weight).resample(f"{cfg.rebalance_h}h").prod() - 1.0
        ew_dd = max_drawdown_from_returns(eval_equal_weight)
        dd = max_drawdown_from_returns(hourly)
        strategy_sharpe = sharpe(period, 8760.0 / cfg.rebalance_h)
        ew_sharpe = sharpe(ew_period, 8760.0 / cfg.rebalance_h)
        costs[f"{int(cost_bps)}bps"] = {
            "sharpe": strategy_sharpe,
            "daily_sharpe": sharpe(daily, 365.0),
            "total_return": float((1.0 + hourly).prod() - 1.0) if len(hourly) else 0.0,
            "max_drawdown": dd,
            "period_count": int(len(period)),
            "daily_count": int(len(daily)),
            "rebalance_event_count": int(len(eval_reb)),
            "active_rebalance_event_count": int(active_rebalances.sum()) if len(active_rebalances) else 0,
            "time_in_market_frac": float(active_exposure.mean()) if len(active_exposure) else 0.0,
            "daily_turnover": float(eval_reb["turnover"].resample("1D").sum().mean()) if len(eval_reb) else 0.0,
            "avg_gross_exposure": float(eval_ret["gross_exposure"].mean()) if len(eval_ret) else 0.0,
            "realized_daily_vol_ann": float(daily.std(ddof=0) * math.sqrt(365.0)) if len(daily) else 0.0,
            "risk_off_event_count": int(path["risk_off_event_count"]),
            "risk_off_hours": int(path["risk_off_hours"]),
            "time_in_risk_off_frac": float(path["time_in_risk_off_frac"]),
            "risk_stop_exit_cost": float(path["risk_stop_exit_cost"]),
            "risk_stop_exit_turnover": float(path["risk_stop_exit_turnover"]),
            "equal_weight_benchmark": {
                "sharpe": ew_sharpe,
                "total_return": float((1.0 + eval_equal_weight).prod() - 1.0) if len(eval_equal_weight) else 0.0,
                "max_drawdown": ew_dd,
                "sharpe_excess": strategy_sharpe - ew_sharpe,
                "drawdown_ratio": dd / ew_dd if ew_dd > 0 else 1.0,
            },
        }
    if reference_path is None:
        reference_path = run_path(reference_cost)
    return {
        "kind": "xsec_shadow_oos_v1",
        "config": config,
        "evaluation_start": evaluation_start.isoformat(),
        "latest_dt": pd.Timestamp(closes["dt"].iloc[-1]).isoformat(),
        "latest_rebalance_dt": reference_path["latest_rebalance_dt"],
        "reference_cost_bps": reference_cost,
        "latest_weights": reference_path["latest_weights"],
        "latest_gross_exposure": reference_path["latest_gross_exposure"],
        "costs": costs,
    }


def paper_decision(
    *,
    candidate: dict[str, Any],
    holdout_report: dict[str, Any],
    shadow_report: dict[str, Any],
    min_decay_ratio: float,
    min_benchmark_excess: float,
    max_holdout_dd: float,
    max_post_oos_dd: float,
    min_post_oos_rebalances: int,
    max_realized_vol_multiple: float,
) -> tuple[str, dict[str, bool]]:
    evidence = candidate.get("promotion_evidence") or {}
    holdout_40 = (holdout_report.get("costs") or {}).get("40bps") or {}
    holdout_benchmark = holdout_40.get("equal_weight_benchmark") or {}
    shadow_40 = (shadow_report.get("costs") or {}).get("40bps") or {}
    target_vol = float((candidate.get("candidate_config") or {}).get("vol_target_ann") or 0.0)
    realized_vol = number_or(shadow_40.get("realized_daily_vol_ann"), 0.0)
    max_allowed_vol = target_vol * max_realized_vol_multiple if target_vol > 0 else float("inf")
    benchmark_excess = number_or(
        holdout_benchmark.get("sharpe_excess"),
        number_or(holdout_40.get("benchmark_sharpe_excess"), -999.0),
    )
    checks = {
        "candidate_is_paper_review_required": candidate.get("promotion_decision") == "paper_candidate_manual_review_required",
        "holdout_decay_ge_min": number_or(evidence.get("holdout_sharpe_decay_ratio"), -999.0) >= min_decay_ratio,
        "holdout_40bps_sharpe_positive": number_or(holdout_40.get("sharpe"), -999.0) > 0.0,
        "holdout_40bps_return_positive": number_or(holdout_40.get("total_return"), -999.0) > 0.0,
        "holdout_40bps_drawdown_le_max": number_or(holdout_40.get("max_drawdown"), 999.0) <= max_holdout_dd,
        "holdout_40bps_benchmark_excess_ge_min": benchmark_excess >= min_benchmark_excess,
        "post_oos_has_min_rebalances": int(shadow_40.get("rebalance_event_count") or 0) >= min_post_oos_rebalances,
        "post_oos_has_min_active_rebalances": int(shadow_40.get("active_rebalance_event_count") or 0)
        >= min_post_oos_rebalances,
        "post_oos_time_in_market_positive": number_or(shadow_40.get("time_in_market_frac"), 0.0) > 0.0,
        "post_oos_drawdown_le_max": number_or(shadow_40.get("max_drawdown"), 999.0) <= max_post_oos_dd,
        "post_oos_realized_vol_within_limit": realized_vol <= max_allowed_vol,
    }
    if all(checks.values()):
        return "paper_ready", checks
    if checks["candidate_is_paper_review_required"] and checks["holdout_decay_ge_min"]:
        return "paper_manual_review_required", checks
    return "paper_blocked", checks


def build_gate_report(
    *,
    holdout_batch_path: Path,
    cache_dir: Path,
    warmup_start: str,
    evaluation_start: str,
    evaluation_end: str,
    costs_bps: tuple[float, ...],
    min_decay_ratio: float,
    min_benchmark_excess: float,
    max_holdout_dd: float,
    max_post_oos_dd: float,
    min_post_oos_rebalances: int,
    max_realized_vol_multiple: float,
) -> dict[str, Any]:
    batch = read_json(holdout_batch_path)
    try:
        candidate = paper_candidate_from_batch(batch)
    except ValueError:
        return {
            "kind": "xsec_paper_readiness_gate_v1",
            "created_at": now_utc(),
            "decision": "paper_blocked_no_candidate",
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "source_holdout_batch": str(holdout_batch_path),
            "source_holdout_report": None,
            "candidate": {},
            "thresholds": {
                "min_decay_ratio": min_decay_ratio,
                "min_benchmark_excess": min_benchmark_excess,
                "max_holdout_dd": max_holdout_dd,
                "max_post_oos_dd": max_post_oos_dd,
                "min_post_oos_rebalances": min_post_oos_rebalances,
                "max_realized_vol_multiple": max_realized_vol_multiple,
            },
            "checks": {"holdout_batch_has_paper_candidate": False},
            "holdout_40bps": {},
            "post_holdout_shadow_oos": {},
            "data": {
                "warmup_start": warmup_start,
                "evaluation_start": evaluation_start,
                "evaluation_end": evaluation_end,
                "source_holdout_status_counts": (batch.get("summary") or {}).get("status_counts") or {},
            },
            "paper_gate": paper_gate_payload(),
        }
    holdout_report = read_json(Path(candidate["holdout_report_json"]))
    closes = load_close_matrix(
        cache_dir,
        tuple((holdout_report.get("data") or {}).get("symbols") or DEFAULT_SYMBOLS),
        utc_ts(warmup_start),
        utc_ts(evaluation_end),
        utc_ts("2100-01-01"),
    )
    shadow = shadow_oos_report(
        closes=closes,
        config=candidate["candidate_config"],
        evaluation_start=utc_ts(evaluation_start),
        costs_bps=costs_bps,
    )
    decision, checks = paper_decision(
        candidate=candidate,
        holdout_report=holdout_report,
        shadow_report=shadow,
        min_decay_ratio=min_decay_ratio,
        min_benchmark_excess=min_benchmark_excess,
        max_holdout_dd=max_holdout_dd,
        max_post_oos_dd=max_post_oos_dd,
        min_post_oos_rebalances=min_post_oos_rebalances,
        max_realized_vol_multiple=max_realized_vol_multiple,
    )
    return {
        "kind": "xsec_paper_readiness_gate_v1",
        "created_at": now_utc(),
        "decision": decision,
        "paper_trading_authorized": decision == "paper_ready",
        "live_trading_authorized": False,
        "source_holdout_batch": str(holdout_batch_path),
        "source_holdout_report": candidate.get("holdout_report_json"),
        "candidate": {
            "artifact": candidate.get("artifact"),
            "config": candidate.get("candidate_config"),
            "promotion_evidence": candidate.get("promotion_evidence"),
        },
        "thresholds": {
            "min_decay_ratio": min_decay_ratio,
            "min_benchmark_excess": min_benchmark_excess,
            "max_holdout_dd": max_holdout_dd,
            "max_post_oos_dd": max_post_oos_dd,
            "min_post_oos_rebalances": min_post_oos_rebalances,
            "max_realized_vol_multiple": max_realized_vol_multiple,
        },
        "checks": checks,
        "holdout_40bps": (holdout_report.get("costs") or {}).get("40bps") or {},
        "post_holdout_shadow_oos": shadow,
        "data": {
            "warmup_start": warmup_start,
            "evaluation_start": evaluation_start,
            "evaluation_end": evaluation_end,
            "fingerprint": data_fingerprint(closes),
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
        },
        "paper_gate": paper_gate_payload(),
    }


def format_text(report: dict[str, Any]) -> str:
    shadow_40 = ((report.get("post_holdout_shadow_oos") or {}).get("costs") or {}).get("40bps") or {}
    benchmark = shadow_40.get("equal_weight_benchmark") or {}
    holdout = report.get("holdout_40bps") or {}
    holdout_bench = holdout.get("equal_weight_benchmark") or {}
    holdout_excess = first_number(holdout_bench.get("sharpe_excess"), holdout.get("benchmark_sharpe_excess"))
    lines = [
        f"decision={report['decision']}",
        f"safety=paper:{report['paper_trading_authorized']} live:{report['live_trading_authorized']}",
        f"source_holdout_batch={report['source_holdout_batch']}",
        f"source_holdout_report={report['source_holdout_report']}",
        "holdout_40bps="
        f"sharpe:{fmt(holdout.get('sharpe'))} "
        f"return:{fmt(holdout.get('total_return'))} "
        f"dd:{fmt(holdout.get('max_drawdown'))} "
        f"benchmark_excess:{fmt(holdout_excess)}",
        "post_oos_40bps="
        f"sharpe:{fmt(shadow_40.get('sharpe'))} "
        f"daily_sharpe:{fmt(shadow_40.get('daily_sharpe'))} "
        f"return:{fmt(shadow_40.get('total_return'))} "
        f"dd:{fmt(shadow_40.get('max_drawdown'))} "
        f"daily_vol:{fmt(shadow_40.get('realized_daily_vol_ann'))} "
        f"rebalances:{fmt(shadow_40.get('rebalance_event_count'), 0)} "
        f"active_rebalances:{fmt(shadow_40.get('active_rebalance_event_count'), 0)} "
        f"time_in_market:{fmt(shadow_40.get('time_in_market_frac'))} "
        f"risk_off:{fmt(shadow_40.get('risk_off_event_count'), 0)} "
        f"ew_sharpe:{fmt(benchmark.get('sharpe'))} "
        f"ew_return:{fmt(benchmark.get('total_return'))} "
        f"excess:{fmt(benchmark.get('sharpe_excess'))}",
        "checks=" + ",".join(f"{key}:{value}" for key, value in report["checks"].items()),
        "paper_gate="
        f"weeks:{report['paper_gate']['minimum_duration_weeks']} "
        f"rebalances:{report['paper_gate']['minimum_rebalance_events']} "
        f"max_dd:{report['paper_gate']['max_paper_drawdown']} "
        f"max_cost_bps:{report['paper_gate']['max_realized_cost_bps']}",
    ]
    return "\n".join(lines)


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def write_marker(report: dict[str, Any], state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    found_marker = state_dir / "FOUND_PAPER_READY.txt"
    review_marker = state_dir / "PAPER_REVIEW_REQUIRED.txt"
    if report.get("paper_trading_authorized"):
        review_marker.unlink(missing_ok=True)
        found_marker.write_text(
            "FOUND_PAPER_READY "
            f"{now_utc()} artifact={report['candidate']['artifact']} "
            f"paper_gate_decision={report['decision']} "
            "live_trading_authorized=False\n"
        )
    else:
        found_marker.unlink(missing_ok=True)
        artifact = (report.get("candidate") or {}).get("artifact")
        review_marker.write_text(
            "PAPER_REVIEW_REQUIRED "
            f"{now_utc()} artifact={artifact or 'NONE'} "
            f"decision={report['decision']} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper-readiness gate for validated XSEC holdout candidates")
    parser.add_argument("--holdout-batch", default="state/v9_holdout_protocol_state.json")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--warmup-start", default="2024-07-01")
    parser.add_argument("--evaluation-start", default="2026-06-01")
    parser.add_argument("--evaluation-end", default="2026-07-10 00:00:00")
    parser.add_argument("--costs-bps", default="20,40,60,80")
    parser.add_argument("--min-decay-ratio", type=float, default=0.50)
    parser.add_argument("--min-benchmark-excess", type=float, default=0.50)
    parser.add_argument("--max-holdout-dd", type=float, default=0.25)
    parser.add_argument("--max-post-oos-dd", type=float, default=0.15)
    parser.add_argument("--min-post-oos-rebalances", type=int, default=1)
    parser.add_argument("--max-realized-vol-multiple", type=float, default=3.0)
    parser.add_argument("--out-json", default="artifacts/v9/reviews/XSEC_PAPER_READINESS_GATE.json")
    parser.add_argument("--out-text", default="artifacts/v9/reviews/XSEC_PAPER_READINESS_GATE.txt")
    parser.add_argument("--state-out", default="state/xsec_paper_readiness_gate_state.json")
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    costs = tuple(float(item.strip()) for item in args.costs_bps.split(",") if item.strip())
    report = build_gate_report(
        holdout_batch_path=Path(args.holdout_batch),
        cache_dir=Path(args.cache_dir),
        warmup_start=args.warmup_start,
        evaluation_start=args.evaluation_start,
        evaluation_end=args.evaluation_end,
        costs_bps=costs,
        min_decay_ratio=args.min_decay_ratio,
        min_benchmark_excess=args.min_benchmark_excess,
        max_holdout_dd=args.max_holdout_dd,
        max_post_oos_dd=args.max_post_oos_dd,
        min_post_oos_rebalances=args.min_post_oos_rebalances,
        max_realized_vol_multiple=args.max_realized_vol_multiple,
    )
    write_json(report, Path(args.out_json))
    write_json(report, Path(args.state_out))
    text = format_text(report)
    write_text(text, Path(args.out_text))
    write_marker(report, Path(args.state_dir))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text)


if __name__ == "__main__":
    main()
