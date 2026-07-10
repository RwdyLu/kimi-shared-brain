from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BLOCKING_STATUSES = {
    "holdout_fail",
    "holdout_failed_do_not_paper_trade",
    "quarantined",
    "quarantined_data_drift",
    "rejected_multiplicity",
    "rejected_train_hard_gate",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def stable_hash(payload: Any, length: int = 16) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:length]


def accepted_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("top") or payload.get("rows") or []
    return [row for row in rows if isinstance(row, dict) and row.get("advance_passed")]


def best_accepted_row(payload: dict[str, Any]) -> dict[str, Any]:
    rows = accepted_rows(payload)
    if not rows:
        return {}

    def score(row: dict[str, Any]) -> float:
        selection = row.get("selection") or {}
        cost40 = selection.get("cost40") or row.get("cost40") or {}
        try:
            return float(cost40.get("sharpe") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return sorted(rows, key=score, reverse=True)[0]


def family_kind(payload: dict[str, Any], artifact: str = "") -> str:
    text = f"{payload.get('kind', '')} {artifact}".lower()
    if "tsmom" in text:
        return "tsmom"
    if "xsec_ohlcv" in text:
        return "xsec_ohlcv"
    return "unknown"


def bucket_hours(value: Any) -> str:
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if hours <= 168:
        return "fast"
    if hours <= 360:
        return "medium"
    if hours <= 720:
        return "slow"
    return "ultra"


def bucket_drawdown_stop(value: Any) -> str:
    try:
        stop = float(value or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if stop <= 0.0:
        return "none"
    if stop <= 0.10:
        return "tight"
    if stop <= 0.15:
        return "medium"
    return "wide"


def normalize_symbols(payload: dict[str, Any], row: dict[str, Any]) -> list[str]:
    symbols = (
        payload.get("symbols")
        or (payload.get("data") or {}).get("symbols")
        or row.get("symbols")
        or []
    )
    return sorted(str(symbol) for symbol in symbols)


def normalized_family_payload(payload: dict[str, Any], artifact: str = "") -> dict[str, Any]:
    row = best_accepted_row(payload)
    config = dict(row.get("config") or {})
    lookbacks = row.get("lookbacks_h") or config.get("lookbacks_h") or []
    if not lookbacks and config.get("lookback_h") is not None:
        lookbacks = [config.get("lookback_h")]
    primary_lookback = lookbacks[0] if lookbacks else config.get("lookback_h")
    symbols = normalize_symbols(payload, row)
    kind = family_kind(payload, artifact)
    return {
        "kind": kind,
        "signal": str(config.get("score_mode") or config.get("family") or config.get("preset") or kind),
        "side": str(config.get("side") or ("long_only" if kind == "xsec_ohlcv" else "unknown")),
        "lookback_bucket": bucket_hours(primary_lookback),
        "market_filter_bucket": bucket_hours(config.get("market_filter_h")),
        "rebalance_h": int(config.get("rebalance_h") or 0),
        "n_tranches": int(config.get("n_tranches") or 1),
        "drawdown_stop_bucket": bucket_drawdown_stop(config.get("drawdown_stop")),
        "cooldown_bucket": bucket_hours(config.get("cooldown_h")),
        "universe_hash": stable_hash(symbols, 12),
    }


def family_fingerprint(payload: dict[str, Any], artifact: str = "") -> str:
    return stable_hash(normalized_family_payload(payload, artifact), 20)


def status_from_candidate(candidate: dict[str, Any]) -> str:
    raw = str(candidate.get("status") or "seen")
    if raw in BLOCKING_STATUSES or raw.startswith("rejected") or "quarantined" in raw:
        return raw
    return "seen"


def load_registry(path: Path) -> dict[str, Any]:
    registry = read_json(path)
    if not registry:
        return {"kind": "v9_family_registry_v1", "created_at": now_utc(), "families": {}}
    registry.setdefault("kind", "v9_family_registry_v1")
    registry.setdefault("families", {})
    return registry


def family_blocks_queue(entry: dict[str, Any]) -> bool:
    status = str(entry.get("status") or "")
    return status in BLOCKING_STATUSES or status.startswith("rejected") or "quarantined" in status


def upsert_family(
    registry: dict[str, Any],
    *,
    fingerprint: str,
    family: dict[str, Any],
    candidate: dict[str, Any],
    artifact: str,
    train_metric: float | None = None,
    seen_at: str | None = None,
) -> tuple[dict[str, Any], bool]:
    families = registry.setdefault("families", {})
    created = fingerprint not in families
    timestamp = seen_at or now_utc()
    entry = families.setdefault(
        fingerprint,
        {
            "fingerprint": fingerprint,
            "family": family,
            "status": "seen",
            "seen_count": 0,
            "first_seen": timestamp,
            "last_seen": timestamp,
            "artifacts": [],
            "tasks": [],
            "best_train_metric": None,
        },
    )
    entry["last_seen"] = timestamp
    entry["seen_count"] = int(entry.get("seen_count") or 0) + 1
    if artifact and artifact not in entry["artifacts"]:
        entry["artifacts"].append(artifact)
    task = candidate.get("task")
    if task and task not in entry["tasks"]:
        entry["tasks"].append(task)
    candidate_status = status_from_candidate(candidate)
    if family_blocks_queue({"status": candidate_status}):
        entry["status"] = candidate_status
    elif not family_blocks_queue(entry):
        entry["status"] = entry.get("status") or "seen"
    if train_metric is not None:
        previous = entry.get("best_train_metric")
        if previous is None or float(train_metric) > float(previous):
            entry["best_train_metric"] = float(train_metric)
    registry["updated_at"] = timestamp
    return entry, created


def queue_allowed(entry: dict[str, Any], candidate: dict[str, Any], *, require_novel: bool = True) -> bool:
    if require_novel and int(entry.get("seen_count") or 0) != 1:
        return False
    if family_blocks_queue(entry):
        return False
    status = str(candidate.get("status") or "")
    if not status or status == "manual_review_required":
        return True
    return status in {"seen", "accepted_train_only_candidate_found"}
