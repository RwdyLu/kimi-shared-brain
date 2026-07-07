from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContractCandidate:
    """Minimal long-only contract strategy candidate.

    Signals are generated on bar close and executed on the next bar open.
    The simulator enforces one position at a time and never allows DCA.
    """

    symbol: str
    allowed_regimes: tuple[str, ...] = ("up_normal", "up_high_vol")
    breakout_n: int = 24
    atr_n: int = 14
    stop_atr_k: float = 2.0
    tp_r_multiple: float = 2.0
    max_hold_bars: int = 48
    risk_per_trade: float = 0.005
    leverage_cap: float = 2.0
    cooldown_bars: int = 6
    side: str = "long"
    vol_scaling: str = "none"
    vol_lookback_n: int = 50
    vol_target_ann: float = 0.50
    scale_min: float = 0.25
    scale_max: float = 2.0
    trend_ema_len: int = 100
    rsi_len: int = 2
    rsi_entry_max: float = 20.0
    rsi_exit_min: float = 65.0
    entry_confirm: str = "close_above_ema"
    regime_len: int = 150
    slope_len: int = 20
    rsi_hi: float = 70.0
    stop_pct: float = 0.03
    target_pct: float = 0.02
    max_regime_drawdown_1y: float | None = None
    be_trigger_r: float | None = None
    be_lock_r: float = 0.0
    trail_atr_mult: float | None = None
    trail_trigger_r: float = 1.0
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    funding_bps_per_8h: float = 1.0
    short_extra_cost_bps: float = 5.0
    initial_equity: float = 10_000.0
    family: str = "donchian_breakout_long_v9"
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "allowed_regimes", tuple(sorted(set(self.allowed_regimes))))
        if self.family not in {"donchian_breakout_long_v9", "pullback_long_v1", "bear_rally_fade_short_v1"}:
            raise ValueError(f"unknown family: {self.family}")
        if self.side not in {"long", "short"}:
            raise ValueError("side must be long or short")
        if self.vol_scaling not in {"none", "inverse_atr", "vol_target"}:
            raise ValueError("vol_scaling must be none, inverse_atr, or vol_target")
        if self.vol_lookback_n < 1:
            raise ValueError("vol_lookback_n must be >= 1")
        if self.vol_target_ann <= 0:
            raise ValueError("vol_target_ann must be > 0")
        if not 0 < self.scale_min <= self.scale_max:
            raise ValueError("scale_min and scale_max must satisfy 0 < min <= max")
        if self.family == "bear_rally_fade_short_v1" and self.side != "short":
            raise ValueError("bear_rally_fade_short_v1 requires side=short")
        if self.family != "bear_rally_fade_short_v1" and self.side != "long":
            raise ValueError("long families require side=long")
        if self.breakout_n < 1:
            raise ValueError("breakout_n must be >= 1")
        if self.atr_n < 1:
            raise ValueError("atr_n must be >= 1")
        if self.stop_atr_k <= 0:
            raise ValueError("stop_atr_k must be > 0")
        if self.tp_r_multiple <= 0:
            raise ValueError("tp_r_multiple must be > 0")
        if self.max_hold_bars < 1:
            raise ValueError("max_hold_bars must be >= 1")
        if not 0 < self.risk_per_trade <= 0.05:
            raise ValueError("risk_per_trade must be in (0, 0.05]")
        if self.leverage_cap <= 0:
            raise ValueError("leverage_cap must be > 0")
        if self.cooldown_bars < 0:
            raise ValueError("cooldown_bars must be >= 0")
        if self.trend_ema_len < 1:
            raise ValueError("trend_ema_len must be >= 1")
        if self.rsi_len < 1:
            raise ValueError("rsi_len must be >= 1")
        if not 0 < self.rsi_entry_max < 100:
            raise ValueError("rsi_entry_max must be in (0, 100)")
        if not 0 < self.rsi_exit_min < 100:
            raise ValueError("rsi_exit_min must be in (0, 100)")
        if self.family == "pullback_long_v1" and self.rsi_entry_max >= self.rsi_exit_min:
            raise ValueError("pullback_long_v1 requires rsi_entry_max < rsi_exit_min")
        if self.entry_confirm != "close_above_ema":
            raise ValueError("entry_confirm must be close_above_ema")
        if self.regime_len < 1:
            raise ValueError("regime_len must be >= 1")
        if self.slope_len < 1:
            raise ValueError("slope_len must be >= 1")
        if not 0 < self.rsi_hi < 100:
            raise ValueError("rsi_hi must be in (0, 100)")
        if not 0 < self.stop_pct < 1:
            raise ValueError("stop_pct must be in (0, 1)")
        if not 0 < self.target_pct < 1:
            raise ValueError("target_pct must be in (0, 1)")
        if self.max_regime_drawdown_1y is not None and not 0 <= self.max_regime_drawdown_1y <= 1:
            raise ValueError("max_regime_drawdown_1y must be in [0, 1] when set")
        if self.be_trigger_r is not None and self.be_trigger_r <= 0:
            raise ValueError("be_trigger_r must be > 0 when set")
        if self.be_lock_r < 0:
            raise ValueError("be_lock_r must be >= 0")
        if self.trail_atr_mult is not None and self.trail_atr_mult <= 0:
            raise ValueError("trail_atr_mult must be > 0 when set")
        if self.trail_trigger_r <= 0:
            raise ValueError("trail_trigger_r must be > 0")
        if self.short_extra_cost_bps < 0:
            raise ValueError("short_extra_cost_bps must be >= 0")
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be > 0")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_regimes"] = list(self.allowed_regimes)
        data["candidate_id"] = self.candidate_id()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContractCandidate":
        clean = dict(data)
        clean.pop("candidate_id", None)
        if "allowed_regimes" in clean:
            clean["allowed_regimes"] = tuple(clean["allowed_regimes"])
        return cls(**clean)

    def canonical_json(self) -> str:
        data = asdict(self)
        data["allowed_regimes"] = list(self.allowed_regimes)
        if data.get("side") == "long":
            data.pop("side", None)
            data.pop("short_extra_cost_bps", None)
        if data.get("vol_scaling") == "none":
            for key in ["vol_scaling", "vol_lookback_n", "vol_target_ann", "scale_min", "scale_max"]:
                data.pop(key, None)
        if data.get("family") != "pullback_long_v1":
            for key in ["trend_ema_len", "rsi_len", "rsi_entry_max", "rsi_exit_min", "entry_confirm"]:
                data.pop(key, None)
        else:
            data.pop("breakout_n", None)
            if data.get("entry_confirm") == "close_above_ema":
                data.pop("entry_confirm", None)
        if data.get("family") != "bear_rally_fade_short_v1":
            for key in ["regime_len", "slope_len", "rsi_hi", "stop_pct", "target_pct"]:
                data.pop(key, None)
        else:
            for key in ["breakout_n", "atr_n", "stop_atr_k", "tp_r_multiple"]:
                data.pop(key, None)
        if data.get("max_regime_drawdown_1y") is None:
            data.pop("max_regime_drawdown_1y", None)
        if data.get("be_trigger_r") is None:
            data.pop("be_trigger_r", None)
            data.pop("be_lock_r", None)
        elif float(data.get("be_lock_r", 0.0)) == 0.0:
            data.pop("be_lock_r", None)
        if data.get("trail_atr_mult") is None:
            data.pop("trail_atr_mult", None)
            data.pop("trail_trigger_r", None)
        elif float(data.get("trail_trigger_r", 1.0)) == 1.0:
            data.pop("trail_trigger_r", None)
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def candidate_id(self) -> str:
        digest = hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
        return digest[:16]
