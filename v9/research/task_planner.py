from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from v9.research.candidate_dedupe import candidate_is_quarantined, dedupe_candidates


DEFAULT_TRAIN_MODULE = "v9.contract.xsec_ohlcv_factory"
MODULE_BY_PRESET = {
    "tsmom_bear_short_medium": "v9.contract.tsmom_factory",
    "tsmom_bear_short_medium_neighbor": "v9.contract.tsmom_factory",
    "tsmom_bear_short_medium_risk": "v9.contract.tsmom_factory",
    "tsmom_bear_short_fast": "v9.contract.tsmom_factory",
    "tsmom_bear_short_cost_guard": "v9.contract.tsmom_factory",
    "tsmom_slow_cost_guard": "v9.contract.tsmom_factory",
    "tsmom_ultra_slow_cost_guard": "v9.contract.tsmom_factory",
    "tsmom_core_cost_guard": "v9.contract.tsmom_factory",
    "tsmom_core_slow_cost_guard": "v9.contract.tsmom_factory",
    "tsmom_bear_short_regime": "v9.contract.tsmom_factory",
    "tsmom_defensive_regime": "v9.contract.tsmom_factory",
    "tsmom_trend_ensemble": "v9.contract.tsmom_factory",
}
CLI_PRESET_BY_PRESET = {
    "tsmom_bear_short_medium": "bear_short_medium",
    "tsmom_bear_short_medium_neighbor": "bear_short_medium_neighbor",
    "tsmom_bear_short_medium_risk": "bear_short_medium_risk",
    "tsmom_bear_short_fast": "bear_short_fast",
    "tsmom_bear_short_cost_guard": "bear_short_cost_guard",
    "tsmom_slow_cost_guard": "slow_cost_guard",
    "tsmom_ultra_slow_cost_guard": "ultra_slow_cost_guard",
    "tsmom_core_cost_guard": "core_cost_guard",
    "tsmom_core_slow_cost_guard": "core_slow_cost_guard",
    "tsmom_bear_short_regime": "bear_short_regime",
    "tsmom_defensive_regime": "defensive_regime",
    "tsmom_trend_ensemble": "core",
}

FOCUS_PRESETS = (
    "tsmom_defensive_regime",
    "tsmom_bear_short_regime",
    "tsmom_trend_ensemble",
    "tsmom_bear_short_medium",
    "tsmom_bear_short_medium_neighbor",
    "tsmom_bear_short_medium_risk",
    "tsmom_bear_short_cost_guard",
    "tsmom_slow_cost_guard",
    "tsmom_ultra_slow_cost_guard",
    "tsmom_core_cost_guard",
    "tsmom_core_slow_cost_guard",
    "tsmom_bear_short_fast",
    "evergreen_regime_guarded",
    "evergreen_lowvol_guarded",
    "evergreen_guarded",
    "evergreen_fast",
    "breakout_fast",
    "breakout_slow",
    "hq_active_recent",
    "hq_recent_signal",
    "hq_decay_bridge",
    "hq_wf_bridge",
    "hq_dd_plateau",
    "hq_dd_long",
    "defensive_drawdown",
    "hq_cadence_tranche",
    "hq_breadth_wide",
    "hq_fast_rebal",
    "defensive_neighbor",
    "defensive_breadth",
    "defensive",
    "slow",
    "core",
    "fast",
)

PRESETS = (
    "tsmom_bear_short_medium",
    "tsmom_bear_short_medium_neighbor",
    "tsmom_bear_short_medium_risk",
    "tsmom_bear_short_cost_guard",
    "tsmom_slow_cost_guard",
    "tsmom_ultra_slow_cost_guard",
    "tsmom_core_cost_guard",
    "tsmom_core_slow_cost_guard",
    "tsmom_bear_short_fast",
    "tsmom_bear_short_regime",
    "tsmom_defensive_regime",
    "tsmom_trend_ensemble",
    "evergreen_regime_guarded",
    "evergreen_lowvol_guarded",
    "evergreen_guarded",
    "evergreen_fast",
    "hq_cadence_tranche",
    "hq_active_recent",
    "hq_recent_signal",
    "hq_decay_bridge",
    "hq_wf_bridge",
    "breakout_fast",
    "breakout_slow",
    "hq_dd_plateau",
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

PLANNER_PRESET_MODES = ("balanced", "xsec_first")


def preset_module(preset: str) -> str:
    return MODULE_BY_PRESET.get(preset, DEFAULT_TRAIN_MODULE)


def preset_family(preset: str) -> str:
    return "tsmom" if preset_module(preset) == "v9.contract.tsmom_factory" else "xsec_ohlcv"


XSEC_FIRST_FOCUS_PRESETS = (
    *(preset for preset in FOCUS_PRESETS if preset_family(preset) == "xsec_ohlcv"),
    *(preset for preset in FOCUS_PRESETS if preset_family(preset) == "tsmom"),
)


def focus_presets_for_mode(preset_mode: str = "balanced") -> tuple[str, ...]:
    if preset_mode == "balanced":
        return FOCUS_PRESETS
    if preset_mode == "xsec_first":
        return XSEC_FIRST_FOCUS_PRESETS
    modes = ", ".join(PLANNER_PRESET_MODES)
    raise ValueError(f"unknown planner preset mode: {preset_mode!r}; expected one of {modes}")


TRAIN_WINDOWS = (
    ("2017-08-01", "2024-06-30 23:59:59", "full_202406"),
    ("2017-08-01", "2024-03-31 23:59:59", "full_202403"),
    ("2017-08-01", "2023-12-31 23:59:59", "full_202312"),
    ("2017-08-01", "2024-05-31 23:59:59", "full_202405"),
    ("2017-08-01", "2024-04-30 23:59:59", "full_202404"),
    ("2017-08-01", "2024-02-29 23:59:59", "full_202402"),
    ("2017-08-01", "2024-01-31 23:59:59", "full_202401"),
    ("2017-08-01", "2023-09-30 23:59:59", "full_202309"),
    ("2017-08-01", "2023-06-30 23:59:59", "full_202306"),
    ("2017-08-01", "2022-12-31 23:59:59", "full_202212"),
    ("2018-01-01", "2024-06-30 23:59:59", "from2018_202406"),
    ("2018-01-01", "2024-03-31 23:59:59", "from2018_202403"),
    ("2018-01-01", "2023-12-31 23:59:59", "from2018_202312"),
    ("2018-01-01", "2024-05-31 23:59:59", "from2018_202405"),
    ("2018-01-01", "2024-04-30 23:59:59", "from2018_202404"),
    ("2018-01-01", "2024-02-29 23:59:59", "from2018_202402"),
    ("2018-01-01", "2024-01-31 23:59:59", "from2018_202401"),
    ("2018-01-01", "2023-09-30 23:59:59", "from2018_202309"),
    ("2018-01-01", "2023-06-30 23:59:59", "from2018_202306"),
    ("2018-01-01", "2022-12-31 23:59:59", "from2018_202212"),
    ("2019-01-01", "2024-06-30 23:59:59", "from2019_202406"),
    ("2019-01-01", "2024-03-31 23:59:59", "from2019_202403"),
    ("2019-01-01", "2023-12-31 23:59:59", "from2019_202312"),
    ("2019-01-01", "2024-05-31 23:59:59", "from2019_202405"),
    ("2019-01-01", "2024-04-30 23:59:59", "from2019_202404"),
    ("2019-01-01", "2024-02-29 23:59:59", "from2019_202402"),
    ("2019-01-01", "2024-01-31 23:59:59", "from2019_202401"),
    ("2019-01-01", "2023-09-30 23:59:59", "from2019_202309"),
    ("2019-01-01", "2023-06-30 23:59:59", "from2019_202306"),
    ("2019-01-01", "2022-12-31 23:59:59", "from2019_202212"),
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
EVALUATION_VERSION = "selection_validation_v4_xsec_diagnostic_walkforward"
EVALUATION_VERSION_BY_PRESET = {
    "evergreen_fast": "selection_validation_v10_xsec_evergreen_activity_gate",
    "evergreen_regime_guarded": "selection_validation_v1_xsec_regime_guarded",
    "evergreen_lowvol_guarded": "selection_validation_v1_xsec_lowvol_guarded",
    "evergreen_guarded": "selection_validation_v12_xsec_risk_stop_hysteresis",
    "breakout_fast": "selection_validation_v10_xsec_risk_stop_hysteresis",
    "breakout_slow": "selection_validation_v10_xsec_risk_stop_hysteresis",
    "hq_active_recent": "selection_validation_v2_xsec_hq_recent_activity",
    "hq_recent_signal": "selection_validation_v1_xsec_hq_recent_signal",
    "hq_decay_bridge": "selection_validation_v1_xsec_hq_decay_bridge",
    "hq_wf_bridge": "selection_validation_v2_xsec_hq_walkforward_bridge_bounded_loss",
    "tsmom_bear_short_medium": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_bear_short_medium_neighbor": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_bear_short_medium_risk": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_bear_short_fast": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_bear_short_cost_guard": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_slow_cost_guard": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_ultra_slow_cost_guard": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_core_cost_guard": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_core_slow_cost_guard": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_bear_short_regime": "selection_validation_v2_tsmom_walkforward_symbol_leg",
    "tsmom_defensive_regime": "selection_validation_v2_tsmom_defensive_active_years",
    "tsmom_trend_ensemble": "selection_validation_v4_tsmom_active_years",
}


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
    module: str = DEFAULT_TRAIN_MODULE
    cli_preset: str | None = None

    def command(self) -> tuple[str, ...]:
        return (
            "python3",
            "-m",
            self.module,
            "--preset",
            self.cli_preset or self.preset,
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


def evaluation_version_for_preset(preset: str) -> str:
    return EVALUATION_VERSION_BY_PRESET.get(preset, EVALUATION_VERSION)


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
    selection = row.get("selection", {}) or {}
    c20 = selection.get("cost20") or row.get("cost20", {})
    c40 = selection.get("cost40") or row.get("cost40", {})
    walk_forward = row.get("walk_forward", {}) or {}
    boot = float(c20.get("bootstrap_30d_sharpe_p5", 0.0) or 0.0)
    sh40 = float(c40.get("sharpe", 0.0) or 0.0)
    wf_q25 = float(walk_forward.get("q25_sharpe", 0.0) or 0.0)
    dd_raw = c20.get("max_drawdown")
    dd20 = float(dd_raw) if dd_raw is not None else 1.0
    return max(0.0, boot) + 0.40 * max(0.0, wf_q25) + 0.25 * max(0.0, sh40) - 0.5 * max(0.0, dd20)


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
        if candidate_is_quarantined(candidate):
            continue
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
    preset_mode: str = "balanced",
) -> list[str]:
    stats = preset_stats(task_results, candidates)
    total_tasks = sum(int(stats[preset]["attempts"]) for preset in PRESETS)
    scored = sorted(
        PRESETS,
        key=lambda preset: (
            preset_score(preset, stats, total_tasks, exploration_c=exploration_c),
            -PRESETS.index(preset),
        ),
        reverse=True,
    )
    focused = [preset for preset in focus_presets_for_mode(preset_mode) if preset in scored]
    return focused + [preset for preset in scored if preset not in focused]


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
            fingerprint = task_fingerprint(
                preset,
                train_start,
                train_end,
                embargo_start,
                bootstrap_iterations,
                evaluation_version=evaluation_version_for_preset(preset),
            )
            short = fingerprint[:12]
            module = MODULE_BY_PRESET.get(preset, DEFAULT_TRAIN_MODULE)
            cli_preset = CLI_PRESET_BY_PRESET.get(preset)
            family = "tsmom" if module == "v9.contract.tsmom_factory" else "xsec_ohlcv"
            name = f"{family}_cont_{window_label}_{preset}_{short}"
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
                    module=module,
                    cli_preset=cli_preset,
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
    preset_mode: str = "balanced",
) -> list[PlannedTask]:
    if count <= 0:
        return []
    preset_order = tuple(
        ordered_presets_by_quality(task_results, candidates, preset_mode=preset_mode)
    )
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
