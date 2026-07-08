#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def accepted_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in payload.get("rows", []) if row.get("advance_passed")]


def top_pass_config(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = accepted_rows(payload)
    if not rows:
        return None
    return rows[0].get("config", {})


def same_config(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def find_config_row(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    for row in payload.get("rows", []):
        if same_config(row.get("config", {}), config):
            return row
    return None


def metric(row: dict[str, Any] | None, segment: str, cost: str, key: str) -> Any:
    if not row:
        return None
    block = ((row.get(segment) or {}).get(cost) or {})
    return block.get(key)


def bool_metric(row: dict[str, Any] | None, key: str) -> bool:
    return bool((row or {}).get(key))


def artifact_label(path: Path, payload: dict[str, Any]) -> str:
    train_window = payload.get("train_window") or {}
    start = train_window.get("start") or ((payload.get("data") or {}).get("first_dt"))
    end = train_window.get("end") or ((payload.get("data") or {}).get("last_dt"))
    return f"{path.name}:{start}->{end}"


def artifact_summary(path: Path, target_config: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(path)
    row = find_config_row(payload, target_config)
    summary = payload.get("summary", {}) or {}
    data = payload.get("data", {}) or {}
    selection_validation = payload.get("selection_validation", {}) or {}
    drop_one = (row or {}).get("drop_one_lookback") or {}
    return {
        "artifact": str(path),
        "label": artifact_label(path, payload),
        "kind": payload.get("kind"),
        "data_fingerprint": data.get("fingerprint"),
        "rows": int(summary.get("rows") or len(payload.get("rows", []))),
        "pass_count": int(summary.get("pass_count") or len(accepted_rows(payload))),
        "accepted_train_only": bool(summary.get("accepted_train_only")),
        "target_config_found": row is not None,
        "target_advance_passed": bool_metric(row, "advance_passed"),
        "selection_sharpe20": metric(row, "selection", "cost20", "sharpe"),
        "selection_sharpe40": metric(row, "selection", "cost40", "sharpe"),
        "selection_return20": metric(row, "selection", "cost20", "total_return"),
        "selection_drawdown20": metric(row, "selection", "cost20", "max_drawdown"),
        "selection_bootstrap_p5": metric(row, "selection", "cost20", "bootstrap_30d_sharpe_p5"),
        "selection_positive_symbols": metric(row, "selection", "cost20", "positive_symbol_count"),
        "selection_symbol_count": metric(row, "selection", "cost20", "symbol_count"),
        "validation_sharpe20": metric(row, "validation", "cost20", "sharpe"),
        "validation_sharpe40": metric(row, "validation", "cost40", "sharpe"),
        "validation_return20": metric(row, "validation", "cost20", "total_return"),
        "validation_return40": metric(row, "validation", "cost40", "total_return"),
        "validation_drawdown20": metric(row, "validation", "cost20", "max_drawdown"),
        "validation_drawdown40": metric(row, "validation", "cost40", "max_drawdown"),
        "validation_positive_symbols": metric(row, "validation", "cost20", "positive_symbol_count"),
        "validation_symbol_count": metric(row, "validation", "cost20", "symbol_count"),
        "drop_one_passed": bool(drop_one.get("passed")),
        "prior_trials": selection_validation.get("prior_trials"),
        "effective_trials": selection_validation.get("effective_trials"),
        "holdout_authorized": bool(summary.get("holdout_authorized")),
        "paper_trading_authorized": bool(summary.get("paper_trading_authorized")),
        "live_trading_authorized": bool(summary.get("live_trading_authorized")),
    }


def number_values(rows: list[dict[str, Any]], key: str, passed_only: bool = False) -> list[float]:
    out: list[float] = []
    for row in rows:
        if passed_only and not row.get("target_advance_passed"):
            continue
        value = row.get(key)
        if isinstance(value, (int, float)):
            out.append(float(value))
    return out


def min_or_none(values: list[float]) -> float | None:
    return min(values) if values else None


def build_report(paths: list[Path], target_artifact: Path | None = None) -> dict[str, Any]:
    if not paths:
        raise ValueError("at least one artifact is required")
    payloads = [(path, read_json(path)) for path in paths]
    if target_artifact is not None:
        target_payload = read_json(target_artifact)
        target_config = top_pass_config(target_payload)
        source = str(target_artifact)
    else:
        target_config = None
        source = None
        for path, payload in payloads:
            target_config = top_pass_config(payload)
            if target_config:
                source = str(path)
                break
    if not target_config:
        raise ValueError("could not find an accepted train-only config to audit")

    rows = [artifact_summary(path, target_config) for path, _payload in payloads]
    found_rows = [row for row in rows if row["target_config_found"]]
    pass_rows = [row for row in found_rows if row["target_advance_passed"]]
    safety_clear = not any(row["holdout_authorized"] or row["paper_trading_authorized"] or row["live_trading_authorized"] for row in rows)
    pass_windows = len(pass_rows)
    found_windows = len(found_rows)
    validation_sharpe20_min = min_or_none(number_values(pass_rows, "validation_sharpe20"))
    validation_sharpe40_min = min_or_none(number_values(pass_rows, "validation_sharpe40"))
    validation_drawdown20_max = max(number_values(pass_rows, "validation_drawdown20") or [0.0])
    validation_return40_min = min_or_none(number_values(pass_rows, "validation_return40"))
    drop_one_pass_windows = sum(1 for row in pass_rows if row["drop_one_passed"])
    cost40_positive_windows = sum(
        1 for row in pass_rows if isinstance(row.get("validation_return40"), (int, float)) and float(row["validation_return40"]) > 0.0
    )
    checks = {
        "target_config_seen_in_at_least_2_windows": found_windows >= 2,
        "target_config_passed_at_least_2_windows": pass_windows >= 2,
        "all_pass_windows_drop_one_stable": bool(pass_rows) and drop_one_pass_windows == pass_windows,
        "all_pass_windows_validation_40bps_positive": bool(pass_rows) and cost40_positive_windows == pass_windows,
        "min_validation_sharpe20_ge_1_0": validation_sharpe20_min is not None and validation_sharpe20_min >= 1.0,
        "max_validation_drawdown20_le_20pct": validation_drawdown20_max <= 0.20,
        "train_only_safety_flags_clear": safety_clear,
    }
    robustness_passed = all(checks.values())
    if robustness_passed:
        decision = "promising_train_only_robustness_manual_review_required"
    elif pass_windows >= 2 and safety_clear:
        decision = "mixed_train_only_robustness_manual_review_required"
    else:
        decision = "weak_train_only_robustness_do_not_promote"
    return {
        "kind": "tsmom_train_only_candidate_robustness_v1",
        "decision": decision,
        "target_config_source": source,
        "target_config": target_config,
        "artifact_count": len(paths),
        "target_config_found_windows": found_windows,
        "target_config_pass_windows": pass_windows,
        "drop_one_pass_windows": drop_one_pass_windows,
        "cost40_positive_pass_windows": cost40_positive_windows,
        "validation_sharpe20_min_pass_windows": validation_sharpe20_min,
        "validation_sharpe40_min_pass_windows": validation_sharpe40_min,
        "validation_drawdown20_max_pass_windows": validation_drawdown20_max,
        "validation_return40_min_pass_windows": validation_return40_min,
        "checks": checks,
        "robustness_passed": robustness_passed,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "note": "Train-only robustness review only; this does not authorize holdout, paper trading, or live trading.",
        "windows": rows,
    }


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"decision={report['decision']}",
        f"robustness_passed={report['robustness_passed']}",
        "safety="
        f"holdout:{report['holdout_authorized']} "
        f"paper:{report['paper_trading_authorized']} "
        f"live:{report['live_trading_authorized']}",
        f"target_config_source={report.get('target_config_source')}",
        f"target_config={json.dumps(report.get('target_config'), sort_keys=True)}",
        "summary="
        f"artifacts:{report['artifact_count']} "
        f"found:{report['target_config_found_windows']} "
        f"passed:{report['target_config_pass_windows']} "
        f"drop_one:{report['drop_one_pass_windows']} "
        f"cost40_positive:{report['cost40_positive_pass_windows']}",
        "pass_window_minima="
        f"val_sharpe20:{fmt(report.get('validation_sharpe20_min_pass_windows'))} "
        f"val_sharpe40:{fmt(report.get('validation_sharpe40_min_pass_windows'))} "
        f"val_dd20_max:{fmt(report.get('validation_drawdown20_max_pass_windows'))} "
        f"val_ret40_min:{fmt(report.get('validation_return40_min_pass_windows'))}",
    ]
    checks = report.get("checks") or {}
    lines.append("checks=" + ",".join(f"{key}:{value}" for key, value in checks.items()))
    lines.append("windows:")
    for row in report.get("windows", []):
        lines.append(
            "- "
            f"{Path(row['artifact']).name} "
            f"found:{row['target_config_found']} "
            f"pass:{row['target_advance_passed']} "
            f"passes:{row['pass_count']}/{row['rows']} "
            f"sel20:{fmt(row.get('selection_sharpe20'))} "
            f"val20:{fmt(row.get('validation_sharpe20'))} "
            f"val40:{fmt(row.get('validation_sharpe40'))} "
            f"dd20:{fmt(row.get('validation_drawdown20'))} "
            f"ret40:{fmt(row.get('validation_return40'))} "
            f"drop_one:{row.get('drop_one_passed')}"
        )
    return "\n".join(lines)


def expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in patterns:
        matched = [Path(path) for path in glob.glob(item)]
        if matched:
            paths.extend(matched)
        else:
            paths.append(Path(item))
    unique = sorted({path for path in paths}, key=lambda path: str(path))
    missing = [path for path in unique if not path.exists()]
    if missing:
        raise FileNotFoundError(", ".join(str(path) for path in missing))
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-window train-only robustness review for TSMOM candidates")
    parser.add_argument("artifacts", nargs="+", help="TSMOM artifact paths or glob patterns")
    parser.add_argument("--target-artifact", help="Artifact whose top accepted config should be audited")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--out-json")
    parser.add_argument("--out-text")
    args = parser.parse_args()
    paths = expand_inputs(args.artifacts)
    report = build_report(paths, Path(args.target_artifact) if args.target_artifact else None)
    text = format_text(report)
    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.out_text:
        out = Path(args.out_text)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text)


if __name__ == "__main__":
    main()
