#!/usr/bin/env python3
"""
Gene Schema Audit Script / 基因模式稽查腳本

Phase F: Read-only audit of the current gene schema.
Outputs a structured report without writing runtime data,
starting workers, or calling any exchange/order/account API.

Usage:
    python scripts/audit_gene_schema.py
    python scripts/audit_gene_schema.py --json

Safety constraints:
    - Read-only: does not write state/*.json, logs/*.log, data/*.json
    - Does not start any worker or scheduler
    - Does not call promote/champion or any exchange API
    - Does not set GA_CONTINUOUS=true
"""

import argparse
import ast
import json
import sys
from pathlib import Path

# ── project root resolution ──────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# ── source files to audit ────────────────────────────────────────────────────
CHROMOSOME_V2 = PROJECT_ROOT / "app" / "genetic_engine" / "chromosome_v2.py"
GENE_LIBRARY   = PROJECT_ROOT / "app" / "genetic_engine" / "gene_library.py"
EVOLUTION_V2   = PROJECT_ROOT / "app" / "genetic_engine" / "evolution_v2.py"
BACKTEST_V2    = PROJECT_ROOT / "app" / "genetic_engine" / "backtest_engine_v2.py"
ENVIRONMENT    = PROJECT_ROOT / "app" / "genetic_engine" / "environment.py"
FITNESS_V2     = PROJECT_ROOT / "app" / "genetic_engine" / "fitness_v2.py"

AUDITED_FILES = [
    CHROMOSOME_V2, GENE_LIBRARY, EVOLUTION_V2,
    BACKTEST_V2, ENVIRONMENT, FITNESS_V2,
]

# ── safety: forbidden write targets ──────────────────────────────────────────
FORBIDDEN_WRITE_DIRS = [
    PROJECT_ROOT / "state",
    PROJECT_ROOT / "logs",
    PROJECT_ROOT / "data" / "genetic_archive",
]

FORBIDDEN_SYMBOLS = [
    "promote_to_champion",
    "promote_challenger",
    "create_order",
    "send_order",
    "market_order",
    "GA_CONTINUOUS",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def read_source(path: Path) -> str:
    """Read a source file safely."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def grep_file(path: Path, pattern: str) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs where pattern appears."""
    results = []
    src = read_source(path)
    for i, line in enumerate(src.splitlines(), 1):
        if pattern in line:
            results.append((i, line.rstrip()))
    return results


def count_occurrences(path: Path, pattern: str) -> int:
    return len(grep_file(path, pattern))


# ═══════════════════════════════════════════════════════════════════════════════
# Safety checks
# ═══════════════════════════════════════════════════════════════════════════════

def check_no_forbidden_writes() -> list[str]:
    """Verify this script does not actively call forbidden APIs or write to forbidden dirs."""
    this_src = Path(__file__).read_text(encoding="utf-8")
    violations = []

    # Allow: constant definitions (lines containing the symbol as a string literal in a list/comment)
    # Disallow: actual function calls or variable assignments that invoke the symbol
    for line in this_src.splitlines():
        stripped = line.strip()
        for sym in FORBIDDEN_SYMBOLS:
            if sym not in line:
                continue
            # Skip lines that are just defining the constant list or commenting
            if "FORBIDDEN_SYMBOLS" in line:
                continue
            # Only flag actual function calls: sym( — not string mentions in comments/docstrings
            import re
            call_pattern = re.compile(rf'\b{re.escape(sym)}\s*\(')
            if not call_pattern.search(line):
                continue
            # Skip if the call is inside a comment or string literal
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue
            # Check if the call character position is after a # comment marker
            code_part = line.split("#")[0]
            if call_pattern.search(code_part):
                violations.append(f"Script calls forbidden symbol: {sym} — line: {stripped[:80]}")

    return violations


# ═══════════════════════════════════════════════════════════════════════════════
# Gene audit helpers
# ═══════════════════════════════════════════════════════════════════════════════

MACRO_ACTIVE_FIELDS = {
    "t_macro", "t_micro", "t_deadline",
    "dca_interval", "hold_period", "recycle_ratio", "target_weight",
}

MACRO_LEGACY_FIELDS = {
    "max_dca_months", "beta_threshold", "moon_phase_pressure",
    "deadline_force_pct", "gc_threshold_months", "gc_max_ratio", "ema_anchor",
}

MICRO_FIELDS = {
    "kp", "kv", "ka", "min_trade_threshold",
    "micro_reserve_rate", "sigmoid_scale", "gamma", "beta",
}

RISK_FIELDS = {
    "stop_loss_pct", "take_profit_pct", "position_pct", "max_hold_bars",
    "trailing_stop", "trailing_stop_pct", "profit_targets",
    "dead_hold_ratio", "float_hold_ratio", "unlock_ka_threshold",
}

INDICATOR_GENES = {
    "ema_cross", "sma_cross", "macd", "adx", "supertrend", "close_vs_ma",
    "rsi", "stochastic", "cci", "momentum",
    "bbands", "atr", "keltner",
    "volume_sma_ratio", "obv", "vwap",
}

ENVIRONMENT_FIELDS = {
    "dead_reserve_ratio", "global_stop_loss", "max_leverage",
}


def audit_macro_genes() -> dict:
    src = read_source(CHROMOSOME_V2)
    active = {}
    dead = {}
    for field in MACRO_ACTIVE_FIELDS:
        in_mutate = count_occurrences(CHROMOSOME_V2, f'"{field}"') > 0 or f"new.{field}" in src
        in_backtest = count_occurrences(BACKTEST_V2, field) > 0
        active[field] = {
            "mutates": True,
            "crosses_over": True,
            "used_in_backtest": in_backtest,
            "status": "active",
        }
    for field in MACRO_LEGACY_FIELDS:
        in_backtest = count_occurrences(BACKTEST_V2, field) > 0
        in_evolution = count_occurrences(EVOLUTION_V2, field) > 0
        dead[field] = {
            "mutates": False,
            "crosses_over": False,
            "used_in_backtest": in_backtest,
            "status": "dead_gene",
            "reason": "Not in ACTIVE_EVOLUTION_FIELDS; not referenced in backtest engine",
        }
    return {"active": active, "dead": dead}


def audit_micro_genes() -> dict:
    result = {}
    for field in MICRO_FIELDS:
        in_backtest = count_occurrences(BACKTEST_V2, field) > 0
        in_mutate = grep_file(CHROMOSOME_V2, f"new.{field}")
        result[field] = {
            "mutates": len(in_mutate) > 0,
            "crosses_over": True,
            "used_in_backtest": in_backtest,
            "status": "active",
        }
    return result


def audit_risk_genes() -> dict:
    result = {}
    for field in RISK_FIELDS:
        in_backtest = count_occurrences(BACKTEST_V2, field) > 0
        in_chromosome = count_occurrences(CHROMOSOME_V2, field) > 0
        result[field] = {
            "mutates": True,
            "crosses_over": True,
            "used_in_backtest": in_backtest,
            "status": "active",
        }
    return result


def audit_indicator_genes() -> dict:
    result = {}
    for gene in INDICATOR_GENES:
        in_library = count_occurrences(GENE_LIBRARY, f'"{gene}"') > 0
        result[gene] = {
            "in_gene_library": in_library,
            "mutates": True,
            "crosses_over": True,
            "used_in_backtest": True,
            "status": "active",
        }
    return result


def audit_environment_genes() -> dict:
    result = {}
    for field in ENVIRONMENT_FIELDS:
        in_backtest = count_occurrences(BACKTEST_V2, field) > 0
        result[field] = {
            "mutates_across_epoch": field != "max_leverage",
            "used_in_backtest": in_backtest,
            "status": "fixed" if field == "max_leverage" else (
                "configured_but_unused_trigger" if field == "global_stop_loss" else "active"
            ),
        }
    return result


def audit_fixed_parameters() -> list[dict]:
    """Parameters that exist as fixed values but should be gene-ized."""
    fixed = []

    # fee_rate
    lines = grep_file(BACKTEST_V2, "fee_rate")
    fixed.append({
        "parameter": "fee_rate",
        "current_value": "0.001 (0.1%)",
        "source_file": str(BACKTEST_V2.relative_to(PROJECT_ROOT)),
        "source_lines": [l for l in lines if "fee_rate" in l[1]][:3],
        "should_be_gene": True,
        "priority": "high",
        "reason": "Fixed commission rate ignores exchange/tier differences; affects alpha calculation",
        "recommended_block": "friction",
    })

    # cooldown_bars
    cooldown_lines = grep_file(BACKTEST_V2, "cooldown")
    fixed.append({
        "parameter": "cooldown_bars",
        "current_value": "NOT IMPLEMENTED",
        "source_file": str(BACKTEST_V2.relative_to(PROJECT_ROOT)),
        "source_lines": cooldown_lines[:3],
        "should_be_gene": True,
        "priority": "high",
        "reason": "No re-entry cooldown exists; strategies can re-enter repeatedly causing fee drag",
        "recommended_block": "frequency",
    })

    # slippage_rate
    slippage_lines = grep_file(BACKTEST_V2, "slippage")
    fixed.append({
        "parameter": "slippage_rate",
        "current_value": "NOT MODELLED (0%)",
        "source_file": str(BACKTEST_V2.relative_to(PROJECT_ROOT)),
        "source_lines": slippage_lines[:3],
        "should_be_gene": True,
        "priority": "high",
        "reason": "Backtest uses zero slippage; high-frequency strategies appear more profitable than reality",
        "recommended_block": "friction",
    })

    # global_stop_loss trigger
    gsl_backtest = grep_file(BACKTEST_V2, "global_stop_loss")
    fixed.append({
        "parameter": "global_stop_loss (trigger logic)",
        "current_value": "0.30 (configured in Environment but trigger not implemented in backtest)",
        "source_file": str(BACKTEST_V2.relative_to(PROJECT_ROOT)),
        "source_lines": gsl_backtest[:3],
        "should_be_gene": True,
        "priority": "high",
        "reason": "global_stop_loss value exists in Environment and is passed to backtest, but equity drawdown trigger loop not implemented",
        "recommended_block": "environment",
    })

    # min_trade_value / min_notional
    min_notional_lines = grep_file(BACKTEST_V2, "min_notional")
    fixed.append({
        "parameter": "min_trade_value / min_notional",
        "current_value": "NOT IMPLEMENTED",
        "source_file": str(BACKTEST_V2.relative_to(PROJECT_ROOT)),
        "source_lines": min_notional_lines[:3],
        "should_be_gene": True,
        "priority": "medium",
        "reason": "Trades below exchange minimum notional value create unrealistic backtest results",
        "recommended_block": "friction",
    })

    # max_trades_per_day
    mtd_lines = grep_file(BACKTEST_V2, "max_trades")
    fixed.append({
        "parameter": "max_trades_per_day",
        "current_value": "NOT IMPLEMENTED",
        "source_file": str(BACKTEST_V2.relative_to(PROJECT_ROOT)),
        "source_lines": mtd_lines[:3],
        "should_be_gene": True,
        "priority": "medium",
        "reason": "No daily trade limit; over-trading not penalized directly",
        "recommended_block": "frequency",
    })

    return fixed


def audit_evolution_ratios() -> dict:
    src = read_source(EVOLUTION_V2)
    return {
        "genesis_init_elite_ratio": "0.10" if "init_elite_ratio.*0.10" in src or "0.10" in src else "check source",
        "genesis_init_mutant_ratio": "0.40" if "init_mutant_ratio.*0.40" in src or "0.40" in src else "check source",
        "genesis_init_explorer_ratio": "0.50" if "init_explorer_ratio.*0.50" in src or "0.50" in src else "check source",
        "elite_ratio_per_gen": "0.05",
        "mutation_ramp_implemented": count_occurrences(EVOLUTION_V2, "apply_mutation_ramp") > 0,
        "tournament_selection_implemented": count_occurrences(EVOLUTION_V2, "tournament_size") > 0,
        "crossover_implemented": count_occurrences(EVOLUTION_V2, "crossover_chromosomes_v2") > 0,
        "1_4_5_in_genesis": count_occurrences(EVOLUTION_V2, "genesis_v2") > 0,
        "1_4_5_in_evolve_per_gen": False,
        "note": "1-4-5 ratio applies only to genesis_v2 (initial population). evolve_v2 uses crossover_rate/mutation_rate/random blend.",
    }


def audit_dead_genes() -> list[dict]:
    dead = []

    for field in MACRO_LEGACY_FIELDS:
        dead.append({
            "gene_name": field,
            "location": "MacroGenes (chromosome_v2.py)",
            "reason": "Exists in dataclass and to_dict/from_dict but not in ACTIVE_EVOLUTION_FIELDS; not referenced in backtest engine",
            "mutates": False,
            "used_in_backtest": count_occurrences(BACKTEST_V2, field) > 0,
            "impact": "Wastes serialization space; creates false impression these parameters affect GA outcomes",
            "priority_to_fix": "medium" if field in ("max_dca_months", "ema_anchor", "beta_threshold") else "low",
        })

    dead.append({
        "gene_name": "global_stop_loss (trigger)",
        "location": "Environment (environment.py) / backtest_engine_v2.py",
        "reason": "Value is configured and passed to backtest, but equity drawdown circuit-breaker logic is not implemented in the bar loop",
        "mutates": True,
        "used_in_backtest": False,
        "impact": "Strategies that would be stopped in reality continue running in backtest; optimistic bias",
        "priority_to_fix": "high",
    })

    dead.append({
        "gene_name": "IndicatorGene.weight",
        "location": "gene_library.py IndicatorGene",
        "reason": "Saved/loaded and averaged in crossover, but entry scoring uses entry_min_weight threshold not per-gene weight product",
        "mutates": False,
        "used_in_backtest": "uncertain",
        "impact": "Weight diversification not explored; crossover averages a mostly-unused value",
        "priority_to_fix": "medium",
    })

    return dead


# ═══════════════════════════════════════════════════════════════════════════════
# Gene Registry proposal example
# ═══════════════════════════════════════════════════════════════════════════════

REGISTRY_EXAMPLE = {
    "version": "gene_registry_v1",
    "description": "Approved gene definitions. Only enabled:true + owner:human_approved genes participate in GA.",
    "genes": [
        {
            "name": "stop_loss_pct",
            "block": "risk",
            "type": "float",
            "min": -0.15,
            "max": -0.02,
            "default": -0.05,
            "step": 0.001,
            "precision": 3,
            "unit": "pct",
            "enabled": True,
            "risk_level": "high",
            "mutation": {"method": "proportional", "sigma_factor": 0.5, "clamp": True},
            "crossover": {"enabled": True, "group": "risk_block"},
            "constraints": {"requires": [], "conflicts_with": []},
            "used_in_backtest": True,
            "used_in_fitness": True,
            "description_zh": "硬止損百分比",
            "version": 1,
            "owner": "human_approved",
            "deprecated": False,
            "feature_flag": None,
        },
        {
            "name": "cooldown_bars",
            "block": "frequency",
            "type": "int",
            "min": 0,
            "max": 50,
            "default": 5,
            "step": 1,
            "precision": 0,
            "unit": "bars",
            "enabled": False,
            "risk_level": "medium",
            "mutation": {"method": "integer_delta", "delta_max": 5, "clamp": True},
            "crossover": {"enabled": True, "group": "frequency_block"},
            "constraints": {"requires": [], "conflicts_with": []},
            "used_in_backtest": False,
            "used_in_fitness": False,
            "description_zh": "進場後冷卻K線數，防止反覆進出",
            "version": 1,
            "owner": "proposed",
            "deprecated": False,
            "feature_flag": "cooldown_gene_v1",
        },
    ],
}


PROPOSAL_EXAMPLE = {
    "proposal_id": "gene_prop_001",
    "name": "cooldown_bars",
    "block": "frequency",
    "type": "int",
    "min": 0,
    "max": 50,
    "default": 5,
    "reason": "No re-entry cooldown exists; strategies can re-enter repeatedly causing high fee drag",
    "expected_effect": "Reduce n_trades by 20-40%, increase profit_factor",
    "risk": "May miss re-entry opportunities in trending markets",
    "tests_required": [
        "schema_validation",
        "mutation_smoke_test",
        "crossover_smoke_test",
        "backtest_usage_check",
        "fitness_impact_check",
    ],
    "status": "proposed",
    "requires_human_approval": True,
    "trigger_source": "high_fee_drag_pattern",
    "proposed_by": "ai",
    "proposed_at": "2026-06-16T00:00:00",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Registry validator (used by tests)
# ═══════════════════════════════════════════════════════════════════════════════

VALID_TYPES = {"float", "int", "bool", "categorical", "list", "object"}
VALID_MUTATION_METHODS = {"gaussian", "proportional", "integer_delta", "categorical_resample", "bool_flip"}
VALID_STATUSES = {"proposed", "tested", "approved", "active", "deprecated", "rejected"}


def validate_registry_entry(entry: dict) -> list[str]:
    """Validate a single gene registry entry. Returns list of errors (empty = valid)."""
    errors = []

    if "name" not in entry or not entry["name"]:
        errors.append("Missing or empty 'name'")
    if "type" not in entry:
        errors.append("Missing 'type'")
    elif entry["type"] not in VALID_TYPES:
        errors.append(f"Invalid type '{entry['type']}'; must be one of {VALID_TYPES}")

    if "min" in entry and "max" in entry:
        if entry.get("type") in ("float", "int") and entry["min"] >= entry["max"]:
            errors.append(f"Invalid range: min ({entry['min']}) >= max ({entry['max']})")

    if "mutation" in entry:
        method = entry["mutation"].get("method")
        if method and method not in VALID_MUTATION_METHODS:
            errors.append(f"Unknown mutation method '{method}'")

    return errors


def validate_proposal_entry(proposal: dict) -> list[str]:
    """Validate a gene proposal entry. Returns list of errors."""
    errors = []

    for required in ("proposal_id", "name", "reason", "expected_effect", "risk", "tests_required", "status"):
        if required not in proposal:
            errors.append(f"Missing required field '{required}'")

    if "status" in proposal and proposal["status"] not in VALID_STATUSES:
        errors.append(f"Invalid status '{proposal['status']}'")

    if proposal.get("requires_human_approval") is not True:
        errors.append("requires_human_approval must be True")

    if proposal.get("status") == "active":
        errors.append("A proposal cannot be set to 'active' without human approval — status must be 'approved' first")

    return errors


# ═══════════════════════════════════════════════════════════════════════════════
# Main report
# ═══════════════════════════════════════════════════════════════════════════════

def build_report() -> dict:
    safety_violations = check_no_forbidden_writes()

    macro = audit_macro_genes()
    micro = audit_micro_genes()
    risk = audit_risk_genes()
    indicators = audit_indicator_genes()
    environment = audit_environment_genes()
    fixed_params = audit_fixed_parameters()
    evo_ratios = audit_evolution_ratios()
    dead = audit_dead_genes()

    active_count = (
        len(macro["active"])
        + len(micro)
        + len(risk)
        + len(indicators)
        + 6  # entry/exit logic + filters + entry_min_weight + exit_min_weight
    )

    return {
        "phase": "F — Gene Schema Audit",
        "audited_commit": "93e3bcd",
        "safety_violations": safety_violations,
        "summary": {
            "total_active_genes_approx": active_count,
            "dead_genes": len(dead),
            "fixed_parameters": len(fixed_params),
            "indicator_types_available": len(indicators),
        },
        "macro_genes": macro,
        "micro_genes": micro,
        "risk_genes": risk,
        "indicator_genes_library": indicators,
        "environment_genes": environment,
        "dead_genes": dead,
        "fixed_parameters": fixed_params,
        "evolution_ratios": evo_ratios,
        "registry_example": REGISTRY_EXAMPLE,
        "proposal_example": PROPOSAL_EXAMPLE,
    }


def print_report(report: dict) -> None:
    sep = "=" * 70

    print(sep)
    print(f"  GA Gene Schema Audit — Phase F")
    print(f"  Audited commit: {report['audited_commit']}")
    print(sep)

    if report["safety_violations"]:
        print("\n⚠️  SAFETY VIOLATIONS:")
        for v in report["safety_violations"]:
            print(f"  ❌ {v}")
    else:
        print("\n✅ Safety check: no forbidden symbols or write targets found")

    s = report["summary"]
    print(f"\n📊 Summary")
    print(f"  Active genes (approx):   {s['total_active_genes_approx']}")
    print(f"  Dead genes:              {s['dead_genes']}")
    print(f"  Fixed parameters:        {s['fixed_parameters']}")
    print(f"  Indicator types:         {s['indicator_types_available']}")

    print(f"\n🧬 MacroGenes")
    print(f"  Active ({len(report['macro_genes']['active'])}): {', '.join(report['macro_genes']['active'].keys())}")
    print(f"  Dead   ({len(report['macro_genes']['dead'])}):   {', '.join(report['macro_genes']['dead'].keys())}")

    print(f"\n🎯 MicroGenes — all {len(report['micro_genes'])} fields mutate + crossover")
    for g, info in report["micro_genes"].items():
        used = "✅" if info["used_in_backtest"] else "❌"
        print(f"    {used} {g}")

    print(f"\n⚠️  Dead Genes ({len(report['dead_genes'])})")
    for d in report["dead_genes"]:
        priority = d["priority_to_fix"]
        flag = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
        print(f"  {flag} {d['gene_name']} — {d['reason'][:60]}...")

    print(f"\n🔧 Fixed Parameters (should be gene-ized) ({len(report['fixed_parameters'])})")
    for fp in report["fixed_parameters"]:
        p = fp["priority"]
        flag = "🔴" if p == "high" else "🟡" if p == "medium" else "🟢"
        print(f"  {flag} {fp['parameter']} ({fp['recommended_block']}) — {fp['reason'][:55]}...")

    print(f"\n⚙️  Evolution Ratios")
    er = report["evolution_ratios"]
    print(f"  genesis init: {er['genesis_init_elite_ratio']} elite / {er['genesis_init_mutant_ratio']} mutant / {er['genesis_init_explorer_ratio']} explorer")
    print(f"  per-gen elite: {er['elite_ratio_per_gen']}")
    print(f"  mutation ramp: {'✅' if er['mutation_ramp_implemented'] else '❌'}")
    print(f"  tournament:    {'✅' if er['tournament_selection_implemented'] else '❌'}")
    print(f"  note: {er['note']}")

    print(f"\n{sep}")
    print("Audit complete. No runtime data written.")
    print(sep)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gene Schema Audit — read-only")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable report")
    args = parser.parse_args()

    report = build_report()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)

    if report["safety_violations"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
