import json
from pathlib import Path
from datetime import datetime

CONFIG_FILE = Path("config/strategies.json")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

changes = []

for s in data.get("strategies", []):
    sid = s.get("id", "")
    params = s.get("parameters", {})

    # ── 正向軌道 A: ma_cross_trend_v2 + rsi_mid_bounce ──
    if sid in ["ma_cross_trend_v2", "rsi_mid_bounce"]:
        if not s.get("enabled", False):
            s["enabled"] = True
            changes.append(f"✅ 啟用 {sid}")
        if "hour_restrictions" not in params:
            params["hour_restrictions"] = {
                "forbidden_hours": [0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 14, 15, 17, 18, 23],
                "boost_hours": [20, 22],
                "boost_multiplier": 1.5,
            }
            changes.append(f"🕐 {sid}: 加入時段過濾")
        s["parameters"] = params

    # ── 反向軌道 B: hilbert_cycle + opening_range_breakout ──
    if sid in ["hilbert_cycle", "opening_range_breakout"]:
        if not s.get("enabled", False):
            s["enabled"] = True
            changes.append(f"🔁 啟用 {sid}")
        if not params.get("reverse_mode", False):
            params["reverse_mode"] = True
            params["reverse_mode_note"] = "When strategy signals LONG, paper trade SHORT and vice versa"
            changes.append(f"🔁 {sid}: 標記反向模式")
        s["parameters"] = params

    # ── 禁用其他所有策略 ──
    if sid not in ["ma_cross_trend_v2", "rsi_mid_bounce", "hilbert_cycle", "opening_range_breakout"]:
        if s.get("enabled", False):
            s["enabled"] = False
            changes.append(f"❌ 禁用 {sid}")

# 全局設定
settings = data.get("settings", {})
settings["dual_track_active"] = True
settings["dual_track_started"] = datetime.now().isoformat()
settings["track_a_forward"] = ["ma_cross_trend_v2", "rsi_mid_bounce"]
settings["track_b_reverse"] = ["hilbert_cycle", "opening_range_breakout"]
settings["max_active_strategies"] = 4
settings["reverse_test_active"] = True
data["settings"] = settings

# 備份 + 寫入
backup = CONFIG_FILE.parent / f"strategies.json.bak.dual_track.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
with open(backup, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"{'='*60}")
print("  Dual Track Config Applied")
print(f"{'='*60}")
for c in changes:
    print(f"  • {c}")
print(f"\n  Backup: {backup}")
print("  重啟 scheduler 生效")
