"""
Adaptive Parameter Tuner — Online Self-Correction Toward Profit
在線自適應調參器 — 根據實際交易結果自動修正參數

設計原則：
1. 只動「已經知道方向」的參數（止損太緊→放寬，止盈太低→提高）
2. 每次只微調 ±10-20%，不跳躍
3. 保留人工確認閘門（建議模式 vs 自動模式）
4. 所有調整留痕，可回滾

Author: kimiclaw_bot
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class TuningMode(Enum):
    """調參模式"""
    ADVISORY = "advisory"      # 只給建議，不寫入檔案
    AUTO = "auto"              # 自動寫入並應用
    SEMI_AUTO = "semi_auto"    # 寫入 staging，等待確認


class ActionType(Enum):
    """調整動作類型"""
    WIDEN_STOP = "widen_stop"           # 放寬止損
    TIGHTEN_STOP = "tighten_stop"       # 收緊止損
    RAISE_PROFIT = "raise_profit"       # 提高止盈
    LOWER_PROFIT = "lower_profit"       # 降低止盈
    REDUCE_SIZE = "reduce_size"         # 縮小倉位
    INCREASE_SIZE = "increase_size"     # 放大倉位
    ADJUST_ATR_MULT = "adjust_atr_mult" # 調整ATR倍數
    ADJUST_MA_WINDOW = "adjust_ma_window" # 調整MA週期


@dataclass
class TuningAction:
    """單個調參動作"""
    action_type: ActionType
    param_key: str                # 例如 "HARD_STOP_LOSS"
    old_value: float
    new_value: float
    reason: str                   # 為什麼調
    confidence: float             # 信心度 0.0-1.0
    evidence: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "action_type": self.action_type.value,
            "param_key": self.param_key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "delta_pct": (self.new_value - self.old_value) / abs(self.old_value) * 100 if self.old_value != 0 else 0,
            "reason": self.reason,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
        }


@dataclass
class TuningSession:
    """一次完整的調參會話"""
    session_id: str
    timestamp: datetime
    mode: TuningMode
    strategy_id: str
    actions: List[TuningAction] = field(default_factory=list)
    applied: bool = False
    reverted: bool = False

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "mode": self.mode.value,
            "strategy_id": self.strategy_id,
            "actions": [a.to_dict() for a in self.actions],
            "applied": self.applied,
            "reverted": self.reverted,
        }


class AdaptiveTuner:
    """
    在線自適應調參器。

    核心邏輯：
    1. 收集最近 N 筆交易，按 exit_reason 分類統計
    2. 識別「死亡模式」（如 atr_stop 佔比過高 = 止損太緊）
    3. 產生對應調參建議
    4. 根據模式寫入或建議
    """

    # 調整幅度限制（防止過度反應）
    MAX_ADJUSTMENT_PCT = 0.15          # 單次最多調 15%
    MIN_TRADES_FOR_TUNING = 10         # 至少 N 筆交易才調參
    LOOKBACK_TRADES = 30               # 分析最近 N 筆

    # 問題閾值
    THRESHOLD_ATR_STOP_DOMINANT = 0.40    # ATR止損佔比>40% → 放寬ATR或止損
    THRESHOLD_HARD_STOP_DOMINANT = 0.30   # 硬止損佔比>30% → 放寬硬止損
    THRESHOLD_MA_REVERSE_DOMINANT = 0.35  # MA反轉佔比>35% → 收緊MA反轉條件
    THRESHOLD_TIME_STOP_DOMINANT = 0.30   # 時間止損佔比>30% → 延長時間或縮小倉位
    THRESHOLD_SIGNAL_EXIT_DOMINANT = 0.50 # 訊號出場>50%且盈利低 → 提高止盈

    def __init__(
        self,
        strategies_json_path: str,
        paper_state_path: str,
        mode: TuningMode = TuningMode.ADVISORY,
        history_dir: str = "tuning_history",
    ):
        self.strategies_path = Path(strategies_json_path)
        self.paper_state_path = Path(paper_state_path)
        self.mode = mode
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(exist_ok=True)

        self.sessions: List[TuningSession] = []
        self.current_strategy_params: Dict = {}

        logger.info(f"AdaptiveTuner initialized | mode={mode.value}")

    # ═══════════════════════════════════════════════════════
    # 1. 數據收集與分析
    # ═══════════════════════════════════════════════════════

    def load_recent_trades(self, strategy_id: Optional[str] = None) -> List[Dict]:
        """讀取最近的交易記錄"""
        if not self.paper_state_path.exists():
            logger.warning("Paper trading state not found")
            return []

        try:
            with open(self.paper_state_path, "r") as f:
                state = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load paper state: {e}")
            return []

        # Paper trading state structure: strategies -> {sid: {trades: [...]}}
        strategies = state.get("strategies", {})

        if strategy_id:
            trades = strategies.get(strategy_id, {}).get("trades", [])
        else:
            trades = []
            for sid, acc in strategies.items():
                trades.extend(acc.get("trades", []))

        # 只取已平倉的交易 (exit_price present = closed)
        # 註：舊版交易記錄可能缺少 exit_reason，此處不強制要求
        closed = [
            t for t in trades
            if t.get("exit_price") is not None
        ]

        # 按時間排序，取最近 N 筆
        closed.sort(key=lambda t: t.get("exit_time", "") or t.get("entry_time", ""), reverse=True)
        return closed[: self.LOOKBACK_TRADES]

    def analyze_exit_patterns(self, trades: List[Dict]) -> Dict:
        """
        分析出場模式，識別問題。

        Returns:
            {
                "atr_stop_pct": 0.35,       # ATR止損佔比
                "hard_stop_pct": 0.20,      # 硬止損佔比
                "ma_reverse_pct": 0.15,     # MA反轉佔比
                "time_stop_pct": 0.10,      # 時間止損佔比
                "signal_exit_pct": 0.20,    # 訊號出場佔比
                "avg_pnl_by_reason": {...}, # 各原因的平均盈虧
                "problematic_reasons": [...] # 檢測到的問題原因
            }
        """
        if len(trades) < self.MIN_TRADES_FOR_TUNING:
            return {"error": f"Need {self.MIN_TRADES_FOR_TUNING} trades, got {len(trades)}"}

        total = len(trades)
        reasons = {}
        pnl_by_reason: Dict[str, List[float]] = {}

        for t in trades:
            reason = t.get("exit_reason", "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1

            pnl = t.get("pnl_pct", 0) or t.get("realized_pnl_pct", 0)
            if reason not in pnl_by_reason:
                pnl_by_reason[reason] = []
            pnl_by_reason[reason].append(pnl)

        # 計算佔比
        distribution = {r: c / total for r, c in reasons.items()}

        # 分類到標準原因
        atr_stop_pct = sum(distribution.get(k, 0) for k in distribution if "atr" in k.lower())
        hard_stop_pct = sum(distribution.get(k, 0) for k in distribution if "hard" in k.lower())
        ma_reverse_pct = sum(distribution.get(k, 0) for k in distribution if "ma" in k.lower() or "reverse" in k.lower())
        time_stop_pct = sum(distribution.get(k, 0) for k in distribution if "time" in k.lower())
        signal_exit_pct = sum(distribution.get(k, 0) for k in distribution if "signal" in k.lower())

        # 各原因平均盈虧
        avg_pnl = {
            r: (sum(v) / len(v) if v else 0)
            for r, v in pnl_by_reason.items()
        }

        # 問題檢測
        problems = []
        if atr_stop_pct > self.THRESHOLD_ATR_STOP_DOMINANT:
            problems.append({
                "type": "atr_stop_dominant",
                "pct": atr_stop_pct,
                "avg_pnl": avg_pnl.get(next((k for k in pnl_by_reason if "atr" in k.lower()), ""), 0),
                "suggestion": "ATR止損過頻繁，可能ATR倍數太低或硬止損太緊",
            })
        if hard_stop_pct > self.THRESHOLD_HARD_STOP_DOMINANT:
            problems.append({
                "type": "hard_stop_dominant",
                "pct": hard_stop_pct,
                "avg_pnl": avg_pnl.get(next((k for k in pnl_by_reason if "hard" in k.lower()), ""), 0),
                "suggestion": "硬止損觸發過多，市場波動可能大於-5%",
            })
        if ma_reverse_pct > self.THRESHOLD_MA_REVERSE_DOMINANT:
            problems.append({
                "type": "ma_reverse_dominant",
                "pct": ma_reverse_pct,
                "avg_pnl": avg_pnl.get(next((k for k in pnl_by_reason if "ma" in k.lower()), ""), 0),
                "suggestion": "MA反轉出場過多，條件太寬鬆",
            })
        if time_stop_pct > self.THRESHOLD_TIME_STOP_DOMINANT:
            problems.append({
                "type": "time_stop_dominant",
                "pct": time_stop_pct,
                "avg_pnl": avg_pnl.get(next((k for k in pnl_by_reason if "time" in k.lower()), ""), 0),
                "suggestion": "時間止損過多，可能選股/進場時機有問題",
            })
        if signal_exit_pct > self.THRESHOLD_SIGNAL_EXIT_DOMINANT:
            signal_pnl = sum(
                avg_pnl.get(k, 0) * distribution.get(k, 0)
                for k in distribution if "signal" in k.lower()
            ) / signal_exit_pct if signal_exit_pct > 0 else 0
            if signal_pnl < 0.01:  # 訊號出場平均盈利太低
                problems.append({
                    "type": "signal_exit_unprofitable",
                    "pct": signal_exit_pct,
                    "avg_pnl": signal_pnl,
                    "suggestion": "訊號出場盈利太低，止盈可能設太低",
                })

        return {
            "total_trades": total,
            "distribution": distribution,
            "atr_stop_pct": atr_stop_pct,
            "hard_stop_pct": hard_stop_pct,
            "ma_reverse_pct": ma_reverse_pct,
            "time_stop_pct": time_stop_pct,
            "signal_exit_pct": signal_exit_pct,
            "avg_pnl_by_reason": avg_pnl,
            "problematic_reasons": problems,
            "overall_avg_pnl": sum(t.get("pnl_pct", 0) or t.get("realized_pnl_pct", 0) for t in trades) / total,
        }

    # ═══════════════════════════════════════════════════════
    # 2. 決策引擎 — 識別問題 → 產生動作
    # ═══════════════════════════════════════════════════════

    def generate_actions(
        self,
        analysis: Dict,
        strategy_id: str,
        current_params: Optional[Dict] = None,
    ) -> List[TuningAction]:
        """
        根據分析結果產生調參動作。
        """
        actions = []
        problems = analysis.get("problematic_reasons", [])

        if not problems:
            logger.info(f"[{strategy_id}] No problems detected — no tuning needed")
            return actions

        # 讀取當前參數
        if current_params is None:
            current_params = self._load_strategy_params(strategy_id)

        for problem in problems:
            ptype = problem["type"]
            confidence = min(problem["pct"] * 2, 0.95)  # 佔比越高信心越強，上限0.95

            if ptype == "atr_stop_dominant":
                # ATR止損過多 → 提高ATR倍數或放寬硬止損
                atr_mult = current_params.get("atr_stop_multiplier", 1.5)
                new_mult = self._clamp_adjustment(atr_mult, 1.3, 3.0, +0.15)
                actions.append(TuningAction(
                    action_type=ActionType.ADJUST_ATR_MULT,
                    param_key="atr_stop_multiplier",
                    old_value=atr_mult,
                    new_value=new_mult,
                    reason=f"ATR止損佔比{problem['pct']:.0%}過高，提高ATR倍數減少過早出場",
                    confidence=confidence,
                    evidence=problem,
                ))

                # 同時微調硬止損作為緩衝
                hard_stop = current_params.get("hard_stop_loss", -0.05)
                if abs(hard_stop) < 0.10:  # 還有空間
                    new_stop = self._clamp_adjustment(hard_stop, -0.15, -0.03, +0.10)
                    actions.append(TuningAction(
                        action_type=ActionType.WIDEN_STOP,
                        param_key="hard_stop_loss",
                        old_value=hard_stop,
                        new_value=new_stop,
                        reason=f"配合ATR調整，微放寬硬止損至{new_stop:.1%}",
                        confidence=confidence * 0.7,
                        evidence=problem,
                    ))

            elif ptype == "hard_stop_dominant":
                # 硬止損過多 → 放寬硬止損
                hard_stop = current_params.get("hard_stop_loss", -0.05)
                new_stop = self._clamp_adjustment(hard_stop, -0.15, -0.03, +0.15)
                actions.append(TuningAction(
                    action_type=ActionType.WIDEN_STOP,
                    param_key="hard_stop_loss",
                    old_value=hard_stop,
                    new_value=new_stop,
                    reason=f"硬止損佔比{problem['pct']:.0%}過高，放寬至{new_stop:.1%}",
                    confidence=confidence,
                    evidence=problem,
                ))

            elif ptype == "ma_reverse_dominant":
                # MA反轉過多 → 收緊條件（提高虧損門檻）
                ma_threshold = current_params.get("ma_reverse_pnl_threshold", -0.005)
                # 更負 = 更難觸發（需要虧更多才允許MA反轉）
                new_threshold = self._clamp_adjustment(ma_threshold, -0.05, -0.001, -0.20)
                actions.append(TuningAction(
                    action_type=ActionType.TIGHTEN_STOP,
                    param_key="ma_reverse_pnl_threshold",
                    old_value=ma_threshold,
                    new_value=new_threshold,
                    reason=f"MA反轉佔比{problem['pct']:.0%}過高，收緊至虧損<{new_threshold:.2%}才允許反轉",
                    confidence=confidence,
                    evidence=problem,
                ))

            elif ptype == "time_stop_dominant":
                # 時間止損過多 → 延長時間或縮小倉位
                time_limit = current_params.get("time_stop_hours", 8.0)
                new_time = self._clamp_adjustment(time_limit, 4.0, 24.0, +0.15)
                actions.append(TuningAction(
                    action_type=ActionType.ADJUST_MA_WINDOW,
                    param_key="time_stop_hours",
                    old_value=time_limit,
                    new_value=new_time,
                    reason=f"時間止損佔比{problem['pct']:.0%}過高，延長至{new_time:.1f}小時",
                    confidence=confidence,
                    evidence=problem,
                ))

                # 順便縮小倉位，降低時間成本
                position_pct = current_params.get("position_pct", 0.15)
                if position_pct > 0.05:
                    new_pos = self._clamp_adjustment(position_pct, 0.05, 0.50, -0.10)
                    actions.append(TuningAction(
                        action_type=ActionType.REDUCE_SIZE,
                        param_key="position_pct",
                        old_value=position_pct,
                        new_value=new_pos,
                        reason=f"時間止損多 = 資金佔用成本高，縮小倉位至{new_pos:.0%}",
                        confidence=confidence * 0.6,
                        evidence=problem,
                    ))

            elif ptype == "signal_exit_unprofitable":
                # 訊號出場盈利太低 → 提高階梯止盈
                # 提高所有階梯的基線
                profit_targets = current_params.get("profit_targets", {})
                if profit_targets:
                    new_targets = {}
                    for minute, target in profit_targets.items():
                        new_targets[minute] = self._clamp_adjustment(
                            target, 0.001, 0.20, +0.10
                        )
                    actions.append(TuningAction(
                        action_type=ActionType.RAISE_PROFIT,
                        param_key="profit_targets",
                        old_value=profit_targets,
                        new_value=new_targets,
                        reason=f"訊號出場平均僅{problem['avg_pnl']:.2%}，提高階梯止盈10%",
                        confidence=confidence,
                        evidence=problem,
                    ))

        return actions

    def _clamp_adjustment(
        self, current: float, min_val: float, max_val: float, delta_pct: float
    ) -> float:
        """
        在限制範圍內做百分比調整。
        delta_pct > 0 = 增加，< 0 = 減少
        """
        new_val = current * (1 + delta_pct)
        # 限制單次最大調整幅度
        max_delta = abs(current) * self.MAX_ADJUSTMENT_PCT
        if abs(new_val - current) > max_delta:
            direction = 1 if delta_pct > 0 else -1
            new_val = current + direction * max_delta

        # 限制範圍
        return max(min_val, min(max_val, new_val))

    # ═══════════════════════════════════════════════════════
    # 3. 應用與持久化
    # ═══════════════════════════════════════════════════════

    def run_tuning(self, strategy_id: Optional[str] = None) -> TuningSession:
        """
        執行一次完整的調參流程。

        Args:
            strategy_id: 指定策略（None = 分析全局/主要策略）

        Returns:
            TuningSession 包含所有建議/已應用的動作
        """
        session_id = f"TUNE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session = TuningSession(
            session_id=session_id,
            timestamp=datetime.now(),
            mode=self.mode,
            strategy_id=strategy_id or "global",
        )

        # 1. 載入交易
        trades = self.load_recent_trades(strategy_id)
        if not trades:
            logger.warning(f"[{strategy_id}] No closed trades found for tuning")
            return session

        # 2. 分析
        analysis = self.analyze_exit_patterns(trades)
        if "error" in analysis:
            logger.info(f"[{strategy_id}] {analysis['error']}")
            return session

        logger.info(
            f"[{strategy_id}] Analyzed {analysis['total_trades']} trades | "
            f"avg_pnl={analysis['overall_avg_pnl']:.2%} | "
            f"problems={len(analysis['problematic_reasons'])}"
        )

        # 3. 產生動作
        current_params = self._load_strategy_params(strategy_id)
        actions = self.generate_actions(analysis, strategy_id or "global", current_params)
        session.actions = actions

        if not actions:
            logger.info(f"[{strategy_id}] No tuning actions generated")
            self._save_session(session)
            return session

        # 4. 根據模式處理
        if self.mode == TuningMode.ADVISORY:
            logger.info(f"[{strategy_id}] ADVISORY mode — {len(actions)} suggestions ready")
            for a in actions:
                logger.info(f"  SUGGEST: {a.param_key} {a.old_value} → {a.new_value} ({a.reason})")

        elif self.mode == TuningMode.SEMI_AUTO:
            # 寫入 staging 檔案，等待人工確認
            self._write_staging(session)
            logger.info(f"[{strategy_id}] SEMI_AUTO mode — {len(actions)} actions staged")

        elif self.mode == TuningMode.AUTO:
            # 直接應用
            self._apply_actions(actions, strategy_id)
            session.applied = True
            logger.info(f"[{strategy_id}] AUTO mode — {len(actions)} actions applied")

        self._save_session(session)
        return session

    def _load_strategy_params(self, strategy_id: Optional[str]) -> Dict:
        """從 strategies.json 讀取參數"""
        if not self.strategies_path.exists():
            return {}
        try:
            with open(self.strategies_path, "r") as f:
                data = json.load(f)
            if strategy_id and "strategies" in data:
                for s in data["strategies"]:
                    if s.get("id") == strategy_id:
                        return s.get("parameters", {})  # FIX: was "params"
            # 返回全域預設
            return data.get("default_params", {})
        except Exception as e:
            logger.error(f"Failed to load strategy params: {e}")
            return {}

    def _save_strategy_params(self, strategy_id: str, params: Dict):
        """寫入 strategies.json"""
        if not self.strategies_path.exists():
            data = {"strategies": [], "default_params": {}}
        else:
            with open(self.strategies_path, "r") as f:
                data = json.load(f)

        updated = False
        for s in data.get("strategies", []):
            if s.get("id") == strategy_id:
                s["parameters"] = params  # FIX: was "params"
                s["last_tuned"] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            data["strategies"].append({
                "id": strategy_id,
                "parameters": params,  # FIX: was "params"
                "last_tuned": datetime.now().isoformat(),
            })

        with open(self.strategies_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _apply_actions(self, actions: List[TuningAction], strategy_id: Optional[str]):
        """將動作應用到參數檔"""
        params = self._load_strategy_params(strategy_id)

        for action in actions:
            params[action.param_key] = action.new_value
            logger.info(
                f"  APPLIED: {action.param_key} = {action.old_value} → {action.new_value}"
            )

        self._save_strategy_params(strategy_id or "global", params)

    def _write_staging(self, session: TuningSession):
        """寫入待確認的 staging 檔"""
        staging_path = self.history_dir / f"staging_{session.session_id}.json"
        with open(staging_path, "w") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Staging file written: {staging_path}")

    def _save_session(self, session: TuningSession):
        """保存調參歷史"""
        self.sessions.append(session)
        filepath = self.history_dir / f"session_{session.session_id}.json"
        with open(filepath, "w") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

    def approve_staging(self, session_id: str) -> bool:
        """人工確認後應用 staging 的調參"""
        staging_path = self.history_dir / f"staging_{session_id}.json"
        if not staging_path.exists():
            logger.error(f"Staging file not found: {staging_path}")
            return False

        with open(staging_path, "r") as f:
            data = json.load(f)

        # 重建動作
        actions = []
        for a_data in data.get("actions", []):
            actions.append(TuningAction(
                action_type=ActionType(a_data["action_type"]),
                param_key=a_data["param_key"],
                old_value=a_data["old_value"],
                new_value=a_data["new_value"],
                reason=a_data["reason"],
                confidence=a_data["confidence"],
            ))

        self._apply_actions(actions, data.get("strategy_id"))

        # 標記已應用
        data["applied"] = True
        with open(staging_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Staging {session_id} approved and applied")
        return True

    def revert_last_tuning(self, strategy_id: Optional[str] = None) -> bool:
        """回滾最後一次調參"""
        # 找到最後一次應用的 session
        applicable = [
            s for s in self.sessions
            if s.applied and (not strategy_id or s.strategy_id == strategy_id)
        ]
        if not applicable:
            logger.warning("No applied sessions to revert")
            return False

        last = max(applicable, key=lambda s: s.timestamp)

        # 反向應用
        reverse_actions = []
        for a in last.actions:
            reverse_actions.append(TuningAction(
                action_type=a.action_type,  # 類型相同但方向相反
                param_key=a.param_key,
                old_value=a.new_value,
                new_value=a.old_value,
                reason=f"REVERT: {a.reason}",
                confidence=1.0,
            ))

        self._apply_actions(reverse_actions, last.strategy_id)
        last.reverted = True
        self._save_session(last)

        logger.info(f"Reverted session {last.session_id}")
        return True

    # ═══════════════════════════════════════════════════════
    # 4. 報告與查詢
    # ═══════════════════════════════════════════════════════

    def get_tuning_report(self, strategy_id: Optional[str] = None) -> Dict:
        """產生調參報告"""
        sessions = self.sessions
        if strategy_id:
            sessions = [s for s in sessions if s.strategy_id == strategy_id]

        applied = [s for s in sessions if s.applied]
        reverted = [s for s in sessions if s.reverted]

        return {
            "total_sessions": len(sessions),
            "applied": len(applied),
            "reverted": len(reverted),
            "pending_staging": len([s for s in sessions if not s.applied and not s.reverted]),
            "recent_actions": [
                {
                    "session_id": s.session_id,
                    "timestamp": s.timestamp.isoformat(),
                    "actions": [a.to_dict() for a in s.actions],
                    "applied": s.applied,
                }
                for s in sessions[-5:]
            ],
        }

    def export_history(self, filepath: str):
        """匯出完整歷史"""
        data = {
            "exported_at": datetime.now().isoformat(),
            "mode": self.mode.value,
            "total_sessions": len(self.sessions),
            "sessions": [s.to_dict() for s in self.sessions],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# 5. 整合 scheduler 用的 wrapper
# ═════════════════════════════════════════════════════════════════==

class AutoTunerScheduler:
    """
    掛載到現有 scheduler 的定時調參任務。

    用法：
        tuner = AutoTunerScheduler(
            strategies_json="app/strategies.json",
            paper_state="data/paper_trading_state.json",
            mode="advisory",  # 或 "semi_auto" / "auto"
        )
        # 每 6 小時檢查一次
        tuner.schedule_every(hours=6)
    """

    def __init__(
        self,
        strategies_json: str,
        paper_state: str,
        mode: str = "advisory",
        min_trades: int = 10,
    ):
        self.tuner = AdaptiveTuner(
            strategies_json_path=strategies_json,
            paper_state_path=paper_state,
            mode=TuningMode(mode),
        )
        self.min_trades = min_trades
        self.last_run: Optional[datetime] = None

    def check_and_tune(self, strategy_ids: Optional[List[str]] = None) -> List[TuningSession]:
        """
        檢查條件並執行調參。
        返回所有 session（沒調的也返回空 session）。
        """
        results = []

        # 如果沒指定策略，自動發現所有有交易的策略
        if strategy_ids is None:
            strategy_ids = self._discover_strategies()

        for sid in strategy_ids:
            trades = self.tuner.load_recent_trades(sid)
            if len(trades) < self.min_trades:
                logger.info(f"[{sid}] Only {len(trades)} trades, skipping")
                continue

            session = self.tuner.run_tuning(sid)
            results.append(session)

        self.last_run = datetime.now()
        return results

    def _discover_strategies(self) -> List[str]:
        """從交易記錄發現有數據的策略"""
        all_trades = self.tuner.load_recent_trades()
        sids = set()
        for t in all_trades:
            sid = t.get("strategy_id")
            if sid:
                sids.add(sid)
        return list(sids)

    def get_summary(self) -> str:
        """文字摘要，適合 log/通知"""
        if not self.last_run:
            return "AutoTuner: Never run"

        report = self.tuner.get_tuning_report()
        lines = [
            f"AutoTuner | Last run: {self.last_run.strftime('%Y-%m-%d %H:%M')}",
            f"  Sessions: {report['total_sessions']} | Applied: {report['applied']} | Reverted: {report['reverted']}",
        ]
        for recent in report["recent_actions"][-3:]:
            action_strs = [f"{a['param_key']}→{a['new_value']}" for a in recent["actions"]]
            lines.append(f"  [{recent['session_id'][:20]}] {' | '.join(action_strs) or 'no actions'}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 6. 命令行入口
# ═════════════════════════════════════════════════════════════════==

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Adaptive Parameter Tuner")
    parser.add_argument("--strategies", default="app/strategies.json")
    parser.add_argument("--paper-state", default="data/paper_trading_state.json")
    parser.add_argument("--mode", choices=["advisory", "semi_auto", "auto"], default="advisory")
    parser.add_argument("--strategy-id", help="特定策略ID（不指定則分析全部）")
    parser.add_argument("--approve", help="確認 staging session_id")
    parser.add_argument("--revert", action="store_true", help="回滾最後一次調參")
    parser.add_argument("--report", action="store_true", help="輸出報告")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    tuner = AdaptiveTuner(
        strategies_json_path=args.strategies,
        paper_state_path=args.paper_state,
        mode=TuningMode(args.mode),
    )

    if args.approve:
        tuner.approve_staging(args.approve)
    elif args.revert:
        tuner.revert_last_tuning(args.strategy_id)
    elif args.report:
        report = tuner.get_tuning_report(args.strategy_id)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        session = tuner.run_tuning(args.strategy_id)
        print(json.dumps(session.to_dict(), indent=2, ensure_ascii=False))
