from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


PRESETS = (
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
) -> str:
    raw = json.dumps(
        {
            "preset": preset,
            "train_start": train_start,
            "train_end": train_end,
            "embargo_start": embargo_start,
            "bootstrap_iterations": bootstrap_iterations,
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


def proposed_search_space(
    embargo_start: str = DEFAULT_EMBARGO_START,
    bootstrap_iterations: int = 100,
) -> list[PlannedTask]:
    tasks: list[PlannedTask] = []
    embargo = utc_ts(embargo_start)
    for train_start, train_end, window_label in TRAIN_WINDOWS:
        if utc_ts(train_end) >= embargo:
            raise ValueError(f"train window leaks into embargo: {train_end} >= {embargo_start}")
        for preset in PRESETS:
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
                )
            )
    return tasks


def propose_tasks(
    explored_fingerprints: set[str],
    count: int,
    embargo_start: str = DEFAULT_EMBARGO_START,
    bootstrap_iterations: int = 100,
) -> list[PlannedTask]:
    if count <= 0:
        return []
    proposals = []
    for task in proposed_search_space(embargo_start=embargo_start, bootstrap_iterations=bootstrap_iterations):
        if task.fingerprint in explored_fingerprints:
            continue
        proposals.append(task)
        if len(proposals) >= count:
            break
    return proposals

