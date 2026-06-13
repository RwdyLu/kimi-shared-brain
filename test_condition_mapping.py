#!/usr/bin/env python3
"""
Test script: Verify genetic condition mapping to strategy_conditions.py
生成 50 個隨機染色體，檢查轉換後的條件是否全部在 strategy_conditions.py 的檢查器中
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.genetic_engine.gene_library import random_gene, IndicatorType, ConditionType
from app.genetic_engine.chromosome import random_chromosome
from app.genetic_engine.converter import convert_to_strategy_json, _gene_to_condition_name
from app.strategy_conditions import StrategyConditions

def test_mapping(population_size=50):
    """生成 population_size 個隨機染色體並檢查條件映射"""
    
    # 取得所有已實作的檢查器名稱
    sc = StrategyConditions()
    valid_conditions = set(sc._checkers.keys())
    print(f"✅ strategy_conditions.py 已實作檢查器: {len(valid_conditions)} 個")
    
    all_conditions = []
    invalid_conditions = []
    
    # 生成 50 個隨機染色體
    for i in range(population_size):
        chrom = random_chromosome()
        strategy_json = convert_to_strategy_json(chrom)
        conditions = strategy_json.get("conditions", [])
        all_conditions.extend(conditions)
        
        for cond in conditions:
            if cond not in valid_conditions:
                invalid_conditions.append({
                    "chromosome_id": chrom.chromosome_id,
                    "condition": cond,
                    "entry_genes": [g.name + "_" + g.condition.value for g in chrom.entry_genes],
                    "exit_genes": [g.name + "_" + g.condition.value for g in chrom.exit_genes],
                })
    
    # 統計
    unique_conditions = set(all_conditions)
    print(f"\n📊 測試結果:")
    print(f"   生成染色體: {population_size}")
    print(f"   總條件數: {len(all_conditions)}")
    print(f"   唯一條件數: {len(unique_conditions)}")
    print(f"   無效條件數: {len(invalid_conditions)}")
    
    print(f"\n🔍 使用的條件分布:")
    from collections import Counter
    cond_counts = Counter(all_conditions)
    for cond, count in cond_counts.most_common():
        status = "✅" if cond in valid_conditions else "❌"
        print(f"   {status} {cond}: {count}")
    
    if invalid_conditions:
        print(f"\n❌ 無效條件詳情:")
        for inv in invalid_conditions[:10]:  # 只顯示前10個
            print(f"   {inv['condition']} (from {inv['chromosome_id']})")
            print(f"      Entry genes: {inv['entry_genes']}")
            print(f"      Exit genes: {inv['exit_genes']}")
    else:
        print(f"\n✅ 所有條件都有效！")
    
    return len(invalid_conditions) == 0

if __name__ == "__main__":
    success = test_mapping(population_size=50)
    sys.exit(0 if success else 1)
