#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


BASE = Path("/root/.openclaw/workspace/kimi-shared-brain")
STATE = BASE / "state"
LOGS = BASE / "logs"
CACHE = BASE / "data" / "binance_public_cache"
SUMMARY = STATE / "latest_strategy_summary.txt"
FOUND = STATE / "FOUND_STRATEGY_READY.txt"
STAGE_STATE = STATE / "staged_autohunter_state.json"

SYMBOLS = "BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT ADAUSDT LINKUSDT AVAXUSDT"
SEED_SCANS = [
    "state/lunar_genome_symbol_local_search_v7_multi_doc_tailfirst_scout_evolve1000.json",
    "state/lunar_genome_symbol_validate_v7_multi_tailfirst_72_all50.json",
    "state/lunar_genome_symbol_local_search_v7_btc_doc_fullhist_balanced_tail_evolve1000.json",
    "state/lunar_genome_symbol_local_search_v7_btc_doc_audit_rows_evolve1000.json",
]


@dataclass(frozen=True)
class Stage:
    name: str
    timeframe: str
    window_bars: int
    min_trades: int
    max_trades: int
    months_per_symbol: int = 4
    epochs: int = 1000
    population: int = 18
    elites: int = 6
    seed_rows: int = 220


@dataclass(frozen=True)
class Profile:
    name: str
    population: int
    elites: int
    mut_prob: float
    mut_scale: float
    regime_gate_scale: float
    regime_core_prob: float
    explorer_regime_gate_frac: float
    seed_mutant_frac: float
    crossover_frac: float
    trade_min_mult: float = 1.0
    trade_max_mult: float = 1.0
    prune_min_alpha: float = -0.004
    prune_max_failures: int = 1


STAGES = [
    Stage("macro4h_core8", "4h", 3000, 18, 360, months_per_symbol=12),
    Stage("lowfreq1h_core8", "1h", 5000, 36, 720),
    Stage("swing15m_core8", "15m", 8000, 72, 1440),
    Stage("intraday5m_core8", "5m", 10000, 96, 1800),
    Stage("controlled1m_core8", "1m", 12000, 120, 2400),
]

PROFILES = [
    Profile("balanced", 18, 6, 0.12, 0.006, 0.30, 0.18, 0.20, 0.82, 0.08),
    Profile("lowtrade", 20, 6, 0.16, 0.008, 0.42, 0.22, 0.28, 0.76, 0.10, trade_min_mult=0.80, trade_max_mult=0.60),
    Profile("explorer", 24, 8, 0.24, 0.012, 0.65, 0.30, 0.45, 0.62, 0.18, trade_min_mult=0.70, trade_max_mult=1.15, prune_min_alpha=-0.006, prune_max_failures=2),
]

RESAMPLE_RULES = {
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
}

EXPECTED_INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}

MAX_MONTH_ROWS = {
    "1m": 45_500,
    "5m": 9_200,
    "15m": 3_100,
    "1h": 800,
    "4h": 210,
}


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


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STAGE_STATE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def seed_args(stage: Stage) -> str:
    if stage.timeframe in {"4h", "1h", "15m"}:
        return ""
    return " ".join(f"--seed-scan {path}" for path in SEED_SCANS if (BASE / path).exists())


def strict_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        m = row.get("metrics") or row
        if (
            row.get("qualified")
            and m.get("qualified_rows") == m.get("scenario_count")
            and float(m.get("min_alpha", -999)) >= 0
            and float(m.get("min_return", -999)) >= 0
            and float(m.get("max_drawdown", 999)) <= 0.20
        ):
            out.append(row)
    return out


def row_summary(row: dict) -> str:
    m = row.get("metrics") or row
    return (
        f"{row.get('symbol')} {m.get('qualified_rows')}/{m.get('scenario_count')} "
        f"min={float(m.get('min_alpha', 0)):.6f} avg={float(m.get('avg_alpha', 0)):.6f} "
        f"ret={float(m.get('min_return', 0)):.6f} mdd={float(m.get('max_drawdown', 0)):.4f} "
        f"trades={m.get('trades')} q={row.get('qualified')}"
    )


def trade_band(stage: Stage, profile: Profile) -> tuple[int, int]:
    min_trades = max(1, int(round(stage.min_trades * profile.trade_min_mult)))
    max_trades = max(min_trades, int(round(stage.max_trades * profile.trade_max_mult)))
    return min_trades, max_trades


def archive_path(stage: Stage, profile: Profile) -> Path:
    return STATE / f"lunar_genome_symbol_local_search_v7_{stage.name}_{profile.name}_evolve1000.json"


def smoke_path(stage: Stage) -> Path:
    return STATE / f"lunar_genome_symbol_local_search_v7_{stage.name}_smoke.json"


def validate_path(stage: Stage, profile: Profile) -> Path:
    return STATE / f"lunar_genome_symbol_validate_v7_{stage.name}_{profile.name}_independent72.json"


def walkforward_path(stage: Stage, profile: Profile) -> Path:
    return STATE / f"lunar_genome_symbol_walkforward_v7_{stage.name}_{profile.name}_terminal.json"


def normalize_open_time_ms(series: pd.Series) -> pd.Series:
    ts = pd.to_numeric(series, errors="coerce")
    clean = ts.dropna()
    if clean.empty:
        return ts.astype("Int64")
    median_value = float(clean.median())
    if median_value > 10_000_000_000_000:
        ts = ts / 1000.0
    elif median_value < 10_000_000_000:
        ts = ts * 1000.0
    return ts.round().astype("Int64")


def cache_file_usable(path: Path, timeframe: str) -> bool:
    if not path.exists() or path.stat().st_size <= 1000:
        return False
    try:
        df = pd.read_parquet(path, columns=["open_time", "close"])
    except Exception:
        return False
    if df.empty:
        return False
    max_rows = MAX_MONTH_ROWS.get(timeframe)
    if max_rows and len(df) > max_rows:
        return False
    expected = EXPECTED_INTERVAL_MS.get(timeframe)
    if expected and len(df) > 2:
        ts = normalize_open_time_ms(df["open_time"]).dropna().astype("int64")
        diffs = ts.sort_values().diff().dropna()
        diffs = diffs[diffs > 0]
        if diffs.empty:
            return False
        median_diff = float(diffs.median())
        if abs(median_diff - expected) > expected * 0.05:
            return False
    return True


def prepare_resampled_cache(stage: Stage) -> tuple[int, int]:
    if stage.timeframe == "1m":
        return (0, 0)
    rule = RESAMPLE_RULES[stage.timeframe]
    created = 0
    available = 0
    for symbol in SYMBOLS.split():
        for src in sorted(CACHE.glob(f"{symbol}_1m_*.parquet")):
            month = src.stem.rsplit("_", 1)[-1]
            dst = CACHE / f"{symbol}_{stage.timeframe}_{month}.parquet"
            if cache_file_usable(dst, stage.timeframe):
                available += 1
                continue
            if dst.exists():
                try:
                    dst.unlink()
                except Exception:
                    continue
            try:
                df = pd.read_parquet(src, columns=["open_time", "open", "high", "low", "close"])
                if df.empty:
                    continue
                df["open_time"] = normalize_open_time_ms(df["open_time"])
                df = df.dropna(subset=["open_time"]).sort_values("open_time").drop_duplicates("open_time")
                idx = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
                ohlc = (
                    df.assign(_ts=idx)
                    .set_index("_ts")
                    .resample(rule, label="left", closed="left")
                    .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
                    .dropna()
                    .reset_index()
                )
                if len(ohlc) < 100:
                    continue
                ts = ohlc.pop("_ts").astype("int64")
                if int(ts.max()) > 10_000_000_000_000:
                    ts = ts // 1_000_000
                ohlc.insert(0, "open_time", ts.astype("int64"))
                ohlc.to_parquet(dst, index=False)
                if cache_file_usable(dst, stage.timeframe):
                    created += 1
                    available += 1
                else:
                    dst.unlink(missing_ok=True)
            except Exception:
                continue
    return (created, available)


def command_common(stage: Stage, profile: Profile) -> str:
    min_trades, max_trades = trade_band(stage, profile)
    return (
        f"{seed_args(stage)} --symbols {SYMBOLS} --timeframe {stage.timeframe} "
        f"--start 2017-08 --end 2026-05 --months-per-symbol {stage.months_per_symbol} "
        f"--window-bars {stage.window_bars} --scenario-costs 20,30,50 "
        f"--min-survival-rate 1.0 --min-positive-alpha-frac 1.0 --min-alpha 0.0 --min-return 0.0 "
        f"--max-drawdown 0.20 --max-trades {max_trades} --min-trades {min_trades} "
        f"--min-notional 10"
    )


def search_command(stage: Stage, profile: Profile, out: Path, smoke: bool) -> str:
    epochs = 1 if smoke else stage.epochs
    population = 4 if smoke else profile.population
    scenarios = 2 if smoke else 24
    audit_top = 3 if smoke else 10
    seed = 920000 + STAGES.index(stage) * 1000 + PROFILES.index(profile) * 100 + (1 if smoke else 50)
    return (
        f"cd {BASE} && /usr/bin/time -f wall=%e python3 scripts/lunar_genome_symbol_local_search_v7_doc_tailfirst.py "
        f"{command_common(stage, profile)} --epochs {epochs} --population {population} --elites {min(profile.elites, population)} "
        f"--seed-rows {stage.seed_rows} --seed {seed} --scenarios {scenarios} "
        f"--mut-prob {profile.mut_prob} --mut-scale {profile.mut_scale} --regime-gate-prob 0.95 --regime-gate-scale {profile.regime_gate_scale} "
        f"--regime-core-prob {profile.regime_core_prob} --regime-core-scale 0.004 --regime-core-mix 0.82 "
        f"--explorer-regime-gate-frac {profile.explorer_regime_gate_frac} --seed-mutant-frac {profile.seed_mutant_frac} --crossover-frac {profile.crossover_frac} "
        f"--prune-after 18 --prune-min-alpha {profile.prune_min_alpha} --prune-max-failures {profile.prune_max_failures} "
        f"--audit-top {audit_top} --checkpoint-every 1 --out {out}"
    )


def validate_command(stage: Stage, profile: Profile) -> str:
    min_trades, max_trades = trade_band(stage, profile)
    return (
        f"cd {BASE} && /usr/bin/time -f wall=%e python3 scripts/lunar_genome_symbol_validate_v7.py "
        f"--archive {archive_path(stage, profile)} --out {validate_path(stage, profile)} --limit 30 --seed {930000 + STAGES.index(stage) * 100 + PROFILES.index(profile)} "
        f"--symbols {SYMBOLS} --timeframe {stage.timeframe} --start 2017-08 --end 2026-05 "
        f"--months-per-symbol {stage.months_per_symbol} --window-bars {stage.window_bars} --scenarios 24 "
        f"--scenario-costs 20,30,50 --min-survival-rate 1.0 --min-positive-alpha-frac 1.0 --min-alpha 0.0 "
        f"--max-drawdown 0.20 --max-trades {max_trades} --min-trades {min_trades} --min-notional 10"
    )


def walkforward_command(stage: Stage, profile: Profile) -> str:
    min_trades, max_trades = trade_band(stage, profile)
    return (
        f"cd {BASE} && /usr/bin/time -f wall=%e python3 scripts/lunar_genome_symbol_walkforward_v7.py "
        f"--archive {validate_path(stage, profile)} --out {walkforward_path(stage, profile)} --limit 20 --seed {940000 + STAGES.index(stage) * 100 + PROFILES.index(profile)} "
        f"--symbols {SYMBOLS} --timeframe {stage.timeframe} --start 2017-08 --end 2026-05 "
        f"--window-months 18 --step-months 9 --months-per-symbol {stage.months_per_symbol} "
        f"--window-bars {stage.window_bars} --scenarios 6 --scenario-costs 20,30,50 "
        f"--min-survival-rate 1.0 --min-positive-alpha-frac 1.0 --min-alpha 0.0 "
        f"--max-drawdown 0.20 --max-trades {max_trades} --min-trades {min_trades} --min-notional 10"
    )


def launch_session(name: str, command: str, log: Path) -> None:
    if tmux_has(name):
        return
    wrapped = f"{command} > {log} 2>&1"
    sh(f"tmux new -d -s {name} {json.dumps(wrapped)}")


def process_validation(stage: Stage, profile: Profile) -> bool:
    path = walkforward_path(stage, profile)
    obj = load_json(path)
    rows = obj.get("qualified") or []
    good = [
        row
        for row in rows
        if (
            row.get("qualified")
            and row.get("passed_windows") == row.get("window_count")
            and float(row.get("min_alpha", -999)) >= 0
            and float(row.get("min_return", -999)) >= 0
            and float(row.get("max_drawdown", 999)) <= 0.20
        )
    ]
    if not good:
        return False
    best = max(good, key=lambda row: (float(row.get("min_alpha", -999)), float(row.get("avg_alpha", -999))))
    metrics = {
        "qualified_rows": best.get("passed_windows"),
        "scenario_count": best.get("window_count"),
        "min_alpha": best.get("min_alpha"),
        "avg_alpha": best.get("avg_alpha"),
        "min_return": best.get("min_return"),
        "avg_return": best.get("avg_return"),
        "max_drawdown": best.get("max_drawdown"),
        "trades": best.get("trades"),
    }
    ready = {
        "symbol": best.get("symbol"),
        "qualified": best.get("qualified"),
        "metrics": metrics,
    }
    FOUND.write_text(
        f"FOUND {now()} stage={stage.name} profile={profile.name} validation={validate_path(stage, profile).name} "
        f"walkforward={path.name} {row_summary(ready)}\n"
    )
    SUMMARY.write_text(FOUND.read_text())
    return True


def summarize_stage(stage: Stage, profile: Profile, phase: str) -> str:
    archive = archive_path(stage, profile)
    obj = load_json(archive)
    if not obj:
        return f"{now()} stage={stage.name} profile={profile.name} phase={phase} no_archive tf={stage.timeframe}"
    rows = obj.get("top") or []
    strict = strict_rows((obj.get("qualified") or []) + rows)
    best = "no_rows"
    if rows:
        by_rows = max(rows, key=lambda row: (row.get("metrics") or row).get("qualified_rows", -1))
        by_min = max(rows, key=lambda row: (row.get("metrics") or row).get("min_alpha", -999))
        best = f"BR:{row_summary(by_rows)} | BM:{row_summary(by_min)}"
    min_trades, max_trades = trade_band(stage, profile)
    return (
        f"{now()} stage={stage.name} profile={profile.name} phase={phase} tf={stage.timeframe} "
        f"epoch={obj.get('epoch')} strict={len(strict)} trade_band={min_trades}-{max_trades} {best}"
    )


def stage_done(stage: Stage, profile: Profile) -> bool:
    obj = load_json(archive_path(stage, profile))
    return int(obj.get("epoch") or 0) >= stage.epochs


def next_profile_or_stage(data: dict, idx: int, pidx: int) -> dict:
    if pidx + 1 < len(PROFILES):
        return {"stage_index": idx, "profile_index": pidx + 1, "phase": "smoke", "cache_ready": True}
    return {"stage_index": idx + 1, "profile_index": 0, "phase": "smoke"}


def tick() -> None:
    if FOUND.exists() and FOUND.read_text().strip().startswith("FOUND"):
        SUMMARY.write_text(FOUND.read_text())
        return

    data = load_json(STAGE_STATE) or {"stage_index": 0, "profile_index": 0, "phase": "smoke"}
    idx = int(data.get("stage_index", 0))
    if idx >= len(STAGES):
        SUMMARY.write_text(f"{now()} status=finished_all_stages no_validated_strategy_found\n")
        return

    stage = STAGES[idx]
    pidx = int(data.get("profile_index", 0))
    if pidx >= len(PROFILES):
        data = {"stage_index": idx + 1, "profile_index": 0, "phase": "smoke"}
        save_state(data)
        SUMMARY.write_text(f"{now()} stage={stage.name} profiles_exhausted advancing_next_stage\n")
        return
    profile = PROFILES[pidx]
    phase = data.get("phase", "smoke")
    if phase == "smoke":
        if not data.get("cache_ready"):
            created, available = prepare_resampled_cache(stage)
            data["cache_ready"] = True
            data["cache_created"] = created
            data["cache_available"] = available
            save_state(data)
            SUMMARY.write_text(
                f"{now()} stage={stage.name} phase=prepare_cache tf={stage.timeframe} "
                f"created={created} available={available}\n"
            )
            return
        out = smoke_path(stage)
        session = f"smoke_{stage.name}_{profile.name}"[:80]
        if not out.exists():
            launch_session(session, search_command(stage, profile, out, smoke=True), LOGS / f"{session}.log")
            SUMMARY.write_text(f"{now()} stage={stage.name} profile={profile.name} phase=smoke launched tf={stage.timeframe}\n")
            return
        data["phase"] = "search"
        save_state(data)
        phase = "search"

    if phase == "search":
        session = f"ga_{stage.name}_{profile.name}"[:80]
        if not stage_done(stage, profile):
            launch_session(session, search_command(stage, profile, archive_path(stage, profile), smoke=False), LOGS / f"{session}.log")
            SUMMARY.write_text(summarize_stage(stage, profile, "search") + f" session={session}\n")
            return
        data["phase"] = "validate"
        save_state(data)
        phase = "validate"

    if phase == "validate":
        if process_validation(stage, profile):
            return
        session = f"val_{stage.name}_{profile.name}"[:80]
        validation = load_json(validate_path(stage, profile))
        if not validation:
            launch_session(session, validate_command(stage, profile), LOGS / f"{session}.log")
            SUMMARY.write_text(summarize_stage(stage, profile, "validate") + f" session={session}\n")
            return
        independent_good = strict_rows((validation.get("qualified") or []) + (validation.get("top") or []))
        if independent_good and not walkforward_path(stage, profile).exists():
            wf_session = f"wf_{stage.name}_{profile.name}"[:80]
            launch_session(wf_session, walkforward_command(stage, profile), LOGS / f"{wf_session}.log")
            SUMMARY.write_text(
                f"{now()} stage={stage.name} profile={profile.name} phase=walkforward candidates={len(independent_good)} "
                f"session={wf_session}\n"
            )
            return
        if independent_good and walkforward_path(stage, profile).exists():
            wf = load_json(walkforward_path(stage, profile))
            SUMMARY.write_text(
                f"{now()} stage={stage.name} profile={profile.name} walkforward_failed "
                f"qualified_count={wf.get('qualified_count', 0)} advancing_next_profile_or_stage\n"
            )
        else:
            SUMMARY.write_text(f"{now()} stage={stage.name} profile={profile.name} independent_validation_failed advancing_next_profile_or_stage\n")
        data = next_profile_or_stage(data, idx, pidx)
        save_state(data)


def main() -> None:
    STATE.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    if not FOUND.exists():
        FOUND.write_text("none\n")
    while True:
        try:
            tick()
        except Exception as exc:
            SUMMARY.write_text(f"{now()} staged_monitor_error={exc!r}\n")
        time.sleep(300)


if __name__ == "__main__":
    main()
