#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

BASE = Path("/root/.openclaw/workspace/kimi-shared-brain")
STATE = BASE / "state"
LOGS = BASE / "logs"
SUMMARY = STATE / "latest_strategy_summary.txt"
FOUND = STATE / "FOUND_STRATEGY_READY.txt"
FOUND_VALIDATED = STATE / "FOUND_VALIDATED_CANDIDATE.txt"
RUN_ID_FILE = STATE / "autohunter_run_id.txt"

SEARCH_TEMPLATE = """cd {base} && /usr/bin/time -f wall=%e python3 scripts/lunar_genome_symbol_local_search_v7_doc_tailfirst.py \
--seed-scan state/lunar_genome_symbol_local_search_v7_multi_doc_tailfirst_scout_evolve1000.json \
--seed-scan state/lunar_genome_symbol_validate_v7_multi_tailfirst_72_all50.json \
--seed-scan state/lunar_genome_symbol_local_search_v7_btc_doc_fullhist_balanced_tail_evolve1000.json \
--seed-scan state/lunar_genome_symbol_local_search_v7_btc_doc_audit_rows_evolve1000.json \
--symbols BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT LINKUSDT AVAXUSDT --start 2017-08 --end 2026-05 \
--epochs 500 --population 18 --elites 6 --seed-rows 220 --seed {seed} \
--scenarios 24 --scenario-costs 20,30,50 --months-per-symbol 4 --window-bars 12000 \
--min-survival-rate 1.0 --min-positive-alpha-frac 1.0 --min-alpha 0.0 \
--max-drawdown 0.20 --max-trades 2400 --min-trades 120 --min-notional 10 \
--mut-prob 0.11 --mut-scale 0.006 --regime-gate-prob 0.95 --regime-gate-scale 0.28 \
--regime-core-prob 0.18 --regime-core-scale 0.004 --regime-core-mix 0.82 \
--explorer-regime-gate-frac 0.18 --seed-mutant-frac 0.84 --crossover-frac 0.07 \
--prune-after 18 --prune-min-alpha -0.004 --prune-max-failures 1 --audit-top 10 --checkpoint-every 1 \
--out state/lunar_genome_symbol_local_search_v7_core8_autohunt_{run_id}.json \
> logs/ga_core8_autohunt_{run_id}.log 2>&1"""


def sh(cmd: str) -> str:
    return subprocess.run(
        cmd,
        shell=True,
        cwd=BASE,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout.strip()


def tmux_has(name: str) -> bool:
    out = sh(f"tmux has-session -t {name} 2>/dev/null; echo $?")
    return out.splitlines()[-1].strip() == "0"


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def metrics_from_rows(rows):
    if not rows:
        return None

    def met(row):
        return row.get("metrics") or row

    first = rows[0]
    br = max(rows, key=lambda row: met(row).get("qualified_rows", -1))
    bm = max(rows, key=lambda row: met(row).get("min_alpha", -999))
    parts = []
    for label, row in [("FIRST", first), ("BR", br), ("BM", bm)]:
        m = met(row)
        parts.append(
            f"{label}:{row.get('symbol')} {m.get('qualified_rows')}/{m.get('scenario_count')} "
            f"min={float(m.get('min_alpha', 0)):.6f} avg={float(m.get('avg_alpha', 0)):.6f} "
            f"mdd={float(m.get('max_drawdown', 0)):.4f} trades={m.get('trades')} q={row.get('qualified')}"
        )
    return " | ".join(parts)


def strict_rows(rows):
    out = []
    for row in rows:
        m = row.get("metrics") or row
        if (
            row.get("qualified")
            and m.get("qualified_rows") == m.get("scenario_count")
            and float(m.get("min_alpha", -999)) >= 0
        ):
            out.append(row)
    return out


def current_run_id() -> int:
    try:
        return int(RUN_ID_FILE.read_text().strip())
    except Exception:
        RUN_ID_FILE.write_text("1")
        return 1


def latest_archive() -> Path | None:
    candidates = sorted(
        STATE.glob("lunar_genome_symbol_local_search_v7_core*_autohunt_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    base = STATE / "lunar_genome_symbol_local_search_v7_core3_doc_tailfirst_hard72_evolve500.json"
    all_paths = candidates + ([base] if base.exists() else [])
    return all_paths[0] if all_paths else None


def launch_search(run_id: int) -> str:
    session = f"ga_core8_autohunt_{run_id}"
    if tmux_has(session):
        return session
    seed = 880000 + run_id
    cmd = SEARCH_TEMPLATE.format(base=str(BASE), seed=seed, run_id=run_id)
    sh(f"tmux new -d -s {session} {json.dumps(cmd)}")
    return session


def launch_validation(archive: Path) -> None:
    tag = archive.stem.replace("lunar_genome_symbol_local_search_v7_", "")
    out = STATE / f"autohunt_validate_{tag}_independent72.json"
    session = f"validate_{tag[:40]}"
    if out.exists() or tmux_has(session):
        return
    cmd = (
        f"cd {BASE} && /usr/bin/time -f wall=%e python3 scripts/lunar_genome_symbol_validate_v7.py "
        f"--archive {archive} --out {out} --limit 30 --seed 20260711 "
        f"--symbols BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT LINKUSDT AVAXUSDT --start 2017-08 --end 2026-05 "
        f"--scenarios 24 --scenario-costs 20,30,50 --months-per-symbol 4 --window-bars 12000 "
        f"--min-survival-rate 1.0 --min-positive-alpha-frac 1.0 --min-alpha 0.0 "
        f"--max-drawdown 0.20 --max-trades 2200 --min-trades 120 --min-notional 10 "
        f"> logs/{out.stem}.log 2>&1"
    )
    sh(f"tmux new -d -s {session} {json.dumps(cmd)}")


def check_validations() -> bool:
    for path in sorted(
        STATE.glob("autohunt_validate_*_independent72.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        obj = load_json(path)
        if not obj:
            continue
        good = strict_rows(obj.get("qualified") or [])
        if good:
            row = good[0]
            m = row.get("metrics") or row
            FOUND_VALIDATED.write_text(
                f"FOUND_VALIDATED_CANDIDATE {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                f"file={path.name} symbol={row.get('symbol')} "
                f"rows={m.get('qualified_rows')}/{m.get('scenario_count')} "
                f"min_alpha={m.get('min_alpha')} avg_alpha={m.get('avg_alpha')} "
                f"mdd={m.get('max_drawdown')} trades={m.get('trades')} "
                f"note=validated_only_requires_walkforward_montecarlo_paper_before_ready\n"
            )
            return True
    return False


def tick() -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if check_validations():
        SUMMARY.write_text(FOUND_VALIDATED.read_text())
        return

    archive = latest_archive()
    line = f"{now} no_archive"
    if archive:
        obj = load_json(archive)
        if obj:
            rows = obj.get("top") or []
            good = strict_rows((obj.get("qualified") or []) + rows)
            qcount = int(obj.get("qualified_count") or 0)
            line = (
                f"{now} archive={archive.name} epoch={obj.get('epoch')} "
                f"qcount={qcount} strict={len(good)} "
                + (metrics_from_rows(rows) or "no_rows")
            )
            if good:
                launch_validation(archive)
        else:
            line = f"{now} archive={archive.name} unreadable"

    active = sh("tmux ls 2>/dev/null | grep -E 'ga_core[0-9]+_(autohunt|tailfirst_hard72)' || true")
    if not active and not FOUND.exists():
        run_id = current_run_id() + 1
        RUN_ID_FILE.write_text(str(run_id))
        session = launch_search(run_id)
        line += f" launched={session}"

    SUMMARY.write_text(line + "\n")


def main() -> None:
    STATE.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    while True:
        try:
            tick()
        except Exception as exc:
            SUMMARY.write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} monitor_error={exc!r}\n")
        time.sleep(600)


if __name__ == "__main__":
    main()
