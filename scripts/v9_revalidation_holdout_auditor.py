#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_revalidation_status import build_report as build_revalidation_status  # noqa: E402
from scripts.v9_train_only_holdout_batch import (  # noqa: E402
    compact_post_holdout_probe,
    promotion_decision,
)
from scripts.v9_xsec_data_freshness_watchdog import latest_by_symbol  # noqa: E402
from scripts.v9_xsec_ohlcv_holdout_audit import build_report as build_xsec_holdout_report  # noqa: E402
from scripts.v9_xsec_paper_readiness_gate import shadow_oos_report  # noqa: E402
from v9.contract.simulator import utc_ts  # noqa: E402
from v9.contract.xsec_momentum import load_close_matrix  # noqa: E402


KIND = "v9_revalidation_holdout_auditor_v1"
GROUP_VERDICT_KIND = "v9_revalidation_group_holdout_verdict_v1"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def now_utc() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def canonical_config(config: Any) -> dict[str, Any]:
    out = dict(config or {})
    out.setdefault("n_tranches", 1)
    return out


def config_sig(config: Any) -> str:
    return hashlib.sha1(json.dumps(canonical_config(config), sort_keys=True).encode("utf-8")).hexdigest()[:12]


def first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def accepted_rows(payload: dict[str, Any], max_configs: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in (payload.get("top") or [], payload.get("rows") or []):
        for row in source if isinstance(source, list) else []:
            if not row.get("advance_passed"):
                continue
            cfg = canonical_config(row.get("config"))
            sig = config_sig(cfg)
            if sig in seen:
                continue
            seen.add(sig)
            selected.append({**row, "config": cfg, "config_sig": sig})
            if len(selected) >= max(0, int(max_configs)):
                return selected
    return selected


def candidate_from_row(artifact: str, row: dict[str, Any]) -> dict[str, Any]:
    cost20 = row.get("cost20") or (row.get("selection") or {}).get("cost20") or {}
    cost40 = row.get("cost40") or (row.get("selection") or {}).get("cost40") or {}
    return {
        "artifact": artifact,
        "kind": "xsec_ohlcv",
        "metrics": {
            "sharpe20": first_number(cost20.get("sharpe")),
            "sharpe40": first_number(cost40.get("sharpe")),
        },
        "config": canonical_config(row.get("config")),
    }


def latest_common_end(cache_dir: Path, symbols: tuple[str, ...], timeframe: str) -> pd.Timestamp:
    latest = latest_by_symbol(cache_dir, symbols, timeframe)
    values = [value for value in latest.values() if value is not None]
    if len(values) != len(symbols):
        missing = [symbol for symbol, value in latest.items() if value is None]
        raise ValueError(f"cache missing latest data for symbols: {missing}")
    return pd.Timestamp(min(values), unit="ms", tz="UTC")


def audit_key(payload: dict[str, Any], group: dict[str, Any], params: dict[str, Any]) -> str:
    raw = {
        "kind": GROUP_VERDICT_KIND,
        "group_id": group.get("group_id"),
        "group_plan_fingerprint": group.get("group_plan_fingerprint"),
        "output_json": group.get("output_json"),
        "data_fingerprint": (payload.get("data") or {}).get("fingerprint"),
        "params": params,
    }
    return hashlib.sha1(json.dumps(raw, sort_keys=True).encode("utf-8")).hexdigest()


def verdict_path_for(output_json: str) -> Path:
    path = Path(output_json)
    return path.with_suffix(path.suffix + ".holdout_verdict.json")


def has_group_verdict(group: dict[str, Any]) -> bool:
    existing = read_json(verdict_path_for(str(group.get("output_json") or "")))
    return existing.get("kind") == GROUP_VERDICT_KIND


def normalized_target_path(raw: str) -> str:
    return str(Path(str(raw).strip()))


def output_json_matches_target(output_json: str, targets: set[str]) -> bool:
    if not targets:
        return False
    current = normalized_target_path(output_json)
    for target in targets:
        if current == target:
            return True
        if current.endswith("/" + target) or target.endswith("/" + current):
            return True
    return False


def group_matches_targets(
    group: dict[str, Any],
    *,
    target_group_ids: set[str],
    target_output_jsons: set[str],
) -> bool:
    if not target_group_ids and not target_output_jsons:
        return True
    if str(group.get("group_id") or "") in target_group_ids:
        return True
    return output_json_matches_target(str(group.get("output_json") or ""), target_output_jsons)


def top_reason(results: list[dict[str, Any]]) -> str:
    if any(row.get("promotion_decision") == "paper_candidate_manual_review_required" for row in results):
        return "paper_candidate_manual_review_required"
    if not any(row.get("recent_activity_passed") for row in results):
        return "recent_activity_no_active_configs"
    if any(row.get("holdout_decision") == "holdout_promising_manual_review_required" for row in results):
        return "paper_gate_blocked"
    return "holdout_failed"


def recent_probe_costs(costs_bps: tuple[float, ...]) -> tuple[float, ...]:
    if 40.0 in costs_bps:
        return (40.0,)
    if costs_bps:
        return (float(costs_bps[0]),)
    return (40.0,)


def audit_group(
    group: dict[str, Any],
    *,
    cache_dir: Path,
    holdout_start: str,
    holdout_end: str,
    recent_start: str,
    costs_bps: tuple[float, ...],
    bootstrap_iterations: int,
    max_configs: int,
    min_decay_ratio: float,
    min_recent_active_rebalances: int,
    min_recent_time_in_market: float,
    holdout_authorized: bool,
    force: bool = False,
    skip_existing_any_key: bool = False,
    require_recent_activity_before_holdout: bool = False,
    holdout_builder: Callable[..., dict[str, Any]] = build_xsec_holdout_report,
    probe_builder: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    output_json = str(group.get("output_json") or "")
    artifact = Path(output_json)
    verdict_path = verdict_path_for(output_json)
    params = {
        "holdout_start": holdout_start,
        "holdout_end": holdout_end,
        "recent_start": recent_start,
        "costs_bps": list(costs_bps),
        "bootstrap_iterations": int(bootstrap_iterations),
        "max_configs": int(max_configs),
        "min_decay_ratio": float(min_decay_ratio),
        "min_recent_active_rebalances": int(min_recent_active_rebalances),
        "min_recent_time_in_market": float(min_recent_time_in_market),
        "require_recent_activity_before_holdout": bool(require_recent_activity_before_holdout),
    }
    payload = read_json(artifact)
    key = audit_key(payload, group, params)
    existing = read_json(verdict_path)
    if existing.get("kind") == GROUP_VERDICT_KIND and skip_existing_any_key and not force:
        return {**existing, "audit_status": "skipped_existing"}
    if existing.get("kind") == GROUP_VERDICT_KIND and existing.get("audit_key") == key and not force:
        return {**existing, "audit_status": "skipped_existing"}
    if not holdout_authorized:
        return {
            "kind": GROUP_VERDICT_KIND,
            "created_at": now_utc(),
            "audit_status": "holdout_not_authorized",
            "audit_key": key,
            "group_id": group.get("group_id"),
            "output_json": output_json,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        }

    rows = accepted_rows(payload, max_configs=max_configs)
    results: list[dict[str, Any]] = []
    symbols = tuple(str(symbol) for symbol in (payload.get("symbols") or ((payload.get("data") or {}).get("symbols") or [])))
    probe_costs = recent_probe_costs(costs_bps)
    closes = None
    if probe_builder is None:
        closes = load_close_matrix(
            cache_dir,
            symbols,
            utc_ts(holdout_start),
            utc_ts(holdout_end),
            utc_ts("2100-01-01"),
        )
    for idx, row in enumerate(rows):
        cfg = canonical_config(row.get("config"))
        candidate = candidate_from_row(output_json, row)
        if probe_builder is None:
            probe = shadow_oos_report(
                closes=closes,
                config=cfg,
                evaluation_start=utc_ts(recent_start),
                costs_bps=probe_costs,
            )
        else:
            probe = probe_builder(
                holdout_report={
                    "data": {"symbols": symbols},
                    "target_config": cfg,
                },
                cache_dir=cache_dir,
                warmup_start=holdout_start,
                evaluation_start=recent_start,
                evaluation_end=holdout_end,
                costs_bps=costs_bps,
            )
        probe40 = ((probe.get("costs") or {}).get("40bps") or {})
        recent_activity_passed = (
            int(probe40.get("active_rebalance_event_count") or 0) >= int(min_recent_active_rebalances)
            and float(probe40.get("time_in_market_frac") or 0.0) >= float(min_recent_time_in_market)
        )
        result = {
            "rank": idx + 1,
            "config_sig": row.get("config_sig") or config_sig(cfg),
            "config": cfg,
            "train_sharpe40": candidate["metrics"].get("sharpe40"),
            "recent_activity_passed": bool(recent_activity_passed),
            "recent_probe": compact_post_holdout_probe(probe),
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        }
        if recent_activity_passed or (idx == 0 and not require_recent_activity_before_holdout):
            holdout = holdout_builder(
                artifact=artifact,
                cache_dir=cache_dir,
                split="holdout",
                holdout_start=holdout_start,
                holdout_end=holdout_end,
                costs_bps=costs_bps,
                bootstrap_iterations=bootstrap_iterations,
                holdout_authorized=True,
                target_config=cfg,
            )
            decision, evidence = promotion_decision(
                candidate,
                holdout,
                min_decay_ratio=min_decay_ratio,
                post_holdout_probe=probe,
                require_post_holdout_activity=True,
                min_post_holdout_active_rebalances=min_recent_active_rebalances,
                min_post_holdout_time_in_market=min_recent_time_in_market,
            )
            result.update(
                {
                    "holdout_decision": holdout.get("decision"),
                    "holdout_40bps": (holdout.get("costs") or {}).get("40bps") or {},
                    "promotion_decision": decision,
                    "promotion_evidence": evidence,
                }
            )
        else:
            result["promotion_decision"] = "recent_activity_failed_not_holdout_audited"
        results.append(result)
        if result.get("promotion_decision") == "paper_candidate_manual_review_required":
            break

    paper_candidates = [
        row for row in results if row.get("promotion_decision") == "paper_candidate_manual_review_required"
    ]
    verdict = {
        "kind": GROUP_VERDICT_KIND,
        "created_at": now_utc(),
        "audit_status": "completed",
        "audit_key": key,
        "group_id": group.get("group_id"),
        "preset": group.get("preset"),
        "output_json": output_json,
        "verdict_path": str(verdict_path),
        "decision": "paper_candidate_manual_review_required" if paper_candidates else "not_paper_candidate",
        "reason": top_reason(results),
        "accepted_config_count_scanned": len(rows),
        "recent_active_count": sum(1 for row in results if row.get("recent_activity_passed")),
        "paper_candidate_count": len(paper_candidates),
        "params": params,
        "results": results,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    write_json(verdict, verdict_path)
    return verdict


def build_audit_report(
    *,
    plan_path: Path,
    runner_state_path: Path,
    cache_dir: Path,
    holdout_start: str,
    holdout_end: str,
    recent_start: str,
    costs_bps: tuple[float, ...],
    bootstrap_iterations: int,
    max_groups: int,
    max_configs: int,
    min_decay_ratio: float,
    min_recent_active_rebalances: int,
    min_recent_time_in_market: float,
    holdout_authorized: bool,
    force: bool,
    skip_existing_any_key: bool,
    stop_path: Path,
    require_recent_activity_before_holdout: bool = False,
    target_group_ids: tuple[str, ...] = (),
    target_output_jsons: tuple[str, ...] = (),
    missing_verdicts_first: bool = False,
) -> dict[str, Any]:
    target_group_id_set = {str(item).strip() for item in target_group_ids if str(item).strip()}
    target_output_json_set = {
        normalized_target_path(item)
        for item in target_output_jsons
        if str(item).strip()
    }
    targeted = bool(target_group_id_set or target_output_json_set)
    status = build_revalidation_status(
        plan_path,
        runner_state_path=runner_state_path,
        max_groups=0 if (targeted or missing_verdicts_first) else max_groups,
        include_processes=True,
    )
    groups = list(status.get("groups") or [])
    missing_verdict_groups = [
        group
        for group in groups
        if group.get("status") == "completed_accepted" and not has_group_verdict(group)
    ]
    if targeted:
        groups_for_audit = groups
    elif missing_verdicts_first and missing_verdict_groups:
        groups_for_audit = missing_verdict_groups[:max_groups] if max_groups > 0 else missing_verdict_groups
    elif missing_verdicts_first and max_groups > 0:
        groups_for_audit = groups[:max_groups]
    else:
        groups_for_audit = groups
    verdicts = []
    for group in groups_for_audit:
        if stop_path.exists():
            break
        if not group_matches_targets(
            group,
            target_group_ids=target_group_id_set,
            target_output_jsons=target_output_json_set,
        ):
            continue
        if group.get("status") != "completed_accepted":
            continue
        verdicts.append(
            audit_group(
                group,
                cache_dir=cache_dir,
                holdout_start=holdout_start,
                holdout_end=holdout_end,
                recent_start=recent_start,
                costs_bps=costs_bps,
                bootstrap_iterations=bootstrap_iterations,
                max_configs=max_configs,
                min_decay_ratio=min_decay_ratio,
                min_recent_active_rebalances=min_recent_active_rebalances,
                min_recent_time_in_market=min_recent_time_in_market,
                holdout_authorized=holdout_authorized,
                force=force,
                skip_existing_any_key=skip_existing_any_key,
                require_recent_activity_before_holdout=require_recent_activity_before_holdout,
            )
        )
    paper_candidates = [row for row in verdicts if row.get("paper_candidate_count", 0) > 0]
    return {
        "kind": KIND,
        "created_at": now_utc(),
        "holdout_authorized": bool(holdout_authorized),
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "source_revalidation_status": {
            "plan": str(plan_path),
            "runner_state": str(runner_state_path),
            "status_counts": status.get("status_counts") or {},
            "target_group_ids": sorted(target_group_id_set),
            "target_output_jsons": sorted(target_output_json_set),
            "missing_verdicts_first": bool(missing_verdicts_first),
            "require_recent_activity_before_holdout": bool(require_recent_activity_before_holdout),
        },
        "summary": {
            "accepted_groups_seen": sum(1 for row in groups if row.get("status") == "completed_accepted"),
            "verdict_count": len(verdicts),
            "targeted": targeted,
            "missing_verdicts_first": bool(missing_verdicts_first),
            "missing_verdict_count_seen": len(missing_verdict_groups),
            "selected_for_audit_count": len(groups_for_audit),
            "target_matched_count": sum(
                1
                for row in groups
                if group_matches_targets(
                    row,
                    target_group_ids=target_group_id_set,
                    target_output_jsons=target_output_json_set,
                )
            ),
            "paper_candidate_group_count": len(paper_candidates),
            "reason_counts": {
                reason: sum(1 for row in verdicts if row.get("reason") == reason)
                for reason in sorted({str(row.get("reason")) for row in verdicts})
            },
        },
        "verdicts": verdicts,
    }


def first_paper_candidate(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for verdict in report.get("verdicts") or []:
        if int(verdict.get("paper_candidate_count") or 0) <= 0:
            continue
        for result in verdict.get("results") or []:
            if result.get("promotion_decision") == "paper_candidate_manual_review_required":
                return verdict, result
    return None


def write_validated_marker(report: dict[str, Any], state_dir: Path) -> None:
    found = first_paper_candidate(report)
    state_dir.mkdir(parents=True, exist_ok=True)
    found_marker = state_dir / "FOUND_VALIDATED_CANDIDATE.txt"
    none_marker = state_dir / "NO_VALIDATED_CANDIDATE.txt"
    if found is None:
        found_marker.unlink(missing_ok=True)
        summary = report.get("summary") or {}
        none_marker.write_text(
            "NO_VALIDATED_CANDIDATE "
            f"{now_utc()} source=revalidation_holdout_auditor "
            f"paper_candidate_group_count={summary.get('paper_candidate_group_count', 0)} "
            f"reason_counts={json.dumps(summary.get('reason_counts', {}), sort_keys=True)} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        return
    verdict, result = found
    none_marker.unlink(missing_ok=True)
    found_marker.write_text(
        "FOUND_VALIDATED_CANDIDATE "
        f"{now_utc()} source=revalidation_holdout_auditor "
        f"group_id={verdict.get('group_id')} "
        f"artifact={verdict.get('output_json')} "
        f"verdict={verdict.get('verdict_path')} "
        f"config_sig={result.get('config_sig')} "
        "paper_trading_authorized=False live_trading_authorized=False\n"
    )


def default_holdout_end(cache_dir: Path, symbols: tuple[str, ...], timeframe: str) -> str:
    return latest_common_end(cache_dir, symbols, timeframe).strftime("%Y-%m-%d %H:%M:%S")


def default_recent_start(holdout_end: str, recent_days: int) -> str:
    end = pd.Timestamp(holdout_end, tz="UTC") if pd.Timestamp(holdout_end).tzinfo is None else pd.Timestamp(holdout_end).tz_convert("UTC")
    return (end - timedelta(days=max(1, int(recent_days)))).strftime("%Y-%m-%d %H:%M:%S")


def parse_costs(raw: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in raw.split(",") if item.strip())


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit accepted revalidation groups through holdout and recent-activity gates")
    parser.add_argument("--plan", default="artifacts/v9/revalidation/v9_candidate_revalidation_plan.json")
    parser.add_argument("--runner-state", default="artifacts/v9/revalidation/runner_state.json")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--symbols", default="ADAUSDT,AVAXUSDT,BNBUSDT,BTCUSDT,ETHUSDT,LINKUSDT,SOLUSDT,XRPUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--holdout-start", default="2024-07-01")
    parser.add_argument("--holdout-end", default="")
    parser.add_argument("--recent-start", default="")
    parser.add_argument("--recent-days", type=int, default=45)
    parser.add_argument("--costs-bps", default="20,40,60,80")
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--max-groups", type=int, default=10)
    parser.add_argument("--max-configs", type=int, default=50)
    parser.add_argument("--min-decay-ratio", type=float, default=0.50)
    parser.add_argument("--min-recent-active-rebalances", type=int, default=1)
    parser.add_argument("--min-recent-time-in-market", type=float, default=0.0)
    parser.add_argument("--holdout-authorized", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-existing-any-key", action="store_true")
    parser.add_argument("--require-recent-activity-before-holdout", action="store_true")
    parser.add_argument("--target-group-id", action="append", default=[])
    parser.add_argument("--target-output-json", action="append", default=[])
    parser.add_argument("--missing-verdicts-first", action="store_true")
    parser.add_argument("--stop-path", default="control/STOP")
    parser.add_argument("--out-json", default="artifacts/v9/revalidation/holdout_auditor_report.json")
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        f"kind={report.get('kind')}",
        f"holdout_authorized={report.get('holdout_authorized')} paper={report.get('paper_trading_authorized')} live={report.get('live_trading_authorized')}",
        f"summary={json.dumps(summary, sort_keys=True)}",
    ]
    for verdict in report.get("verdicts") or []:
        lines.append(
            f"group={verdict.get('group_id')} status={verdict.get('audit_status')} decision={verdict.get('decision')} "
            f"reason={verdict.get('reason')} scanned={verdict.get('accepted_config_count_scanned')} "
            f"recent_active={verdict.get('recent_active_count')} paper_candidates={verdict.get('paper_candidate_count')} "
            f"verdict={verdict.get('verdict_path')}"
        )
    return "\n".join(lines)


def main() -> None:
    args = build_arg_parser().parse_args()
    cache_dir = Path(args.cache_dir)
    symbols = tuple(item.strip().upper() for item in args.symbols.replace(",", " ").split() if item.strip())
    holdout_end = args.holdout_end or default_holdout_end(cache_dir, symbols, args.timeframe)
    recent_start = args.recent_start or default_recent_start(holdout_end, args.recent_days)
    report = build_audit_report(
        plan_path=Path(args.plan),
        runner_state_path=Path(args.runner_state),
        cache_dir=cache_dir,
        holdout_start=args.holdout_start,
        holdout_end=holdout_end,
        recent_start=recent_start,
        costs_bps=parse_costs(args.costs_bps),
        bootstrap_iterations=int(args.bootstrap_iterations),
        max_groups=int(args.max_groups),
        max_configs=int(args.max_configs),
        min_decay_ratio=float(args.min_decay_ratio),
        min_recent_active_rebalances=int(args.min_recent_active_rebalances),
        min_recent_time_in_market=float(args.min_recent_time_in_market),
        holdout_authorized=bool(args.holdout_authorized),
        force=bool(args.force),
        skip_existing_any_key=bool(args.skip_existing_any_key),
        require_recent_activity_before_holdout=bool(args.require_recent_activity_before_holdout),
        stop_path=Path(args.stop_path),
        target_group_ids=tuple(args.target_group_id or ()),
        target_output_jsons=tuple(args.target_output_json or ()),
        missing_verdicts_first=bool(args.missing_verdicts_first),
    )
    write_json(report, Path(args.out_json))
    write_validated_marker(report, Path(args.state_dir))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(report))


if __name__ == "__main__":
    main()
