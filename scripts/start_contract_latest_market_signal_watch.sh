#!/usr/bin/env bash
set -euo pipefail

SESSION="${1:-v9_contract_latest_market_signal_watch}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/v9_contract_market_signal"
LOG="$LOG_DIR/watch_$(date -u +%Y%m%dT%H%M%SZ).log"

TIMEFRAME="${CONTRACT_MARKET_TIMEFRAME:-1h}"
TOP_N="${CONTRACT_MARKET_TOP_N:-20}"
SLEEP_SEC="${CONTRACT_MARKET_SIGNAL_SLEEP_SEC:-900}"
LOOKBACK_BARS_IF_EMPTY="${CONTRACT_MARKET_LOOKBACK_BARS_IF_EMPTY:-20000}"
CACHE_DIR="${CONTRACT_MARKET_CACHE_DIR:-data/binance_usdm_ohlcv_cache}"
UNIVERSE_JSON="${CONTRACT_MARKET_UNIVERSE_JSON:-artifacts/v9/universe/binance_usdm_top20_volume_snapshot.json}"
API_URL="${CONTRACT_MARKET_KLINES_API:-https://fapi.binance.com/fapi/v1/klines}"
UPDATE_STATE_JSON="${CONTRACT_MARKET_UPDATE_STATE_JSON:-artifacts/v9/watchdog/binance_usdm_ohlcv_top20_update_status.json}"
SIGNAL_JSON="${CONTRACT_MARKET_SIGNAL_JSON:-artifacts/v9/contract_lab/contract_latest_market_signal_latest.json}"
SIGNAL_MD="${CONTRACT_MARKET_SIGNAL_MD:-artifacts/v9/contract_lab/contract_latest_market_signal_latest.md}"

if [[ "$SESSION" == -* ]]; then
  echo "session name must not start with '-'" >&2
  exit 2
fi
if ! [[ "$TOP_N" =~ ^[0-9]+$ && "$SLEEP_SEC" =~ ^[0-9]+$ && "$LOOKBACK_BARS_IF_EMPTY" =~ ^[0-9]+$ ]]; then
  echo "CONTRACT_MARKET_TOP_N, CONTRACT_MARKET_SIGNAL_SLEEP_SEC, and CONTRACT_MARKET_LOOKBACK_BARS_IF_EMPTY must be integers" >&2
  exit 2
fi
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi

cd "$ROOT"
python3 scripts/v9_xsec_binance_cache_update.py --help >/dev/null
python3 scripts/v9_contract_latest_market_signal.py --help >/dev/null
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
printf -v TOP_N_Q "%q" "$TOP_N"
printf -v LOOKBACK_Q "%q" "$LOOKBACK_BARS_IF_EMPTY"
printf -v SLEEP_Q "%q" "$SLEEP_SEC"

tmux new-session -d -s "$SESSION" \
  "cd $ROOT_Q && while true; do date -u; python3 scripts/v9_xsec_binance_cache_update.py --cache-dir $CACHE_DIR_Q --api-url $API_URL_Q --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --lookback-bars-if-empty $LOOKBACK_Q --state-json $UPDATE_STATE_JSON_Q --format text; python3 scripts/v9_contract_latest_market_signal.py --cache-dir $CACHE_DIR_Q --universe-json $UNIVERSE_JSON_Q --top-n $TOP_N_Q --symbols $SYMBOLS_Q --timeframe $TIMEFRAME_Q --out-json $SIGNAL_JSON_Q --out-md $SIGNAL_MD_Q --format text; sleep $SLEEP_Q; done >> $LOG_Q 2>&1"

echo "started contract latest-market signal watch: $SESSION"
echo "symbols: $SYMBOLS"
echo "timeframe: $TIMEFRAME"
echo "sleep_sec: $SLEEP_SEC"
echo "log: $LOG"
