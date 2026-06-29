# Freqtrade Dry-Run Bridge

Artifact: `ETHUSDT_6acca71f138511a6_smoke_internal_candidate`

Approval status: `internal_candidate_only`

NOT PAPER APPROVED. NOT LIVE READY. FOR INTEGRATION SMOKE TEST ONLY.

This directory is a dry-run scaffold only. It does not contain Binance API keys,
does not enable live trading, and starts Freqtrade in `initial_state=stopped`.

By default this exporter refuses non-paper-ready artifacts. If this directory was
generated with `--allow-unvalidated-smoke-test`, do not use it for paper approval
or live trading. The current bridge reads external signals from
`user_data/signals/external_signals.csv` or from `$KIMI_SIGNAL_CSV`.

Signal CSV schema:

```csv
date,pair,enter_long,exit_long
2026-01-01T00:00:00Z,ETH/USDT,0,0
```

Suggested dry-run command after installing Freqtrade separately:

```bash
freqtrade trade --config integrations/freqtrade/config_dry_run_template.json --strategy ExternalArtifactSignalStrategy --userdir integrations/freqtrade/user_data
```

Keep this in spot mode, no leverage, fixed stake, and dry-run until the full
approval chain has passed.
