#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_contract_latest_market_signal_watch}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/v9_contract_market_signal"
LOG="$LOG_DIR/watch_$(date -u +%Y%m%dT%H%M%SZ).log"

TIMEFRAME="${CONTRACT_MARKET_TIMEFRAME:-1h}"
TIMEFRAME_SAFE="$(printf '%s' "$TIMEFRAME" | tr -c '[:alnum:]' '_')"
TOP_N="${CONTRACT_MARKET_TOP_N:-20}"
SLEEP_SEC="${CONTRACT_MARKET_SIGNAL_SLEEP_SEC:-900}"
LOOKBACK_BARS_IF_EMPTY="${CONTRACT_MARKET_LOOKBACK_BARS_IF_EMPTY:-20000}"
CACHE_DIR="${CONTRACT_MARKET_CACHE_DIR:-data/binance_usdm_ohlcv_cache}"
UNIVERSE_JSON="${CONTRACT_MARKET_UNIVERSE_JSON:-artifacts/v9/universe/binance_usdm_top20_volume_snapshot.json}"
API_URL="${CONTRACT_MARKET_KLINES_API:-https://fapi.binance.com/fapi/v1/klines}"
if [[ "$TIMEFRAME" == "1h" ]]; then
  DEFAULT_UPDATE_STATE_JSON="artifacts/v9/watchdog/binance_usdm_ohlcv_top20_update_status.json"
  DEFAULT_SIGNAL_JSON="artifacts/v9/contract_lab/contract_latest_market_signal_latest.json"
  DEFAULT_SIGNAL_MD="artifacts/v9/contract_lab/contract_latest_market_signal_latest.md"
  DEFAULT_JOURNAL_JSONL="state/contract_latest_market_signal_journal.jsonl"
  DEFAULT_SHADOW_JOURNAL_JSONL="state/contract_latest_market_signal_shadow_journal.jsonl"
  DEFAULT_FAST_SHADOW_JOURNAL_JSONL="state/contract_latest_market_signal_fast_shadow_journal.jsonl"
  DEFAULT_MARKER="state/FOUND_CONTRACT_MARKET_PAPER_PLAN.txt"
  DEFAULT_NO_MARKER="state/NO_CONTRACT_MARKET_PAPER_PLAN.txt"
  DEFAULT_ANALOG_MARKER="state/FOUND_CONTRACT_MARKET_ANALOG_PAPER_PLAN.txt"
  DEFAULT_ANALOG_NO_MARKER="state/NO_CONTRACT_MARKET_ANALOG_PAPER_PLAN.txt"
else
  DEFAULT_UPDATE_STATE_JSON="artifacts/v9/watchdog/binance_usdm_ohlcv_top20_${TIMEFRAME_SAFE}_update_status.json"
  DEFAULT_SIGNAL_JSON="artifacts/v9/contract_lab/contract_latest_market_signal_${TIMEFRAME_SAFE}_latest.json"
  DEFAULT_SIGNAL_MD="artifacts/v9/contract_lab/contract_latest_market_signal_${TIMEFRAME_SAFE}_latest.md"
  DEFAULT_JOURNAL_JSONL="state/contract_latest_market_signal_${TIMEFRAME_SAFE}_journal.jsonl"
  DEFAULT_SHADOW_JOURNAL_JSONL="state/contract_latest_market_signal_${TIMEFRAME_SAFE}_shadow_journal.jsonl"
  DEFAULT_FAST_SHADOW_JOURNAL_JSONL="state/contract_latest_market_signal_${TIMEFRAME_SAFE}_fast_shadow_journal.jsonl"
  DEFAULT_MARKER="state/FOUND_CONTRACT_MARKET_${TIMEFRAME_SAFE}_PAPER_PLAN.txt"
  DEFAULT_NO_MARKER="state/NO_CONTRACT_MARKET_${TIMEFRAME_SAFE}_PAPER_PLAN.txt"
  DEFAULT_ANALOG_MARKER="state/FOUND_CONTRACT_MARKET_${TIMEFRAME_SAFE}_ANALOG_PAPER_PLAN.txt"
  DEFAULT_ANALOG_NO_MARKER="state/NO_CONTRACT_MARKET_${TIMEFRAME_SAFE}_ANALOG_PAPER_PLAN.txt"
fi
UPDATE_STATE_JSON="${CONTRACT_MARKET_UPDATE_STATE_JSON:-$DEFAULT_UPDATE_STATE_JSON}"
SIGNAL_JSON="${CONTRACT_MARKET_SIGNAL_JSON:-$DEFAULT_SIGNAL_JSON}"
SIGNAL_MD="${CONTRACT_MARKET_SIGNAL_MD:-$DEFAULT_SIGNAL_MD}"
JOURNAL_JSONL="${CONTRACT_MARKET_JOURNAL_JSONL:-$DEFAULT_JOURNAL_JSONL}"
SHADOW_JOURNAL_JSONL="${CONTRACT_MARKET_SHADOW_JOURNAL_JSONL:-$DEFAULT_SHADOW_JOURNAL_JSONL}"
FAST_SHADOW_JOURNAL_JSONL="${CONTRACT_MARKET_FAST_SHADOW_JOURNAL_JSONL:-$DEFAULT_FAST_SHADOW_JOURNAL_JSONL}"
BLOCKED_PAIRS_JSON="${CONTRACT_MARKET_BLOCKED_PAIRS_JSON:-state/contract_paper_blocked_pairs.json}"
ACTIONS_JSON="${CONTRACT_MARKET_ACTIONS_JSON:-artifacts/v9/contract_lab/contract_paper_strategy_actions_latest.json}"
SHADOW_PROMOTE_MARKER="${CONTRACT_MARKET_SHADOW_PROMOTE_MARKER:-state/FOUND_CURRENT_POLICY_SHADOW_PROMOTE.txt}"
SHADOW_NO_PROMOTE_MARKER="${CONTRACT_MARKET_SHADOW_NO_PROMOTE_MARKER:-state/NO_CURRENT_POLICY_SHADOW_PROMOTE.txt}"
SHADOW_READINESS_MARKER="${CONTRACT_MARKET_SHADOW_READINESS_MARKER:-state/CURRENT_POLICY_SHADOW_READINESS.txt}"
SHADOW_READINESS_JSON="${CONTRACT_MARKET_SHADOW_READINESS_JSON:-state/current_policy_shadow_readiness.json}"
FOCUS_PLAN_JSON="${CONTRACT_MARKET_FOCUS_PLAN_JSON:-artifacts/v9/contract_lab/contract_focus_canary_plan_latest.json}"
FOCUS_LAUNCHER_JSON="${CONTRACT_MARKET_FOCUS_LAUNCHER_JSON:-artifacts/v9/contract_lab/contract_focus_canary_launcher_latest.json}"
FOCUS_LAUNCHER_MD="${CONTRACT_MARKET_FOCUS_LAUNCHER_MD:-artifacts/v9/contract_lab/contract_focus_canary_launcher_latest.md}"
MARKER="${CONTRACT_MARKET_MARKER:-$DEFAULT_MARKER}"
NO_MARKER="${CONTRACT_MARKET_NO_MARKER:-$DEFAULT_NO_MARKER}"
ANALOG_MARKER="${CONTRACT_MARKET_ANALOG_MARKER:-$DEFAULT_ANALOG_MARKER}"
ANALOG_NO_MARKER="${CONTRACT_MARKET_ANALOG_NO_MARKER:-$DEFAULT_ANALOG_NO_MARKER}"
if [[ -n "${CONTRACT_MARKET_ANALOG_HORIZON_BARS:-}" ]]; then
  ANALOG_HORIZON_BARS="$CONTRACT_MARKET_ANALOG_HORIZON_BARS"
else
  case "$TIMEFRAME" in
    15m) ANALOG_HORIZON_BARS="96" ;;
    5m) ANALOG_HORIZON_BARS="288" ;;
    1h) ANALOG_HORIZON_BARS="24" ;;
    *) ANALOG_HORIZON_BARS="24" ;;
  esac
fi
PAPER_OUTCOME_HORIZON_BARS="${CONTRACT_MARKET_PAPER_OUTCOME_HORIZON_BARS:-$ANALOG_HORIZON_BARS}"
if [[ -n "${CONTRACT_MARKET_FAST_SHADOW_OUTCOME_HORIZON_BARS:-}" ]]; then
  FAST_SHADOW_OUTCOME_HORIZON_BARS="$CONTRACT_MARKET_FAST_SHADOW_OUTCOME_HORIZON_BARS"
else
  case "$TIMEFRAME" in
    15m) FAST_SHADOW_OUTCOME_HORIZON_BARS="16" ;;
    5m) FAST_SHADOW_OUTCOME_HORIZON_BARS="48" ;;
    1h) FAST_SHADOW_OUTCOME_HORIZON_BARS="6" ;;
    *) FAST_SHADOW_OUTCOME_HORIZON_BARS="6" ;;
  esac
fi
PAPER_FEE_BPS="${CONTRACT_MARKET_PAPER_FEE_BPS:-5.0}"
PAPER_SLIPPAGE_BPS="${CONTRACT_MARKET_PAPER_SLIPPAGE_BPS:-2.0}"
PAPER_ENTRY_LATENCY_BARS="${CONTRACT_MARKET_PAPER_ENTRY_LATENCY_BARS:-1}"
PAPER_MAX_ENTRY_DRIFT_BPS="${CONTRACT_MARKET_PAPER_MAX_ENTRY_DRIFT_BPS:-80.0}"
PAPER_FUNDING_BPS_PER_8H="${CONTRACT_MARKET_PAPER_FUNDING_BPS_PER_8H:-1.0}"
PAPER_PARTIAL_FILL_FRAC="${CONTRACT_MARKET_PAPER_PARTIAL_FILL_FRAC:-1.0}"
PAPER_MIN_FILL_FRAC="${CONTRACT_MARKET_PAPER_MIN_FILL_FRAC:-1.0}"
PAPER_MIGRATE_LEGACY_RECORDS="${CONTRACT_MARKET_PAPER_MIGRATE_LEGACY_RECORDS:-all}"
JOURNAL_MAX_ACTIVE_PER_PAIR="${CONTRACT_MARKET_JOURNAL_MAX_ACTIVE_PER_PAIR:-1}"
JOURNAL_RECORD_MODE="${CONTRACT_MARKET_JOURNAL_RECORD_MODE:-analog_supported}"
JOURNAL_SHADOW_RECORD_MODE="${CONTRACT_MARKET_JOURNAL_SHADOW_RECORD_MODE:-positive_expectancy}"
JOURNAL_SHADOW_MIN_ANALOG_SAMPLES="${CONTRACT_MARKET_JOURNAL_SHADOW_MIN_ANALOG_SAMPLES:-20}"
JOURNAL_SHADOW_MIN_EXPECTANCY_R="${CONTRACT_MARKET_JOURNAL_SHADOW_MIN_EXPECTANCY_R:-0.15}"
JOURNAL_SHADOW_MIN_HIT_RATE="${CONTRACT_MARKET_JOURNAL_SHADOW_MIN_HIT_RATE:-0.30}"
JOURNAL_SHADOW_MIN_PROFITABLE_RATE="${CONTRACT_MARKET_JOURNAL_SHADOW_MIN_PROFITABLE_RATE:-0.40}"
REGIME_FILTER_MODE="${CONTRACT_MARKET_REGIME_FILTER_MODE:-block_conflict}"
REGIME_SYMBOLS="${CONTRACT_MARKET_REGIME_SYMBOLS:-BTCUSDT,ETHUSDT}"
REGIME_MIN_DIRECTION_VOTES="${CONTRACT_MARKET_REGIME_MIN_DIRECTION_VOTES:-2}"
REGIME_VOL_LOOKBACK_BARS="${CONTRACT_MARKET_REGIME_VOL_LOOKBACK_BARS:-1000}"
REGIME_HIGH_VOL_PERCENTILE="${CONTRACT_MARKET_REGIME_HIGH_VOL_PERCENTILE:-0.85}"
REGIME_BLOCK_HIGH_VOL="${CONTRACT_MARKET_REGIME_BLOCK_HIGH_VOL:-0}"

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi
if ! [[ "$TOP_N" =~ ^[0-9]+$ && "$SLEEP_SEC" =~ ^[0-9]+$ && "$LOOKBACK_BARS_IF_EMPTY" =~ ^[0-9]+$ && "$ANALOG_HORIZON_BARS" =~ ^[0-9]+$ && "$PAPER_OUTCOME_HORIZON_BARS" =~ ^[0-9]+$ && "$FAST_SHADOW_OUTCOME_HORIZON_BARS" =~ ^[0-9]+$ && "$PAPER_ENTRY_LATENCY_BARS" =~ ^[0-9]+$ && "$JOURNAL_MAX_ACTIVE_PER_PAIR" =~ ^[0-9]+$ && "$JOURNAL_SHADOW_MIN_ANALOG_SAMPLES" =~ ^[0-9]+$ && "$REGIME_MIN_DIRECTION_VOTES" =~ ^[0-9]+$ && "$REGIME_VOL_LOOKBACK_BARS" =~ ^[0-9]+$ ]]; then
  echo "CONTRACT_MARKET_TOP_N, CONTRACT_MARKET_SIGNAL_SLEEP_SEC, CONTRACT_MARKET_LOOKBACK_BARS_IF_EMPTY, CONTRACT_MARKET_ANALOG_HORIZON_BARS, CONTRACT_MARKET_PAPER_OUTCOME_HORIZON_BARS, CONTRACT_MARKET_FAST_SHADOW_OUTCOME_HORIZON_BARS, CONTRACT_MARKET_PAPER_ENTRY_LATENCY_BARS, CONTRACT_MARKET_JOURNAL_MAX_ACTIVE_PER_PAIR, CONTRACT_MARKET_JOURNAL_SHADOW_MIN_ANALOG_SAMPLES, CONTRACT_MARKET_REGIME_MIN_DIRECTION_VOTES, and CONTRACT_MARKET_REGIME_VOL_LOOKBACK_BARS must be integers" >&2
  exit 2
fi
case "$REGIME_FILTER_MODE" in
  off|annotate|block_conflict|trend_only) ;;
  *)
    echo "CONTRACT_MARKET_REGIME_FILTER_MODE must be off, annotate, block_conflict, or trend_only" >&2
    exit 2
    ;;
esac
case "$JOURNAL_RECORD_MODE" in
  all_signals|analog_supported|off) ;;
  *)
    echo "CONTRACT_MARKET_JOURNAL_RECORD_MODE must be all_signals, analog_supported, or off" >&2
    exit 2
    ;;
esac
case "$JOURNAL_SHADOW_RECORD_MODE" in
  inherit|all_signals|analog_supported|positive_expectancy|off) ;;
  *)
    echo "CONTRACT_MARKET_JOURNAL_SHADOW_RECORD_MODE must be inherit, all_signals, analog_supported, positive_expectancy, or off" >&2
    exit 2
    ;;
esac
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"
python3 scripts/v9_xsec_binance_cache_update.py --help >/dev/null
python3 scripts/v9_contract_latest_market_signal.py --help >/dev/null
python3 scripts/v9_contract_paper_signal_report.py --help >/dev/null
python3 scripts/v9_contract_focus_canary_plan.py --help >/dev/null
python3 scripts/v9_contract_focus_canary_launcher.py --help >/dev/null
mkdir -p "$LOG_DIR" state artifacts/v9/contract_lab artifacts/v9/watchdog

if tmux has-session -t "=$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION"
  echo "log: $LOG_DIR"
  exit 0
fi

SYMBOLS="${CONTRACT_MARKET_SYMBOLS:-}"
if [[ -z "$SYMBOLS" ]]; then
  SYMBOLS="$(
    CONTRACT_MARKET_UNIVERSE_JSON="$UNIVERSE_JSON" CONTRACT_MARKET_TOP_N="$TOP_N" python3 - <<'PY'
import json
import os
from pathlib import Path

default = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
]
path = Path(os.environ["CONTRACT_MARKET_UNIVERSE_JSON"])
top_n = int(os.environ["CONTRACT_MARKET_TOP_N"])
symbols = default
if path.exists():
    try:
        payload = json.loads(path.read_text())
        found = [str(item).upper() for item in payload.get("symbols", []) if item]
        if found:
            symbols = found
    except json.JSONDecodeError:
        pass
print(",".join(symbols[:top_n]))
PY
  )"
fi

printf -v ROOT_Q "%q" "$ROOT"
printf -v LOG_Q "%q" "$LOG"
printf -v CACHE_DIR_Q "%q" "$CACHE_DIR"
printf -v API_URL_Q "%q" "$API_URL"
printf -v SYMBOLS_Q "%q" "$SYMBOLS"
printf -v TIMEFRAME_Q "%q" "$TIMEFRAME"
printf -v UPDATE_STATE_JSON_Q "%q" "$UPDATE_STATE_JSON"
printf -v UNIVERSE_JSON_Q "%q" "$UNIVERSE_JSON"
printf -v SIGNAL_JSON_Q "%q" "$SIGNAL_JSON"
printf -v SIGNAL_MD_Q "%q" "$SIGNAL_MD"
printf -v JOURNAL_JSONL_Q "%q" "$JOURNAL_JSONL"
printf -v SHADOW_JOURNAL_JSONL_Q "%q" "$SHADOW_JOURNAL_JSONL"
printf -v FAST_SHADOW_JOURNAL_JSONL_Q "%q" "$FAST_SHADOW_JOURNAL_JSONL"
printf -v BLOCKED_PAIRS_JSON_Q "%q" "$BLOCKED_PAIRS_JSON"
printf -v ACTIONS_JSON_Q "%q" "$ACTIONS_JSON"
printf -v SHADOW_PROMOTE_MARKER_Q "%q" "$SHADOW_PROMOTE_MARKER"
printf -v SHADOW_NO_PROMOTE_MARKER_Q "%q" "$SHADOW_NO_PROMOTE_MARKER"
printf -v SHADOW_READINESS_MARKER_Q "%q" "$SHADOW_READINESS_MARKER"
printf -v SHADOW_READINESS_JSON_Q "%q" "$SHADOW_READINESS_JSON"
printf -v FOCUS_PLAN_JSON_Q "%q" "$FOCUS_PLAN_JSON"
printf -v FOCUS_LAUNCHER_JSON_Q "%q" "$FOCUS_LAUNCHER_JSON"
printf -v FOCUS_LAUNCHER_MD_Q "%q" "$FOCUS_LAUNCHER_MD"
printf -v MARKER_Q "%q" "$MARKER"
printf -v NO_MARKER_Q "%q" "$NO_MARKER"
printf -v ANALOG_MARKER_Q "%q" "$ANALOG_MARKER"
printf -v ANALOG_NO_MARKER_Q "%q" "$ANALOG_NO_MARKER"
printf -v TOP_N_Q "%q" "$TOP_N"
printf -v LOOKBACK_Q "%q" "$LOOKBACK_BARS_IF_EMPTY"
printf -v SLEEP_Q "%q" "$SLEEP_SEC"
printf -v ANALOG_HORIZON_Q "%q" "$ANALOG_HORIZON_BARS"
printf -v PAPER_OUTCOME_HORIZON_Q "%q" "$PAPER_OUTCOME_HORIZON_BARS"
printf -v FAST_SHADOW_OUTCOME_HORIZON_Q "%q" "$FAST_SHADOW_OUTCOME_HORIZON_BARS"
printf -v PAPER_FEE_BPS_Q "%q" "$PAPER_FEE_BPS"
printf -v PAPER_SLIPPAGE_BPS_Q "%q" "$PAPER_SLIPPAGE_BPS"
printf -v PAPER_ENTRY_LATENCY_Q "%q" "$PAPER_ENTRY_LATENCY_BARS"
printf -v PAPER_MAX_ENTRY_DRIFT_Q "%q" "$PAPER_MAX_ENTRY_DRIFT_BPS"
printf -v PAPER_FUNDING_BPS_Q "%q" "$PAPER_FUNDING_BPS_PER_8H"
printf -v PAPER_PARTIAL_FILL_Q "%q" "$PAPER_PARTIAL_FILL_FRAC"
printf -v PAPER_MIN_FILL_Q "%q" "$PAPER_MIN_FILL_FRAC"
printf -v PAPER_MIGRATE_LEGACY_Q "%q" "$PAPER_MIGRATE_LEGACY_RECORDS"
printf -v JOURNAL_MAX_ACTIVE_Q "%q" "$JOURNAL_MAX_ACTIVE_PER_PAIR"
printf -v JOURNAL_RECORD_MODE_Q "%q" "$JOURNAL_RECORD_MODE"
printf -v JOURNAL_SHADOW_RECORD_MODE_Q "%q" "$JOURNAL_SHADOW_RECORD_MODE"
printf -v JOURNAL_SHADOW_MIN_ANALOG_Q "%q" "$JOURNAL_SHADOW_MIN_ANALOG_SAMPLES"
printf -v JOURNAL_SHADOW_MIN_EXPECTANCY_Q "%q" "$JOURNAL_SHADOW_MIN_EXPECTANCY_R"
printf -v JOURNAL_SHADOW_MIN_HIT_Q "%q" "$JOURNAL_SHADOW_MIN_HIT_RATE"
printf -v JOURNAL_SHADOW_MIN_PROFITABLE_Q "%q" "$JOURNAL_SHADOW_MIN_PROFITABLE_RATE"
printf -v REGIME_FILTER_MODE_Q "%q" "$REGIME_FILTER_MODE"
printf -v REGIME_SYMBOLS_Q "%q" "$REGIME_SYMBOLS"
printf -v REGIME_MIN_DIRECTION_Q "%q" "$REGIME_MIN_DIRECTION_VOTES"
printf -v REGIME_VOL_LOOKBACK_Q "%q" "$REGIME_VOL_LOOKBACK_BARS"
printf -v REGIME_HIGH_VOL_Q "%q" "$REGIME_HIGH_VOL_PERCENTILE"
REGIME_BLOCK_HIGH_VOL_ARG=""
if [[ "$REGIME_BLOCK_HIGH_VOL" == "1" || "$REGIME_BLOCK_HIGH_VOL" == "true" || "$REGIME_BLOCK_HIGH_VOL" == "TRUE" || "$REGIME_BLOCK_HIGH_VOL" == "yes" || "$REGIME_BLOCK_HIGH_VOL" == "YES" ]]; then
  REGIME_BLOCK_HIGH_VOL_ARG="--regime-block-high-vol"
fi

tmux new-session -d -s "$SESSION" \
  "cd $ROOT_Q && while true; do date -u; python3 scripts/v9_xsec_binance_cache_update.py --cache-dir $CACHE_DIR_Q --api-url $API_URL_Q --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --lookback-bars-if-empty $LOOKBACK_Q --state-json $UPDATE_STATE_JSON_Q --format text; python3 scripts/v9_contract_latest_market_signal.py --cache-dir $CACHE_DIR_Q --universe-json $UNIVERSE_JSON_Q --top-n $TOP_N_Q --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --out-json $SIGNAL_JSON_Q --out-md $SIGNAL_MD_Q --journal-jsonl $JOURNAL_JSONL_Q --journal-shadow-jsonl $SHADOW_JOURNAL_JSONL_Q --journal-fast-shadow-jsonl $FAST_SHADOW_JOURNAL_JSONL_Q --journal-fast-shadow-outcome-horizon-bars $FAST_SHADOW_OUTCOME_HORIZON_Q --journal-shadow-record-mode $JOURNAL_SHADOW_RECORD_MODE_Q --journal-shadow-min-analog-samples $JOURNAL_SHADOW_MIN_ANALOG_Q --journal-shadow-min-expectancy-r $JOURNAL_SHADOW_MIN_EXPECTANCY_Q --journal-shadow-min-hit-rate $JOURNAL_SHADOW_MIN_HIT_Q --journal-shadow-min-profitable-rate $JOURNAL_SHADOW_MIN_PROFITABLE_Q --journal-blocked-pairs-json $BLOCKED_PAIRS_JSON_Q --journal-max-active-per-pair $JOURNAL_MAX_ACTIVE_Q --journal-record-mode $JOURNAL_RECORD_MODE_Q --marker $MARKER_Q --no-marker $NO_MARKER_Q --analog-marker $ANALOG_MARKER_Q --analog-no-marker $ANALOG_NO_MARKER_Q --analog-horizon-bars $ANALOG_HORIZON_Q --paper-outcome-horizon-bars $PAPER_OUTCOME_HORIZON_Q --paper-fee-bps $PAPER_FEE_BPS_Q --paper-slippage-bps $PAPER_SLIPPAGE_BPS_Q --paper-entry-latency-bars $PAPER_ENTRY_LATENCY_Q --paper-max-entry-drift-bps $PAPER_MAX_ENTRY_DRIFT_Q --paper-funding-bps-per-8h $PAPER_FUNDING_BPS_Q --paper-partial-fill-frac $PAPER_PARTIAL_FILL_Q --paper-min-fill-frac $PAPER_MIN_FILL_Q --paper-migrate-legacy-records $PAPER_MIGRATE_LEGACY_Q --regime-filter-mode $REGIME_FILTER_MODE_Q --regime-symbols $REGIME_SYMBOLS_Q --regime-min-direction-votes $REGIME_MIN_DIRECTION_Q --regime-vol-lookback-bars $REGIME_VOL_LOOKBACK_Q --regime-high-vol-percentile $REGIME_HIGH_VOL_Q $REGIME_BLOCK_HIGH_VOL_ARG --format text; python3 scripts/v9_contract_paper_signal_report.py --cache-dir $CACHE_DIR_Q --out-actions-json $ACTIONS_JSON_Q --out-blocked-pairs-json $BLOCKED_PAIRS_JSON_Q --out-current-policy-shadow-promote-marker $SHADOW_PROMOTE_MARKER_Q --out-current-policy-shadow-no-promote-marker $SHADOW_NO_PROMOTE_MARKER_Q --out-current-policy-shadow-readiness-marker $SHADOW_READINESS_MARKER_Q --out-current-policy-shadow-readiness-json $SHADOW_READINESS_JSON_Q --format text; python3 scripts/v9_contract_focus_canary_plan.py --actions-json $ACTIONS_JSON_Q --out-json $FOCUS_PLAN_JSON_Q --format text; python3 scripts/v9_contract_focus_canary_launcher.py --plan-json $FOCUS_PLAN_JSON_Q --out-json $FOCUS_LAUNCHER_JSON_Q --out-md $FOCUS_LAUNCHER_MD_Q --launch --format text; sleep $SLEEP_Q; done >> $LOG_Q 2>&1"

echo "started contract latest-market signal watch: $SESSION"
echo "symbols: $SYMBOLS"
echo "timeframe: $TIMEFRAME"
echo "sleep_sec: $SLEEP_SEC"
echo "analog_horizon_bars: $ANALOG_HORIZON_BARS"
echo "fast_shadow_outcome_horizon_bars: $FAST_SHADOW_OUTCOME_HORIZON_BARS"
echo "paper_execution: fee_bps=$PAPER_FEE_BPS slippage_bps=$PAPER_SLIPPAGE_BPS latency_bars=$PAPER_ENTRY_LATENCY_BARS funding_bps_per_8h=$PAPER_FUNDING_BPS_PER_8H migrate_legacy=$PAPER_MIGRATE_LEGACY_RECORDS"
echo "regime_filter: mode=$REGIME_FILTER_MODE symbols=$REGIME_SYMBOLS min_direction_votes=$REGIME_MIN_DIRECTION_VOTES high_vol_percentile=$REGIME_HIGH_VOL_PERCENTILE block_high_vol=$REGIME_BLOCK_HIGH_VOL"
echo "journal_max_active_per_pair: $JOURNAL_MAX_ACTIVE_PER_PAIR"
echo "journal_record_mode: $JOURNAL_RECORD_MODE"
echo "journal_shadow_record_mode: $JOURNAL_SHADOW_RECORD_MODE"
echo "journal_shadow_thresholds: samples=$JOURNAL_SHADOW_MIN_ANALOG_SAMPLES expectancy=$JOURNAL_SHADOW_MIN_EXPECTANCY_R hit=$JOURNAL_SHADOW_MIN_HIT_RATE profitable=$JOURNAL_SHADOW_MIN_PROFITABLE_RATE"
echo "blocked_pairs_json: $BLOCKED_PAIRS_JSON"
echo "actions_json: $ACTIONS_JSON"
echo "shadow_promote_marker: $SHADOW_PROMOTE_MARKER"
echo "shadow_no_promote_marker: $SHADOW_NO_PROMOTE_MARKER"
echo "shadow_readiness_marker: $SHADOW_READINESS_MARKER"
echo "shadow_readiness_json: $SHADOW_READINESS_JSON"
echo "focus_plan_json: $FOCUS_PLAN_JSON"
echo "focus_launcher_json: $FOCUS_LAUNCHER_JSON"
echo "journal: $JOURNAL_JSONL"
echo "shadow_journal: $SHADOW_JOURNAL_JSONL"
echo "fast_shadow_journal: $FAST_SHADOW_JOURNAL_JSONL"
echo "log: $LOG"
