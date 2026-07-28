# Holdout Ledger

This ledger records every evaluation that touches post-training data. It is the multiple-testing accountant for the strategy factory.

Rules:

- Every holdout or forward-shadow evaluation must be logged before or immediately after it runs.
- Each frozen batch gets one holdout evaluation.
- Failed batches are discarded unmodified.
- A burned holdout window must not be reused for tuning features, thresholds, seeds, candidate selection, or retry decisions.
- If a future protocol deliberately reuses a burned window for a different design, it must state that reuse before running and tighten its pass criteria.

| Date UTC | Batch | Frozen artifact | Frozen SHA256 | Runner/Config | Train window | Holdout window | Effective scored window | Outcome | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-06 | `v8_link_batch1_20260706` | `results/frozen/v8_link_candidates_batch1_20260706.json` | `6fac0d6a44adba63e67278ca12dddbb53eee12850717e4826ac88e056e016c80` | `scripts/holdout_eval_v8_frozen.py`; protocol `docs/holdout_protocol_v8_batch1.md` | 2017-08..2024-06 | 2024-07..2026-05 | 2024-08..2026-05 | Fail: 0/3 passed | LINKUSDT 1h, 24 scenarios x 20/30/50 bps. Holdout is burned. Do not evaluate remaining LINK siblings on this window. |
