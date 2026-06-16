"""
一次性清理 state/live_strategy_ranking.json 中的歷史 duplicate。
執行前先備份：cp state/live_strategy_ranking.json state/live_strategy_ranking.json.bak
人工確認輸出後再解除注釋最後一行再執行一次。
"""
import json, sys
from pathlib import Path
project_root_early = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root_early))
from app.strategy_identity import build_strategy_alias_map, resolve_strategy_id

# 載入 strategies config
project_root = Path(__file__).resolve().parents[1]
strategies = json.loads((project_root / 'config' / 'strategies.json').read_text())["strategies"]
aliases = build_strategy_alias_map(strategies)

path = project_root / 'state' / 'live_strategy_ranking.json'
data = json.loads(path.read_text())

changed = 0
for sym, sym_data in data.get("symbols", {}).items():
    merged = {}
    for entry in sym_data.get("strategies", []):
        canonical = resolve_strategy_id(entry.get("name", ""), entry.get("name", ""), aliases)
        if canonical not in merged:
            merged[canonical] = {**entry, "name": canonical}
        else:
            # 保留較高 rolling_avg
            if entry.get("rolling_avg", 0) > merged[canonical].get("rolling_avg", 0):
                merged[canonical] = {**entry, "name": canonical}
            changed += 1
    sym_data["strategies"] = list(merged.values())

# 同理清理 rolling_scores
for key in list(data.get("rolling_scores", {}).keys()):
    canonical = resolve_strategy_id(key, key, aliases)
    if canonical != key:
        existing = data["rolling_scores"].get(canonical, [])
        data["rolling_scores"][canonical] = existing or data["rolling_scores"].pop(key)
        changed += 1

print(f"\u5408併了 {changed} 筆 duplicate。預覽前 3 個 symbol 策略列表：")
for sym in list(data["symbols"].keys())[:3]:
    names = [s["name"] for s in data["symbols"][sym].get("strategies", [])]
    print(f"  {sym}: {names}")

# 確認無誤後解除注釋下一行
# path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
print("\n請確認上方輸出，確認無誤後取消最後一行的註解再執行一次。")
