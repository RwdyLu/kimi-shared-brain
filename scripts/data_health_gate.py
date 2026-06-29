#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def month_range(start: str, end: str) -> list[str]:
    y, m = [int(x) for x in start.split("-")]
    ey, em = [int(x) for x in end.split("-")]
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y += 1
            m = 1
    return out


def contiguous_blocks(months: list[str]) -> list[list[str]]:
    if not months:
        return []
    wanted = set(months)
    ordered = sorted(wanted)
    blocks: list[list[str]] = []
    current = [ordered[0]]
    full = month_range(ordered[0], ordered[-1])
    for month in full[1:]:
        if month in wanted:
            if current and month_range(current[-1], month) == [current[-1], month]:
                current.append(month)
            else:
                blocks.append(current)
                current = [month]
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return [block for block in blocks if block]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


@dataclass
class DataGateResult:
    enabled: bool
    manifest_dir: str | None
    requested_symbols: list[str]
    allowed_symbols: list[str]
    blocked_symbols: dict[str, str]
    data_gate: str
    data_audit_summary_hash: str | None = None


class DataHealthGate:
    def __init__(self, manifest_dir: str | Path | None, timeframe: str, start: str, end: str, months_per_symbol: int):
        self.manifest_dir = Path(manifest_dir) if manifest_dir else None
        self.timeframe = timeframe
        self.start = start
        self.end = end
        self.months_per_symbol = int(months_per_symbol)
        self._manifests: dict[str, dict[str, Any]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.manifest_dir)

    def manifest_path(self, symbol: str) -> Path | None:
        if not self.manifest_dir:
            return None
        return self.manifest_dir / f"{symbol}_{self.timeframe}_{self.start}_{self.end}.json"

    def manifest(self, symbol: str) -> dict[str, Any]:
        if symbol not in self._manifests:
            path = self.manifest_path(symbol)
            self._manifests[symbol] = load_json(path) if path else {}
        return self._manifests[symbol]

    def valid_months(self, symbol: str, requested_months: list[str]) -> list[str]:
        if not self.enabled:
            return requested_months
        manifest = self.manifest(symbol)
        valid = set(manifest.get("valid_months") or [])
        return [month for month in requested_months if month in valid]

    def has_enough_contiguous_months(self, symbol: str, requested_months: list[str]) -> bool:
        months = self.valid_months(symbol, requested_months)
        return any(len(block) >= self.months_per_symbol for block in contiguous_blocks(months))

    def reject_reason(self, symbol: str, requested_months: list[str]) -> str | None:
        if not self.enabled:
            return None
        manifest = self.manifest(symbol)
        if not manifest:
            return "missing_data_manifest"
        months = self.valid_months(symbol, requested_months)
        if not months:
            return "no_valid_months_in_requested_range"
        if not self.has_enough_contiguous_months(symbol, requested_months):
            return f"no_contiguous_valid_block_{self.months_per_symbol}_months"
        return None

    def summarize(self, requested_symbols: list[str], requested_months: list[str], audit_summary_hash: str | None = None) -> DataGateResult:
        if not self.enabled:
            return DataGateResult(
                enabled=False,
                manifest_dir=None,
                requested_symbols=list(requested_symbols),
                allowed_symbols=list(requested_symbols),
                blocked_symbols={},
                data_gate="disabled_no_manifest_dir",
                data_audit_summary_hash=audit_summary_hash,
            )
        allowed = []
        blocked: dict[str, str] = {}
        for symbol in requested_symbols:
            reason = self.reject_reason(symbol, requested_months)
            if reason:
                blocked[symbol] = reason
            else:
                allowed.append(symbol)
        return DataGateResult(
            enabled=True,
            manifest_dir=str(self.manifest_dir),
            requested_symbols=list(requested_symbols),
            allowed_symbols=allowed,
            blocked_symbols=blocked,
            data_gate="strict_valid_month_manifest_required",
            data_audit_summary_hash=audit_summary_hash,
        )

    def to_jsonable(self, result: DataGateResult) -> dict[str, Any]:
        return {
            "enabled": result.enabled,
            "manifest_dir": result.manifest_dir,
            "requested_symbols": result.requested_symbols,
            "allowed_symbols": result.allowed_symbols,
            "blocked_symbols": result.blocked_symbols,
            "data_gate": result.data_gate,
            "data_audit_summary_hash": result.data_audit_summary_hash,
        }


def build_gate_from_args(args: Any) -> DataHealthGate:
    return DataHealthGate(
        getattr(args, "data_manifest_dir", ""),
        getattr(args, "timeframe", "1m"),
        getattr(args, "start", ""),
        getattr(args, "end", ""),
        int(getattr(args, "months_per_symbol", 1)),
    )
