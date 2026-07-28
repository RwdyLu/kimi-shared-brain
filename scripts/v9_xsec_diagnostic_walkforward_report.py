from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def artifact_paths(path: Path) -> tuple[Path, Path, Path]:
    if path.suffix == ".jsonl" and path.name.endswith(".progress.jsonl"):
        stem = path.with_suffix("").with_suffix("")
        return stem.with_suffix(".json"), path, stem.with_suffix(".progress.meta.json")
    if path.suffix == ".json":
        return path, path.with_suffix(".progress.jsonl"), path.with_suffix(".progress.meta.json")
    return path.with_suffix(".json"), path.with_suffix(".progress.jsonl"), path.with_suffix(".progress.meta.json")


def load_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    final_json, progress_jsonl, progress_meta = artifact_paths(path)
    if final_json.exists():
        payload = json.loads(final_json.read_text())
        return list(payload.get("rows", [])), dict(payload.get("summary", {})), "final"

    rows: list[dict[str, Any]] = []
    if progress_jsonl.exists():
        for line in progress_jsonl.read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            row = record.get("row")
            if isinstance(row, dict):
                rows.append(row)
    meta: dict[str, Any] = {}
    if progress_meta.exists():
        meta = json.loads(progress_meta.read_text())
    return rows, meta, "progress"


def fail_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        for name, passed in (row.get("advance_checks") or {}).items():
            if not passed:
                counts[str(name)] += 1
    return dict(counts.most_common())


def row_metric(row: dict[str, Any], section: str, key: str, default: float = 0.0) -> float:
    value = ((row.get(section) or {}).get("cost20") or {}).get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def summarize(rows: list[dict[str, Any]], meta: dict[str, Any], source_kind: str) -> dict[str, Any]:
    total_rows = int(meta.get("total_rows") or len(rows))
    completed_rows = int(meta.get("completed_rows") or len(rows))
    pass_rows = [row for row in rows if row.get("advance_passed")]
    diagnostic_rows = [row for row in rows if (row.get("diagnostic_walk_forward") or {}).get("triggered")]
    regular_wf_rows = [row for row in rows if "q25_sharpe" in (row.get("walk_forward") or {})]

    diag_q25 = [float((row.get("diagnostic_walk_forward") or {}).get("q25_sharpe") or 0.0) for row in diagnostic_rows]
    diag_sign = [float((row.get("diagnostic_walk_forward") or {}).get("sign_consistency") or 0.0) for row in diagnostic_rows]
    regular_q25 = [float((row.get("walk_forward") or {}).get("q25_sharpe") or 0.0) for row in regular_wf_rows]
    validation_sharpes = [row_metric(row, "validation", "sharpe") for row in rows if (row.get("validation") or {}).get("cost20")]

    threshold = 0.30
    strong_diag = [
        row
        for row in diagnostic_rows
        if float((row.get("diagnostic_walk_forward") or {}).get("q25_sharpe") or 0.0) >= threshold
        and float((row.get("diagnostic_walk_forward") or {}).get("sign_consistency") or 0.0) >= 0.75
    ]
    top_rows = sorted(
        rows,
        key=lambda row: (
            float((row.get("diagnostic_walk_forward") or {}).get("q25_sharpe") or -999.0),
            row_metric(row, "validation", "sharpe"),
            float(((row.get("cost20") or {}).get("sharpe")) or 0.0),
        ),
        reverse=True,
    )[:10]
    return {
        "source_kind": source_kind,
        "completed_rows": completed_rows,
        "total_rows": total_rows,
        "pass_count": len(pass_rows),
        "diagnostic_triggered_count": len(diagnostic_rows),
        "diagnostic_q25_max": max(diag_q25) if diag_q25 else None,
        "diagnostic_q25_values": diag_q25,
        "diagnostic_sign_max": max(diag_sign) if diag_sign else None,
        "diagnostic_strong_count": len(strong_diag),
        "diagnostic_strong_fraction": len(strong_diag) / len(diagnostic_rows) if diagnostic_rows else 0.0,
        "regular_walk_forward_count": len(regular_wf_rows),
        "regular_walk_forward_q25_max": max(regular_q25) if regular_q25 else None,
        "validation_sharpe20_max": max(validation_sharpes) if validation_sharpes else None,
        "fail_counts": fail_counts(rows),
        "top_rows": [
            {
                "config": row.get("config", {}),
                "advance_passed": bool(row.get("advance_passed")),
                "selection_sharpe20": float(((row.get("cost20") or {}).get("sharpe")) or 0.0),
                "validation_sharpe20": row_metric(row, "validation", "sharpe"),
                "walk_forward_q25": float((row.get("walk_forward") or {}).get("q25_sharpe") or 0.0),
                "diagnostic_triggered": bool((row.get("diagnostic_walk_forward") or {}).get("triggered")),
                "diagnostic_q25": float((row.get("diagnostic_walk_forward") or {}).get("q25_sharpe") or 0.0),
                "diagnostic_sign_consistency": float((row.get("diagnostic_walk_forward") or {}).get("sign_consistency") or 0.0),
                "failed_checks": [name for name, passed in (row.get("advance_checks") or {}).items() if not passed],
            }
            for row in top_rows
        ],
    }


def format_text(summary: dict[str, Any]) -> str:
    lines = [
        f"source={summary['source_kind']}",
        f"rows={summary['completed_rows']}/{summary['total_rows']}",
        f"pass_count={summary['pass_count']}",
        f"diagnostic_triggered={summary['diagnostic_triggered_count']}",
        f"diagnostic_q25_max={summary['diagnostic_q25_max']}",
        f"diagnostic_sign_max={summary['diagnostic_sign_max']}",
        f"diagnostic_strong={summary['diagnostic_strong_count']} fraction={summary['diagnostic_strong_fraction']:.3f}",
        f"regular_wf_count={summary['regular_walk_forward_count']}",
        f"regular_wf_q25_max={summary['regular_walk_forward_q25_max']}",
        f"validation_sharpe20_max={summary['validation_sharpe20_max']}",
        "fail_counts:",
    ]
    for name, count in summary["fail_counts"].items():
        lines.append(f"- {name}: {count}")
    lines.append("top_rows:")
    for row in summary["top_rows"]:
        lines.append(
            "- pass={pass_} sel20={sel:.3f} val20={val:.3f} wf={wf:.3f} diag={diag} diag_q25={diag_q25:.3f} sign={sign:.3f} fails={fails}".format(
                pass_=row["advance_passed"],
                sel=row["selection_sharpe20"],
                val=row["validation_sharpe20"],
                wf=row["walk_forward_q25"],
                diag=row["diagnostic_triggered"],
                diag_q25=row["diagnostic_q25"],
                sign=row["diagnostic_sign_consistency"],
                fails=",".join(row["failed_checks"][:5]),
            )
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only XSEC diagnostic walk-forward report")
    parser.add_argument("artifact", help="Final .json artifact or base/progress path")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    rows, meta, source_kind = load_rows(Path(args.artifact))
    summary = summarize(rows, meta, source_kind)
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(format_text(summary))


if __name__ == "__main__":
    main()
