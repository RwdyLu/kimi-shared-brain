from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def accepted_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    for row in payload.get("rows", []):
        if row.get("advance_passed"):
            return row
    for row in payload.get("top", []):
        if row.get("advance_passed"):
            return row
    return None


def canonical_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if config is None:
        return None
    out = dict(config)
    out.setdefault("n_tranches", 1)
    return out


def candidate_signature(payload: dict[str, Any]) -> str | None:
    if not payload.get("summary", {}).get("accepted_train_only"):
        return None
    row = accepted_row(payload)
    if not row:
        return None
    return json.dumps(
        {
            "kind": payload.get("kind"),
            "symbols": payload.get("symbols"),
            "config": canonical_config(row.get("config")),
        },
        sort_keys=True,
    )


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        enriched = dict(candidate)
        signature = None
        path = candidate.get("output_json")
        if path:
            payload = read_json(Path(str(path)))
            signature = candidate_signature(payload) if payload else None
        if signature:
            enriched["signature"] = signature
        if signature and signature in seen:
            enriched["duplicate_of"] = seen[signature]
        elif signature:
            seen[signature] = str(candidate.get("task"))
        out.append(enriched)
    return out


def distinct_candidate_count(candidates: list[dict[str, Any]]) -> int:
    signatures = {row.get("signature") for row in dedupe_candidates(candidates)}
    signatures.discard(None)
    return len(signatures)
