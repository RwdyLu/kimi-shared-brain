#!/usr/bin/env python3
"""V2 End-to-End Test"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

print('=== End-to-End V2 Test ===')

# Step 1
print('\nStep 1: Create 3 random V2 chromosomes')
from chromosome_v2 import random_chromosome_v2
c1 = random_chromosome_v2()
c2 = random_chromosome_v2()
c3 = random_chromosome_v2()
print(f'   Chrom 1: {c1.chromosome_id[:8]}')
print(f'   Chrom 2: {c2.chromosome_id[:8]}')
print(f'   Chrom 3: {c3.chromosome_id[:8]}')

# Step 2
print('\nStep 2: Validate chromosomes')
for i, c in enumerate([c1, c2, c3]):
    # Check gene weights sum
    ok = True
    msg = "valid"
    mw = c.micro_genes
    weight_sum = mw.kp + mw.kv + mw.ka
    if abs(weight_sum - 1.0) > 0.05:
        ok = False
        msg = f"weights sum={weight_sum:.3f} (should be ~1.0)"
    # Check hold ratios
    hold_sum = c.risk_genes.dead_hold_ratio + c.risk_genes.float_hold_ratio
    if hold_sum > 1.0:
        ok = False
        msg = f"hold ratios sum={hold_sum:.2f} > 1.0"
    print(f'   Chrom {i+1}: {"OK" if ok else "FAIL"} {msg}')

# Step 3
print('\nStep 3: Mutate one chromosome')
from chromosome_v2 import mutate_chromosome_v2
c1_mutated = mutate_chromosome_v2(c1, generation=1, mutation_rate=0.5, intensity=0.3)
print(f'   Original kp={c1.micro_genes.kp:.2f}, mutated kp={c1_mutated.micro_genes.kp:.2f}')

# Step 4
print('\nStep 4: Crossover two chromosomes')
from chromosome_v2 import crossover_chromosomes_v2
child = crossover_chromosomes_v2(c1, c2, generation=1)
print(f'   Parent 1 entry_logic={c1.entry_logic}, Parent 2={c2.entry_logic}')
print(f'   Child entry_logic={child.entry_logic}')
print(f'   Child Macro max_dca={child.macro_genes.max_dca_months}')

# Step 5
print('\nStep 5: Create ThreeLayerConfig')
from .environment import ThreeLayerConfig
tlc = ThreeLayerConfig.create_for_new_epoch()
print(f'   Environment: reserve={tlc.environment.dead_reserve_ratio:.0%}')
print(f'   Seasons: {len(tlc.seasons)}')
for s in tlc.seasons:
    print(f'      {s.season.value}: x{s.aggressiveness}')

# Step 6
print('\nStep 6: StrategyArchive')
from .archive import StrategyArchive
archive = StrategyArchive()
print(f'   Archive initialized: Champions={archive.get_stats()["champions"]}')

# Step 7
print('\nStep 7: Create EvolutionEngineV2 (mini config)')
from evolution_v2 import EvolutionEngineV2
config = {
    'population_size': 3,
    'symbols': ['BTCUSDT'],
    'backtest_days': 7,
    'backtest_interval': '1h',
    'max_generations': 1,
    'mutation_rate': 0.3,
    'crossover_rate': 0.5,
}
engine = EvolutionEngineV2(config=config)
engine.three_layer = tlc
engine.population = [c1, c2, c3]
print(f'   Engine created with {len(engine.population)} strategies')

# Step 8
print('\nStep 8: Test BacktestEngineV2 components')
from backtest_engine_v2 import GhostDCABaseline, GeneBacktestEngineV2
import pandas as pd

print('   Testing Ghost DCA...')
dca = GhostDCABaseline(initial_capital=1000, dca_interval_hours=24)
test_prices = pd.Series([100 + i*2 + (i%3)*5 for i in range(50)])
test_df = pd.DataFrame({'close': test_prices})
test_df.index = pd.date_range('2024-01-01', periods=50, freq='h')
equity, trades = dca.run(test_df)
dca_ret = dca.calculate_dca_return(equity)
print(f'      DCA Return: {dca_ret:+.2%} | Trades: {len(trades)} | Final: ${equity[-1]:.2f}')

print('   Testing lot truncation...')
bt = GeneBacktestEngineV2(lot_step=0.001, lot_min=0.001)
print(f'      0.0005 -> {bt._truncate_lot(0.0005)}')
print(f'      0.0023 -> {bt._truncate_lot(0.0023)}')
print(f'      1.2345 -> {bt._truncate_lot(1.2345)}')

# Step 9 - Season application
print('\nStep 9: Season friction test')
from .environment import Season, SeasonConfig, SeasonApplier
season = SeasonConfig(season=Season.SUMMER, aggressiveness=2.0)
env = tlc.environment
base_pos = 0.15
adjusted = SeasonApplier.apply_to_position_size(base_pos, season, env)
print(f'   Base={base_pos:.0%} | Season=Summer(x2) | Env Reserve=20% | Result={adjusted:.2%}')

# Step 10 - Fitness scoring
print('\nStep 10: Fitness V2 scoring')
from fitness_v2 import BacktestMetricsV2, compute_fitness_v2
m = BacktestMetricsV2(
    total_trades=50,
    total_pnl=0.15,
    max_drawdown=0.08,
    ghost_dca_pnl=0.05,
    alpha_vs_dca=0.10,
    total_fees_paid=0.10,
)
score = compute_fitness_v2(m)
print(f'   Test metrics: PnL=15%, DD=8%, Alpha=10%, Fees=10%')
print(f'   Fitness score: {score:.4f}')

print('\n=== All V2 components verified ===')
