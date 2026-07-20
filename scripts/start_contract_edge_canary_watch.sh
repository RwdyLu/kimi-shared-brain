#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_contract_edge_canary_1h_watch}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/v9_contract_edge_canary"
LOG="$LOG_DIR/watch_$(date -u +%Y%m%dT%H%M%SZ).log"

TIMEFRAME="${CONTRACT_EDGE_CANARY_TIMEFRAME:-1h}"
SYMBOLS="${CONTRACT_EDGE_CANARY_SYMBOLS:-SYNUSDT,AAVEUSDT,WLDUSDT}"
ALLOWED_PAIRS="${CONTRACT_EDGE_CANARY_ALLOWED_PAIRS:-SYNUSDT:short,AAVEUSDT:short,WLDUSDT:short}"
SLEEP_SEC="${CONTRACT_EDGE_CANARY_SLEEP_SEC:-900}"
LOOKBACK_BARS_IF_EMPTY="${CONTRACT_EDGE_CANARY_LOOKBACK_BARS_IF_EMPTY:-20000}"
CACHE_DIR="${CONTRACT_EDGE_CANARY_CACHE_DIR:-data/binance_usdm_ohlcv_cache}"
API_URL="${CONTRACT_EDGE_CANARY_KLINES_API:-https://fapi.binance.com/fapi/v1/klines}"
UNIVERSE_JSON="${CONTRACT_EDGE_CANARY_UNIVERSE_JSON:-artifacts/v9/universe/binance_usdm_top20_volume_snapshot.json}"

TIMEFRAME_SAFE="$(printf '%s' "$TIMEFRAME" | tr -c '[:alnum:]' '_')"
UPDATE_STATE_JSON="${CONTRACT_EDGE_CANARY_UPDATE_STATE_JSON:-artifacts/v9/watchdog/contract_edge_canary_${TIMEFRAME_SAFE}_update_status.json}"
SIGNAL_JSON="${CONTRACT_EDGE_CANARY_SIGNAL_JSON:-artifacts/v9/contract_lab/contract_edge_canary_${TIMEFRAME_SAFE}_latest.json}"
SIGNAL_MD="${CONTRACT_EDGE_CANARY_SIGNAL_MD:-artifacts/v9/contract_lab/contract_edge_canary_${TIMEFRAME_SAFE}_latest.md}"
JOURNAL_JSONL="${CONTRACT_EDGE_CANARY_JOURNAL_JSONL:-state/contract_edge_canary_${TIMEFRAME_SAFE}_journal.jsonl}"
REPORT_JSON="${CONTRACT_EDGE_CANARY_REPORT_JSON:-artifacts/v9/contract_lab/contract_edge_canary_report_latest.json}"
REPORT_MD="${CONTRACT_EDGE_CANARY_REPORT_MD:-artifacts/v9/contract_lab/contract_edge_canary_report_latest.md}"
GUARD_JSON="${CONTRACT_EDGE_CANARY_GUARD_JSON:-state/contract_edge_canary_guard_state.json}"
GUARD_MD="${CONTRACT_EDGE_CANARY_GUARD_MD:-artifacts/v9/contract_lab/contract_edge_canary_guard_latest.md}"
MARKER="${CONTRACT_EDGE_CANARY_MARKER:-state/FOUND_CONTRACT_EDGE_CANARY_PAPER_PLAN.txt}"
NO_MARKER="${CONTRACT_EDGE_CANARY_NO_MARKER:-state/NO_CONTRACT_EDGE_CANARY_PAPER_PLAN.txt}"
ANALOG_MARKER="${CONTRACT_EDGE_CANARY_ANALOG_MARKER:-state/FOUND_CONTRACT_EDGE_CANARY_ANALOG_PAPER_PLAN.txt}"
ANALOG_NO_MARKER="${CONTRACT_EDGE_CANARY_ANALOG_NO_MARKER:-state/NO_CONTRACT_EDGE_CANARY_ANALOG_PAPER_PLAN.txt}"

if [[ -n "${CONTRACT_EDGE_CANARY_ANALOG_HORIZON_BARS:-}" ]]; then
  ANALOG_HORIZON_BARS="$CONTRACT_EDGE_CANARY_ANALOG_HORIZON_BARS"
else
  case "$TIMEFRAME" in
    15m) ANALOG_HORIZON_BARS="96" ;;
    1h) ANALOG_HORIZON_BARS="24" ;;
    *) ANALOG_HORIZON_BARS="24" ;;
  esac
fi
PAPER_OUTCOME_HORIZON_BARS="${CONTRACT_EDGE_CANARY_PAPER_OUTCOME_HORIZON_BARS:-$ANALOG_HORIZON_BARS}"
PAPER_FEE_BPS="${CONTRACT_EDGE_CANARY_PAPER_FEE_BPS:-5.0}"
PAPER_SLIPPAGE_BPS="${CONTRACT_EDGE_CANARY_PAPER_SLIPPAGE_BPS:-2.0}"
PAPER_ENTRY_LATENCY_BARS="${CONTRACT_EDGE_CANARY_PAPER_ENTRY_LATENCY_BARS:-1}"
PAPER_MAX_ENTRY_DRIFT_BPS="${CONTRACT_EDGE_CANARY_PAPER_MAX_ENTRY_DRIFT_BPS:-80.0}"
PAPER_FUNDING_BPS_PER_8H="${CONTRACT_EDGE_CANARY_PAPER_FUNDING_BPS_PER_8H:-1.0}"
JOURNAL_MAX_ACTIVE_PER_PAIR="${CONTRACT_EDGE_CANARY_JOURNAL_MAX_ACTIVE_PER_PAIR:-1}"
JOURNAL_RECORD_MODE="${CONTRACT_EDGE_CANARY_JOURNAL_RECORD_MODE:-analog_supported}"

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi
if ! [[ "$SLEEP_SEC" =~ ^[0-9]+$ && "$LOOKBACK_BARS_IF_EMPTY" =~ ^[0-9]+$ && "$ANALOG_HORIZON_BARS" =~ ^[0-9]+$ && "$PAPER_OUTCOME_HORIZON_BARS" =~ ^[0-9]+$ && "$PAPER_ENTRY_LATENCY_BARS" =~ ^[0-9]+$ && "$JOURNAL_MAX_ACTIVE_PER_PAIR" =~ ^[0-9]+$ ]]; then
  echo "sleep, lookback, horizon, and latency values must be integers" >&2
  exit 2
fi
case "$JOURNAL_RECORD_MODE" in
  all_signals|analog_supported|off) ;;
  *)
    echo "CONTRACT_EDGE_CANARY_JOURNAL_RECORD_MODE must be all_signals, analog_supported, or off" >&2
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
python3 scripts/v9_contract_canary_guard.py --help >/dev/null
mkdir -p "$LOG_DIR" state artifacts/v9/contract_lab artifacts/v9/watchdog

if tmux has-session -t "=$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION"
  echo "log: $LOG_DIR"
  exit 0
fi

printf -v ROOT_Q "%q" "$ROOT"
printf -v LOG_Q "%q" "$LOG"
printf -v CACHE_DIR_Q "%q" "$CACHE_DIR"
printf -v API_URL_Q "%q" "$API_URL"
printf -v SYMBOLS_Q "%q" "$SYMBOLS"
printf -v ALLOWED_PAIRS_Q "%q" "$ALLOWED_PAIRS"
printf -v TIMEFRAME_Q "%q" "$TIMEFRAME"
printf -v UPDATE_STATE_JSON_Q "%q" "$UPDATE_STATE_JSON"
printf -v UNIVERSE_JSON_Q "%q" "$UNIVERSE_JSON"
printf -v SIGNAL_JSON_Q "%q" "$SIGNAL_JSON"
printf -v SIGNAL_MD_Q "%q" "$SIGNAL_MD"
printf -v JOURNAL_JSONL_Q "%q" "$JOURNAL_JSONL"
printf -v REPORT_JSON_Q "%q" "$REPORT_JSON"
printf -v REPORT_MD_Q "%q" "$REPORT_MD"
printf -v GUARD_JSON_Q "%q" "$GUARD_JSON"
printf -v GUARD_MD_Q "%q" "$GUARD_MD"
printf -v MARKER_Q "%q" "$MARKER"
printf -v NO_MARKER_Q "%q" "$NO_MARKER"
printf -v ANALOG_MARKER_Q "%q" "$ANALOG_MARKER"
printf -v ANALOG_NO_MARKER_Q "%q" "$ANALOG_NO_MARKER"
printf -v SLEEP_Q "%q" "$SLEEP_SEC"
printf -v LOOKBACK_Q "%q" "$LOOKBACK_BARS_IF_EMPTY"
printf -v ANALOG_HORIZON_Q "%q" "$ANALOG_HORIZON_BARS"
printf -v PAPER_OUTCOME_HORIZON_Q "%q" "$PAPER_OUTCOME_HORIZON_BARS"
printf -v PAPER_FEE_BPS_Q "%q" "$PAPER_FEE_BPS"
printf -v PAPER_SLIPPAGE_BPS_Q "%q" "$PAPER_SLIPPAGE_BPS"
printf -v PAPER_ENTRY_LATENCY_Q "%q" "$PAPER_ENTRY_LATENCY_BARS"
printf -v PAPER_MAX_ENTRY_DRIFT_Q "%q" "$PAPER_MAX_ENTRY_DRIFT_BPS"
printf -v PAPER_FUNDING_BPS_Q "%q" "$PAPER_FUNDING_BPS_PER_8H"
printf -v JOURNAL_MAX_ACTIVE_Q "%q" "$JOURNAL_MAX_ACTIVE_PER_PAIR"
printf -v JOURNAL_RECORD_MODE_Q "%q" "$JOURNAL_RECORD_MODE"
REPORT_SOURCES="${TIMEFRAME}:${JOURNAL_JSONL}"
printf -v REPORT_SOURCES_Q "%q" "$REPORT_SOURCES"

tmux new-session -d -s "$SESSION" \
  "cd $ROOT_Q && while true; do date -u; python3 scripts/v9_xsec_binance_cache_update.py --cache-dir $CACHE_DIR_Q --api-url $API_URL_Q --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --lookback-bars-if-empty $LOOKBACK_Q --state-json $UPDATE_STATE_JSON_Q --format text; python3 scripts/v9_contract_latest_market_signal.py --cache-dir $CACHE_DIR_Q --universe-json $UNIVERSE_JSON_Q --top-n 3 --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --out-json $SIGNAL_JSON_Q --out-md $SIGNAL_MD_Q --journal-jsonl $JOURNAL_JSONL_Q --journal-allowed-pairs $ALLOWED_PAIRS_Q --journal-max-active-per-pair $JOURNAL_MAX_ACTIVE_Q --journal-record-mode $JOURNAL_RECORD_MODE_Q --marker $MARKER_Q --no-marker $NO_MARKER_Q --analog-marker $ANALOG_MARKER_Q --analog-no-marker $ANALOG_NO_MARKER_Q --analog-horizon-bars $ANALOG_HORIZON_Q --paper-outcome-horizon-bars $PAPER_OUTCOME_HORIZON_Q --paper-fee-bps $PAPER_FEE_BPS_Q --paper-slippage-bps $PAPER_SLIPPAGE_BPS_Q --paper-entry-latency-bars $PAPER_ENTRY_LATENCY_Q --paper-max-entry-drift-bps $PAPER_MAX_ENTRY_DRIFT_Q --paper-funding-bps-per-8h $PAPER_FUNDING_BPS_Q --paper-migrate-legacy-records off --format text; python3 scripts/v9_contract_paper_signal_report.py --cache-dir $CACHE_DIR_Q --sources $REPORT_SOURCES_Q --out-json $REPORT_JSON_Q --out-md $REPORT_MD_Q --format text; python3 scripts/v9_contract_canary_guard.py --report-json $REPORT_JSON_Q --out-json $GUARD_JSON_Q --out-md $GUARD_MD_Q --max-active-per-pair $JOURNAL_MAX_ACTIVE_Q --format text; sleep $SLEEP_Q; done >> $LOG_Q 2>&1"

echo "started contract edge canary watch: $SESSION"
echo "symbols: $SYMBOLS"
echo "allowed_pairs: $ALLOWED_PAIRS"
echo "timeframe: $TIMEFRAME"
echo "sleep_sec: $SLEEP_SEC"
echo "journal_max_active_per_pair: $JOURNAL_MAX_ACTIVE_PER_PAIR"
echo "journal_record_mode: $JOURNAL_RECORD_MODE"
echo "journal: $JOURNAL_JSONL"
echo "report: $REPORT_MD"
echo "guard: $GUARD_MD"
echo "log: $LOG"
