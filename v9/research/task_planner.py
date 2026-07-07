from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from v9.research.candidate_dedupe import dedupe_candidates


PRESETS = (
    "hq_dd_long",
    "hq_fast_rebal",
    "hq_breadth_wide",
    "defensive_neighbor",
    "defensive_breadth",
    "defensive_drawdown",
    "defensive",
    "slow",
    "core",
    "fast",
)

TRAIN_WINDOWS = (
    ("2017-08-01", "2024-06-30 23:59:59", "full_202406"),
    ("2017-08-01", "2024-03-31 23:59:59", "full_202403"),
    ("2017-08-01", "2023-12-31 23:59:59", "full_202312"),
    ("2018-01-01", "2024-06-30 23:59:59", "from2018_202406"),
    ("2018-01-01", "2024-03-31 23:59:59", "from2018_202403"),
    ("2018-01-01", "2023-12-31 23:59:59", "from2018_202312"),
    ("2019-01-01", "2024-06-30 23:59:59", "from2019_202406"),
    ("2019-01-01", "2024-03-31 23:59:59", "from2019_202403"),
    ("2019-01-01", "2023-12-31 23:59:59", "from2019_202312"),
)

LEGACY_TASK_PRESETS = {
    "xsec_ohlcv_core_v1": "core",
    "xsec_ohlcv_defensive_v1": "defensive",
    "xsec_ohlcv_slow_v1": "slow",
    "xsec_ohlcv_fast_v1": "fast",
    "xsec_ohlcv_defensive_neighbor_v1": "defensive_neighbor",
    "xsec_ohlcv_defensive_breadth_v1": "defensive_breadth",
    "xsec_ohlcv_defensive_drawdown_v1": "defensive_drawdown",
}

DEFAULT_TRAIN_START = "2017-08-01"
DEFAULT_TRAIN_END = "2024-06-30 23:59:59"
DEFAULT_EMBARGO_START = "2024-07-01"
EVALUATION_VERSION = "selection_validation_v1"


@dataclass(frozen=True)
class PlannedTask:
    name: str
    preset: str
    train_start: str
    train_end: str
    embargo_start: str
    fingerprint: str
    output_json: str
    output_md: str
    bootstrap_iterations: int = 100
    prior_trials: int = 0
    timeout_sec: int = 3 * 60 * 60

    def command(self) -> tuple[str, ...]:
        return (
            "python3",
            "-m",
            "v9.contract.xsec_ohlcv_factory",
            "--preset",
            self.preset,
            "--train-start",
            self.train_start,
            "--train-end",
            self.train_end,
            "--embargo-start",
            self.embargo_start,
            "--bootstrap-iterations",
            str(self.bootstrap_iterations),
            "--prior-trials",
            str(self.prior_trials),
            "--out-json",
            self.output_json,
            "--out-md",
            self.output_md,
        )

    def record(self) -> dict[str, Any]:
        return asdict(self)


def utc_ts(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC") if ts.tzinfo else pd.Timestamp(value, tz="UTC")


def task_fingerprint(
    preset: str,
    train_start: str,
    train_end: str,
    embargo_start: str = DEFAULT_EMBARGO_START,
    bootstrap_iterations: int = 100,
    evaluation_version: str = EVALUATION_VERSION,
) -> str:
    raw = json.dumps(
        {
            "preset": preset,
            "train_start": train_start,
            "train_end": train_end,
            "embargo_start": embargo_start,
            "bootstrap_iterations": bootstrap_iterations,
            "evaluation_version": evaluation_version,
        },
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def legacy_fingerprints_from_results(task_results: list[dict[str, Any]]) -> set[str]:
    fingerprints: set[str] = set()
    for result in task_results:
        preset = LEGACY_TASK_PRESETS.get(str(result.get("task")))
        if preset:
            fingerprints.add(task_fingerprint(preset, DEFAULT_TRAIN_START, DEFAULT_TRAIN_END))
    return fingerprints


def load_explored_fingerprints(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        fingerprint = row.get("fingerprint")
        if fingerprint:
            out.add(str(fingerprint))
    return out


def append_explored_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def cumulative_trials(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += int(row.get("n_configs_tested", 0) or 0)
    return total


def preset_from_result(result: dict[str, Any]) -> str | None:
    planned = result.get("planned_task") or {}
    if planned.get("preset"):
        return str(planned["preset"])
    return LEGACY_TASK_PRESETS.get(str(result.get("task")))


def accepted_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    for row in payload.get("rows", []):
        if row.get("advance_passed"):
            return row
    for row in payload.get("top", []):
        if row.get("advance_passed"):
            return row
    return None


def candidate_quality(output_json: str | None) -> float:
    if not output_json:
        return 1.0
    path = Path(output_json)
    if not path.exists():
        return 1.0
    payload = json.loads(path.read_text())
    row = accepted_row(payload)
    if not row:
        return 1.0
    validation = row.get("validation", {}) or {}
    c20 = validation.get("cost20") or row.get("cost20", {})
    c40 = validation.get("cost40") or row.get("cost40", {})
    boot = float(c20.get("bootstrap_30d_sharpe_p5", 0.0) or 0.0)
    sh40 = float(c40.get("sharpe", 0.0) or 0.0)
    dd20 = float(c20.get("max_drawdown", 1.0) or 1.0)
    return max(0.0, boot) + 0.25 * max(0.0, sh40) - 0.5 * max(0.0, dd20)


def preset_stats(
    task_results: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, float]]:
    task_results = task_results or []
    attempts = {preset: 0.0 for preset in PRESETS}
    rewards = {preset: 0.0 for preset in PRESETS}
    qualities = {preset: [] for preset in PRESETS}
    output_to_preset: dict[str, str] = {}

    for result in task_results:
        preset = preset_from_result(result)
        if not preset or preset not in attempts:
            continue
        attempts[preset] += 1.0
        output_json = result.get("output_json")
        if output_json:
            output_to_preset[str(output_json)] = preset

    for candidate in dedupe_candidates(candidates or []):
        if candidate.get("duplicate_of"):
            continue
        output_json = candidate.get("output_json")
        preset = output_to_preset.get(str(output_json)) if output_json else None
        if not preset or preset not in rewards:
            continue
        rewards[preset] += 1.0
        qualities[preset].append(candidate_quality(str(output_json)))

    out: dict[str, dict[str, float]] = {}
    for preset in PRESETS:
        mean_quality = sum(qualities[preset]) / len(qualities[preset]) if qualities[preset] else 1.0
        out[preset] = {
            "attempts": attempts[preset],
            "distinct_rewards": rewards[preset],
            "mean_quality": mean_quality,
        }
    return out


def preset_score(
    preset: str,
    stats: dict[str, dict[str, float]],
    total_tasks: int,
    exploration_c: float = 0.5,
    quality_ref: float = 1.5,
) -> float:
    row = stats[preset]
    attempts = float(row["attempts"])
    rewards = float(row["distinct_rewards"])
    q = (rewards + 1.0) / (attempts + 2.0)
    quality_bonus = max(0.25, float(row["mean_quality"]) / quality_ref)
    ucb = exploration_c * math.sqrt(math.log(total_tasks + 2.0) / (attempts + 1.0))
    return q * quality_bonus + ucb


def ordered_presets_by_quality(
    task_results: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    exploration_c: float = 0.5,
) -> list[str]:
    stats = preset_stats(task_results, candidates)
    total_tasks = sum(int(stats[preset]["attempts"]) for preset in PRESETS)
    return sorted(
        PRESETS,
        key=lambda preset: (
            preset_score(preset, stats, total_tasks, exploration_c=exploration_c),
            -PRESETS.index(preset),
        ),
        reverse=True,
    )


def proposed_search_space(
    embargo_start: str = DEFAULT_EMBARGO_START,
    bootstrap_iterations: int = 100,
    preset_order: tuple[str, ...] = PRESETS,
    prior_trials: int = 0,
) -> list[PlannedTask]:
    tasks: list[PlannedTask] = []
    embargo = utc_ts(embargo_start)
    for train_start, train_end, window_label in TRAIN_WINDOWS:
        if utc_ts(train_end) >= embargo:
            raise ValueError(f"train window leaks into embargo: {train_end} >= {embargo_start}")
        for preset in preset_order:
            fingerprint = task_fingerprint(preset, train_start, train_end, embargo_start, bootstrap_iterations)
            short = fingerprint[:12]
            name = f"xsec_ohlcv_cont_{window_label}_{preset}_{short}"
            output_json = f"artifacts/v9/contract_lab/{name}.json"
            output_md = f"artifacts/v9/contract_lab/{name}.md"
            tasks.append(
                PlannedTask(
                    name=name,
                    preset=preset,
                    train_start=train_start,
                    train_end=train_end,
                    embargo_start=embargo_start,
                    fingerprint=fingerprint,
                    output_json=output_json,
                    output_md=output_md,
                    bootstrap_iterations=bootstrap_iterations,
                    prior_trials=max(0, int(prior_trials)),
                )
            )
    return tasks


def propose_tasks(
    explored_fingerprints: set[str],
    count: int,
    embargo_start: str = DEFAULT_EMBARGO_START,
    bootstrap_iterations: int = 100,
    task_results: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    prior_trials: int = 0,
) -> list[PlannedTask]:
    if count <= 0:
        return []
    preset_order = tuple(ordered_presets_by_quality(task_results, candidates))
    proposals = []
    for preset in preset_order:
        for task in proposed_search_space(
            embargo_start=embargo_start,
            bootstrap_iterations=bootstrap_iterations,
            preset_order=(preset,),
            prior_trials=prior_trials,
        ):
            if task.fingerprint in explored_fingerprints:
                continue
            proposals.append(task)
            break
        if len(proposals) >= count:
            break
    return proposals
