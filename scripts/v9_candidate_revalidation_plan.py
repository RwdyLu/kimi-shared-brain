from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.candidate_dedupe import dedupe_candidates  # noqa: E402
from v9.research.task_planner import (  # noqa: E402
    CLI_PRESET_BY_PRESET,
    EVALUATION_VERSION,
    EVALUATION_VERSION_BY_PRESET,
    MODULE_BY_PRESET,
    PRESETS,
)
from v9.contract.auto_research import maybe_pin_xsec_data_snapshot  # noqa: E402


XSEC_MODULE = "v9.contract.xsec_ohlcv_factory"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def read_jsonl_candidates(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def infer_preset(task_name: str) -> str | None:
    for preset in sorted(PRESETS, key=len, reverse=True):
        if preset in task_name:
            return preset
    return None


def current_eval_version(preset: str) -> str:
    return EVALUATION_VERSION_BY_PRESET.get(preset, EVALUATION_VERSION)


def config_fingerprint(config: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def group_fingerprint(parts: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def accepted_configs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    configs = []
    seen: set[str] = set()
    for row in payload.get("rows", []):
        if not row.get("advance_passed"):
            continue
        config = dict(row.get("config") or {})
        fp = config_fingerprint(config)
        if config and fp not in seen:
            seen.add(fp)
            configs.append(config)
    return configs


def payload_data_fingerprint(payload: dict[str, Any]) -> str:
    data = payload.get("data") or {}
    snapshot = data.get("snapshot") or {}
    return str(data.get("fingerprint") or snapshot.get("fingerprint") or "")


def build_revalidation_plan(
    state_path: Path,
    out_dir: Path = Path("artifacts/v9/revalidation"),
    max_configs_per_group: int = 250,
    supplemental_candidates_path: Path | None = Path("state/v9_supplemental_train_only_candidates.jsonl"),
) -> dict[str, Any]:
    state = read_json(state_path)
    state_candidates = list(state.get("candidates_found", []))
    supplemental_candidates = (
        read_jsonl_candidates(supplemental_candidates_path)
        if supplemental_candidates_path is not None
        else []
    )
    candidates = dedupe_candidates([*state_candidates, *supplemental_candidates])
    groups: dict[str, dict[str, Any]] = {}
    skipped = []
    max_effective_trials = 0

    for candidate in candidates:
        task_name = str(candidate.get("task") or "")
        if candidate.get("duplicate_of"):
            continue
        if candidate.get("quarantined"):
            skipped.append(
                {
                    "task": task_name,
                    "reason": "candidate_not_revalidatable",
                    "status": candidate.get("status"),
                    "output_json": candidate.get("output_json"),
                }
            )
            continue
        output_json = candidate.get("output_json")
        artifact = Path(str(output_json or ""))
        if not output_json or not artifact.exists():
            skipped.append({"task": task_name, "reason": "missing_artifact", "output_json": output_json})
            continue
        payload = read_json(artifact)
        preset = str(candidate.get("preset") or "") or infer_preset(task_name)
        if not preset:
            skipped.append({"task": task_name, "reason": "unknown_preset", "output_json": output_json})
            continue
        module = str(candidate.get("module") or "") or MODULE_BY_PRESET.get(preset, XSEC_MODULE)
        cli_preset = str(candidate.get("cli_preset") or "") or CLI_PRESET_BY_PRESET.get(preset, preset)
        configs = accepted_configs(payload)
        if not configs:
            skipped.append({"task": task_name, "reason": "no_accepted_configs", "output_json": output_json})
            continue
        run_cfg = payload.get("config") or {}
        selection_validation = payload.get("selection_validation") or {}
        max_effective_trials = max(max_effective_trials, int(selection_validation.get("effective_trials") or 0))
        key_parts = {
            "module": module,
            "preset": preset,
            "train_start": run_cfg.get("train_start", "2017-08-01"),
            "train_end": run_cfg.get("train_end", "2024-06-30 23:59:59"),
            "embargo_start": run_cfg.get("embargo_start", "2024-07-01"),
            "symbols": run_cfg.get("symbols") or payload.get("symbols") or [],
            "lookbacks_h": run_cfg.get("lookbacks_h") or [],
            "current_eval_version": current_eval_version(preset),
            "data_fingerprint": payload_data_fingerprint(payload),
        }
        key = group_fingerprint(key_parts)
        group = groups.setdefault(
            key,
            {
                "group_id": key,
                **key_parts,
                "cli_preset": cli_preset,
                "source_candidates": [],
                "configs": [],
                "config_fingerprints": set(),
                "data_snapshot": {},
                "data_snapshot_errors": [],
            },
        )
        snapshot_metadata: dict[str, Any] = {}
        if module == XSEC_MODULE:
            snapshot_metadata = maybe_pin_xsec_data_snapshot(payload)
            if snapshot_metadata.get("data_snapshot_path") and snapshot_metadata.get("data_snapshot_fingerprint"):
                group["data_snapshot"] = snapshot_metadata
            else:
                group["data_snapshot_errors"].append(
                    {
                        "task": task_name,
                        "output_json": output_json,
                        "data_snapshot_error": snapshot_metadata.get("data_snapshot_error") or "missing_data_snapshot",
                        "data_snapshot_expected_fingerprint": snapshot_metadata.get("data_snapshot_expected_fingerprint"),
                        "data_snapshot_current_fingerprint": snapshot_metadata.get("data_snapshot_current_fingerprint"),
                    }
                )
        group["source_candidates"].append(
            {
                "task": task_name,
                "status": candidate.get("status"),
                "output_json": output_json,
                "pass_count": int((payload.get("summary") or {}).get("pass_count") or len(configs)),
                "artifact_eval_version": (selection_validation.get("cache_version") or selection_validation.get("evaluation_version")),
                "data_snapshot_path": snapshot_metadata.get("data_snapshot_path"),
                "data_snapshot_fingerprint": snapshot_metadata.get("data_snapshot_fingerprint"),
                "data_snapshot_source": snapshot_metadata.get("data_snapshot_source"),
                "data_snapshot_error": snapshot_metadata.get("data_snapshot_error"),
            }
        )
        for config in configs:
            fp = config_fingerprint(config)
            if fp in group["config_fingerprints"]:
                continue
            if len(group["configs"]) >= max_configs_per_group:
                continue
            group["config_fingerprints"].add(fp)
            group["configs"].append(config)

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_groups = []
    for group in sorted(groups.values(), key=lambda row: (row["module"], row["preset"], row["train_end"])):
        configs = group.pop("configs")
        group.pop("config_fingerprints", None)
        data_snapshot = group.pop("data_snapshot", {}) or {}
        data_snapshot_errors = group.pop("data_snapshot_errors", []) or []
        if group["module"] == XSEC_MODULE:
            if not data_snapshot.get("data_snapshot_path") or not data_snapshot.get("data_snapshot_fingerprint"):
                skipped.append(
                    {
                        "group_id": group["group_id"],
                        "module": group["module"],
                        "preset": group["preset"],
                        "reason": "missing_data_snapshot",
                        "source_candidates": group["source_candidates"],
                        "data_snapshot_errors": data_snapshot_errors,
                    }
                )
                continue
            group.update(
                {
                    "data_snapshot_path": str(data_snapshot["data_snapshot_path"]),
                    "data_snapshot_fingerprint": str(data_snapshot["data_snapshot_fingerprint"]),
                    "data_snapshot_source": str(data_snapshot.get("data_snapshot_source") or "unknown"),
                }
            )
        config_path = out_dir / f"{group['group_id']}_{group['preset']}_configs.json"
        output_stem = f"revalidate_{group['group_id']}_{group['preset']}"
        output_json = f"artifacts/v9/contract_lab/{output_stem}.json"
        output_md = f"artifacts/v9/contract_lab/{output_stem}.md"
        config_path.write_text(json.dumps({"configs": configs}, indent=2, sort_keys=True))
        command = [
            "python3",
            "-m",
            str(group["module"]),
        ]
        if group.get("data_snapshot_path"):
            command.extend(["--data-snapshot", str(group["data_snapshot_path"])])
        command.extend(
            [
            "--preset",
            str(group["cli_preset"]),
            "--train-start",
            str(group["train_start"]),
            "--train-end",
            str(group["train_end"]),
            "--embargo-start",
            str(group["embargo_start"]),
            "--bootstrap-iterations",
            "100",
            "--prior-trials",
            str(max_effective_trials),
            "--config-list-json",
            str(config_path),
            "--out-json",
            output_json,
            "--out-md",
            output_md,
            ]
        )
        plan_groups.append(
            {
                **group,
                "config_count": len(configs),
                "config_json": str(config_path),
                "output_json": output_json,
                "output_md": output_md,
                "command": command,
            }
        )

    return {
        "kind": "v9_train_only_candidate_revalidation_plan_v1",
        "source_state": str(state_path),
        "supplemental_candidates": str(supplemental_candidates_path or ""),
        "supplemental_candidate_count": len(supplemental_candidates),
        "current_xsec_eval_version": EVALUATION_VERSION,
        "current_tsmom_eval_versions": EVALUATION_VERSION_BY_PRESET,
        "global_prior_trials": max_effective_trials,
        "group_count": len(plan_groups),
        "config_count": sum(group["config_count"] for group in plan_groups),
        "pinned_group_count": sum(1 for group in plan_groups if group.get("data_snapshot_path")),
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "groups": plan_groups,
        "skipped": skipped,
    }


def format_text(plan: dict[str, Any]) -> str:
    lines = [
        f"kind={plan['kind']}",
        f"groups={plan['group_count']} pinned={plan.get('pinned_group_count', 0)} configs={plan['config_count']} global_prior_trials={plan['global_prior_trials']}",
        f"safety=holdout:{plan['holdout_authorized']} paper:{plan['paper_trading_authorized']} live:{plan['live_trading_authorized']}",
    ]
    for group in plan.get("groups", []):
        lines.append(
            "group="
            f"{group['group_id']} module={group['module']} preset={group['preset']} "
            f"train={group['train_start']}..{group['train_end']} configs={group['config_count']} "
            f"sources={len(group['source_candidates'])} config_json={group['config_json']}"
        )
    if plan.get("skipped"):
        lines.append(f"skipped={len(plan['skipped'])}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build train-only revalidation config lists for existing candidates")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument(
        "--supplemental-candidates",
        default="state/v9_supplemental_train_only_candidates.jsonl",
        help="Optional JSONL candidate ledger appended by out-of-band train-only runs; use empty string to disable.",
    )
    parser.add_argument("--out-dir", default="artifacts/v9/revalidation")
    parser.add_argument("--out-json", default="artifacts/v9/revalidation/v9_candidate_revalidation_plan.json")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    supplemental = Path(args.supplemental_candidates) if args.supplemental_candidates else None
    plan = build_revalidation_plan(
        Path(args.state),
        out_dir=Path(args.out_dir),
        supplemental_candidates_path=supplemental,
    )
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(plan, indent=2, sort_keys=True))
    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(format_text(plan))


if __name__ == "__main__":
    main()
