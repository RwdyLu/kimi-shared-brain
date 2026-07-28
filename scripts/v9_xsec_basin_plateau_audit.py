#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_AXIS_KEYS = (
    "lookback_h",
    "k",
    "market_filter_h",
    "vol_target_ann",
    "drawdown_stop",
    "cooldown_h",
)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def cfg_value(value: Any) -> int | float | str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 12)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return int(number)
    return round(number, 12)


def cfg_signature(config: dict[str, Any], axis_keys: tuple[str, ...]) -> tuple[int | float | str, ...]:
    return tuple(cfg_value(config.get(key)) for key in axis_keys)


def axis_values(rows: list[dict[str, Any]], axis_keys: tuple[str, ...]) -> dict[str, list[int | float | str]]:
    values: dict[str, set[int | float | str]] = {key: set() for key in axis_keys}
    for row in rows:
        config = row.get("config") or {}
        for key in axis_keys:
            values[key].add(cfg_value(config.get(key)))
    return {key: sorted(raw) for key, raw in values.items()}


def is_one_step_neighbor(
    left: dict[str, Any],
    right: dict[str, Any],
    axes: dict[str, list[int | float | str]],
    axis_keys: tuple[str, ...],
) -> bool:
    left_cfg = left.get("config") or {}
    right_cfg = right.get("config") or {}
    changed_key = None
    for key in axis_keys:
        left_value = cfg_value(left_cfg.get(key))
        right_value = cfg_value(right_cfg.get(key))
        if left_value == right_value:
            continue
        if changed_key is not None:
            return False
        values = axes[key]
        try:
            left_idx = values.index(left_value)
            right_idx = values.index(right_value)
        except ValueError:
            return False
        if abs(left_idx - right_idx) != 1:
            return False
        changed_key = key
    return changed_key is not None


def validation_cost20(row: dict[str, Any]) -> dict[str, Any]:
    return ((row.get("validation") or {}).get("cost20") or {})


def validation_sharpe(row: dict[str, Any]) -> float | None:
    block = validation_cost20(row)
    if not block:
        return None
    return safe_float(block.get("sharpe"), default=float("nan"))


def validation_symbol_pnl(row: dict[str, Any]) -> dict[str, float]:
    raw = validation_cost20(row).get("symbol_pnl") or {}
    return {str(key): safe_float(value) for key, value in raw.items()}


def row_summary(row: dict[str, Any]) -> dict[str, Any]:
    cost20 = row.get("cost20") or {}
    validation20 = validation_cost20(row)
    walk_forward = row.get("walk_forward") or {}
    return {
        "advance_passed": bool(row.get("advance_passed")),
        "config": row.get("config") or {},
        "selection_sharpe20": safe_float(cost20.get("sharpe")),
        "selection_return20": safe_float(cost20.get("total_return")),
        "selection_max_drawdown20": safe_float(cost20.get("max_drawdown")),
        "validation_sharpe20": validation_sharpe(row),
        "validation_return20": safe_float(validation20.get("total_return")),
        "validation_max_drawdown20": safe_float(validation20.get("max_drawdown")),
        "walk_forward_q25_sharpe": safe_float(walk_forward.get("q25_sharpe")),
        "walk_forward_bounded_loss": bool(walk_forward.get("bounded_loss_consistency_passed")),
        "failed_checks": sorted(str(key) for key, value in (row.get("advance_checks") or {}).items() if value is False),
        "validation_symbol_pnl": validation_symbol_pnl(row),
    }


def audit_payload(
    artifact: Path,
    min_neighbors: int = 2,
    min_neighbor_validation_sharpe: float | None = None,
    axis_keys: tuple[str, ...] = DEFAULT_AXIS_KEYS,
) -> dict[str, Any]:
    payload = json.loads(artifact.read_text())
    rows = list(payload.get("rows") or [])
    selection_validation = payload.get("selection_validation") or {}
    threshold = (
        float(min_neighbor_validation_sharpe)
        if min_neighbor_validation_sharpe is not None
        else safe_float(selection_validation.get("validation_sharpe20_min"))
    )
    axes = axis_values(rows, axis_keys)
    validated_rows = [row for row in rows if validation_sharpe(row) is not None]
    pass_rows = [row for row in rows if row.get("advance_passed")]
    centers = []
    for row in pass_rows:
        neighbors = [
            candidate
            for candidate in validated_rows
            if candidate is not row
            and is_one_step_neighbor(row, candidate, axes, axis_keys)
            and (validation_sharpe(candidate) or -999.0) >= threshold
        ]
        centers.append(
            {
                **row_summary(row),
                "neighbor_validation_pass_count": len(neighbors),
                "plateau_passed": len(neighbors) >= min_neighbors,
                "neighbors": [row_summary(neighbor) for neighbor in sorted(neighbors, key=lambda item: validation_sharpe(item) or -999.0, reverse=True)],
            }
        )
    centers.sort(
        key=lambda item: (
            bool(item["plateau_passed"]),
            int(item["neighbor_validation_pass_count"]),
            safe_float(item.get("validation_sharpe20"), -999.0),
            safe_float(item.get("walk_forward_q25_sharpe"), -999.0),
        ),
        reverse=True,
    )
    def near_miss_key(row: dict[str, Any]) -> tuple[bool, float, float, float]:
        return (
            bool(row.get("advance_passed")),
            validation_sharpe(row) or -999.0,
            safe_float((row.get("walk_forward") or {}).get("q25_sharpe"), -999.0),
            safe_float((row.get("cost20") or {}).get("sharpe"), -999.0),
        )

    best_near_miss = max(rows, key=near_miss_key) if rows else None
    return {
        "artifact": str(artifact),
        "row_count": len(rows),
        "validated_row_count": len(validated_rows),
        "advance_pass_count": len(pass_rows),
        "min_neighbor_validation_sharpe": threshold,
        "min_neighbors": int(min_neighbors),
        "axis_keys": list(axis_keys),
        "plateau_passed": any(center["plateau_passed"] for center in centers),
        "centers": centers,
        "best_near_miss": row_summary(best_near_miss) if best_near_miss else None,
        "note": "Plateau audit only. It does not authorize holdout, paper trading, or live trading.",
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"artifact={payload['artifact']}",
        f"rows={payload['row_count']} validated={payload['validated_row_count']} advance_pass={payload['advance_pass_count']}",
        f"threshold={payload['min_neighbor_validation_sharpe']:.6f} min_neighbors={payload['min_neighbors']} plateau_passed={payload['plateau_passed']}",
    ]
    if payload["centers"]:
        lines.append("centers:")
        for center in payload["centers"][:10]:
            cfg = center["config"]
            lines.append(
                "  "
                f"plateau={center['plateau_passed']} neighbors={center['neighbor_validation_pass_count']} "
                f"val_sh={center['validation_sharpe20']:.3f} wf_q25={center['walk_forward_q25_sharpe']:.3f} "
                f"cfg={{lookback={cfg.get('lookback_h')}, k={cfg.get('k')}, mf={cfg.get('market_filter_h')}, "
                f"vol={cfg.get('vol_target_ann')}, stop={cfg.get('drawdown_stop')}, cooldown={cfg.get('cooldown_h')}}}"
            )
    if payload["best_near_miss"]:
        row = payload["best_near_miss"]
        cfg = row["config"]
        lines.append(
            "best_near_miss: "
            f"advance={row['advance_passed']} val_sh={row['validation_sharpe20']:.3f} "
            f"wf_q25={row['walk_forward_q25_sharpe']:.3f} failed={row['failed_checks']} "
            f"cfg={{lookback={cfg.get('lookback_h')}, k={cfg.get('k')}, mf={cfg.get('market_filter_h')}, "
            f"vol={cfg.get('vol_target_ann')}, stop={cfg.get('drawdown_stop')}, cooldown={cfg.get('cooldown_h')}}}"
        )
    lines.append(str(payload["note"]))
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit xsec basin runs for non-isolated validation plateaus")
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--min-neighbors", type=int, default=2)
    parser.add_argument("--min-neighbor-validation-sharpe", type=float, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = audit_payload(
        Path(args.artifact),
        min_neighbors=args.min_neighbors,
        min_neighbor_validation_sharpe=args.min_neighbor_validation_sharpe,
    )
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(payload, indent=2, sort_keys=True))
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_text(payload))


if __name__ == "__main__":
    main()
