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
  DEFAULT_MARKER="state/FOUND_CONTRACT_MARKET_PAPER_PLAN.txt"
  DEFAULT_NO_MARKER="state/NO_CONTRACT_MARKET_PAPER_PLAN.txt"
  DEFAULT_ANALOG_MARKER="state/FOUND_CONTRACT_MARKET_ANALOG_PAPER_PLAN.txt"
  DEFAULT_ANALOG_NO_MARKER="state/NO_CONTRACT_MARKET_ANALOG_PAPER_PLAN.txt"
else
  DEFAULT_UPDATE_STATE_JSON="artifacts/v9/watchdog/binance_usdm_ohlcv_top20_${TIMEFRAME_SAFE}_update_status.json"
  DEFAULT_SIGNAL_JSON="artifacts/v9/contract_lab/contract_latest_market_signal_${TIMEFRAME_SAFE}_latest.json"
  DEFAULT_SIGNAL_MD="artifacts/v9/contract_lab/contract_latest_market_signal_${TIMEFRAME_SAFE}_latest.md"
  DEFAULT_JOURNAL_JSONL="state/contract_latest_market_signal_${TIMEFRAME_SAFE}_journal.jsonl"
  DEFAULT_MARKER="state/FOUND_CONTRACT_MARKET_${TIMEFRAME_SAFE}_PAPER_PLAN.txt"
  DEFAULT_NO_MARKER="state/NO_CONTRACT_MARKET_${TIMEFRAME_SAFE}_PAPER_PLAN.txt"
  DEFAULT_ANALOG_MARKER="state/FOUND_CONTRACT_MARKET_${TIMEFRAME_SAFE}_ANALOG_PAPER_PLAN.txt"
  DEFAULT_ANALOG_NO_MARKER="state/NO_CONTRACT_MARKET_${TIMEFRAME_SAFE}_ANALOG_PAPER_PLAN.txt"
fi
UPDATE_STATE_JSON="${CONTRACT_MARKET_UPDATE_STATE_JSON:-$DEFAULT_UPDATE_STATE_JSON}"
SIGNAL_JSON="${CONTRACT_MARKET_SIGNAL_JSON:-$DEFAULT_SIGNAL_JSON}"
SIGNAL_MD="${CONTRACT_MARKET_SIGNAL_MD:-$DEFAULT_SIGNAL_MD}"
JOURNAL_JSONL="${CONTRACT_MARKET_JOURNAL_JSONL:-$DEFAULT_JOURNAL_JSONL}"
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

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi
if ! [[ "$TOP_N" =~ ^[0-9]+$ && "$SLEEP_SEC" =~ ^[0-9]+$ && "$LOOKBACK_BARS_IF_EMPTY" =~ ^[0-9]+$ && "$ANALOG_HORIZON_BARS" =~ ^[0-9]+$ && "$PAPER_OUTCOME_HORIZON_BARS" =~ ^[0-9]+$ ]]; then
  echo "CONTRACT_MARKET_TOP_N, CONTRACT_MARKET_SIGNAL_SLEEP_SEC, CONTRACT_MARKET_LOOKBACK_BARS_IF_EMPTY, CONTRACT_MARKET_ANALOG_HORIZON_BARS, and CONTRACT_MARKET_PAPER_OUTCOME_HORIZON_BARS must be integers" >&2
  exit 2
fi
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"
python3 scripts/v9_xsec_binance_cache_update.py --help >/dev/null
python3 scripts/v9_contract_latest_market_signal.py --help >/dev/null
python3 scripts/v9_contract_paper_signal_report.py --help >/dev/null
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
printf -v MARKER_Q "%q" "$MARKER"
printf -v NO_MARKER_Q "%q" "$NO_MARKER"
printf -v ANALOG_MARKER_Q "%q" "$ANALOG_MARKER"
printf -v ANALOG_NO_MARKER_Q "%q" "$ANALOG_NO_MARKER"
printf -v TOP_N_Q "%q" "$TOP_N"
printf -v LOOKBACK_Q "%q" "$LOOKBACK_BARS_IF_EMPTY"
printf -v SLEEP_Q "%q" "$SLEEP_SEC"
printf -v ANALOG_HORIZON_Q "%q" "$ANALOG_HORIZON_BARS"
printf -v PAPER_OUTCOME_HORIZON_Q "%q" "$PAPER_OUTCOME_HORIZON_BARS"

tmux new-session -d -s "$SESSION" \
  "cd $ROOT_Q && while true; do date -u; python3 scripts/v9_xsec_binance_cache_update.py --cache-dir $CACHE_DIR_Q --api-url $API_URL_Q --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --lookback-bars-if-empty $LOOKBACK_Q --state-json $UPDATE_STATE_JSON_Q --format text; python3 scripts/v9_contract_latest_market_signal.py --cache-dir $CACHE_DIR_Q --universe-json $UNIVERSE_JSON_Q --top-n $TOP_N_Q --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --out-json $SIGNAL_JSON_Q --out-md $SIGNAL_MD_Q --journal-jsonl $JOURNAL_JSONL_Q --marker $MARKER_Q --no-marker $NO_MARKER_Q --analog-marker $ANALOG_MARKER_Q --analog-no-marker $ANALOG_NO_MARKER_Q --analog-horizon-bars $ANALOG_HORIZON_Q --paper-outcome-horizon-bars $PAPER_OUTCOME_HORIZON_Q --format text; python3 scripts/v9_contract_paper_signal_report.py --cache-dir $CACHE_DIR_Q --format text; sleep $SLEEP_Q; done >> $LOG_Q 2>&1"

echo "started contract latest-market signal watch: $SESSION"
echo "symbols: $SYMBOLS"
echo "timeframe: $TIMEFRAME"
echo "sleep_sec: $SLEEP_SEC"
echo "analog_horizon_bars: $ANALOG_HORIZON_BARS"
echo "journal: $JOURNAL_JSONL"
echo "log: $LOG"
