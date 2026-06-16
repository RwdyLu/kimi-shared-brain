"""
Tests for GA Gene Schema Audit (Phase F)

Verifies:
1. audit script is read-only (no writes to runtime data)
2. audit script does not start worker
3. audit script does not call promote
4. audit script does not call exchange/order/account API
5. registry entry validation (valid passes, invalid fails)
6. proposal validation (status constraints, required fields)
7. dead gene detection
8. fixed parameter detection

Safety: All tests are read-only and do not start any process.
"""

import ast
import json
import sys
from pathlib import Path

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_SCRIPT = PROJECT_ROOT / "scripts" / "audit_gene_schema.py"

sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Script safety: no forbidden writes or calls
# ═══════════════════════════════════════════════════════════════════════════════

def _get_audit_source() -> str:
    assert AUDIT_SCRIPT.exists(), f"audit script not found: {AUDIT_SCRIPT}"
    return AUDIT_SCRIPT.read_text(encoding="utf-8")


def test_audit_script_does_not_write_state_dir():
    """audit script must not write to state/"""
    src = _get_audit_source()
    # Allow the constant definition line itself
    lines = [l for l in src.splitlines() if "state/" in l and not l.strip().startswith("#")]
    write_lines = [l for l in lines if any(w in l for w in ("open(", ".write(", "json.dump", "FORBIDDEN_WRITE_DIRS"))]
    # Only the FORBIDDEN_WRITE_DIRS constant may reference state/
    forbidden_writes = [l for l in write_lines if "FORBIDDEN_WRITE_DIRS" not in l]
    assert not forbidden_writes, f"Audit script writes to state/: {forbidden_writes}"


def test_audit_script_does_not_write_logs_dir():
    """audit script must not write to logs/"""
    src = _get_audit_source()
    lines = [l for l in src.splitlines() if "logs/" in l and not l.strip().startswith("#")]
    write_lines = [l for l in lines if any(w in l for w in ("open(", ".write(", "json.dump"))]
    forbidden_writes = [l for l in write_lines if "FORBIDDEN_WRITE_DIRS" not in l]
    assert not forbidden_writes, f"Audit script writes to logs/: {forbidden_writes}"


def test_audit_script_does_not_write_genetic_archive():
    """audit script must not write to data/genetic_archive/"""
    src = _get_audit_source()
    lines = [l for l in src.splitlines() if "genetic_archive" in l and not l.strip().startswith("#")]
    write_lines = [l for l in lines if any(w in l for w in ("open(", ".write(", "json.dump"))]
    forbidden_writes = [l for l in write_lines if "FORBIDDEN_WRITE_DIRS" not in l]
    assert not forbidden_writes, f"Audit script writes to genetic_archive/: {forbidden_writes}"


def test_audit_script_does_not_start_worker():
    """audit script must not call run_evolution_worker or subprocess.Popen with worker"""
    src = _get_audit_source()
    forbidden_patterns = [
        "run_evolution_worker",
        "subprocess.Popen",
        "subprocess.run.*worker",
        "os.system.*worker",
    ]
    for pat in forbidden_patterns:
        import re
        if re.search(pat, src):
            lines = [l for l in src.splitlines() if re.search(pat, l)]
            pytest.fail(f"Audit script references worker-start pattern '{pat}': {lines}")


def _find_actual_calls(src: str, symbol: str) -> list[str]:
    """Find lines where symbol is actually called (sym(...)), not just mentioned in strings/comments."""
    import re
    call_pattern = re.compile(rf'\b{re.escape(symbol)}\s*\(')
    results = []
    for line in src.splitlines():
        if not call_pattern.search(line):
            continue
        stripped = line.strip()
        # Skip comment lines
        if stripped.startswith("#"):
            continue
        # Skip lines where the call appears only after a # comment marker
        code_part = line.split("#")[0]
        if not call_pattern.search(code_part):
            continue
        # Skip string-literal-only lines (e.g. "promote_to_champion", in a list)
        # These look like: '    "promote_to_champion",' or "    'GA_CONTINUOUS',"
        if re.match(r'^\s*["\']', stripped) or re.match(r'^\s*-\s', stripped):
            continue
        results.append(stripped[:100])
    return results


def test_audit_script_does_not_call_promote():
    """audit script must not call promote_to_champion or promote_challenger"""
    src = _get_audit_source()
    for sym in ["promote_to_champion", "promote_challenger"]:
        actual = _find_actual_calls(src, sym)
        assert not actual, f"Audit script calls '{sym}': {actual}"


def test_audit_script_does_not_call_exchange_api():
    """audit script must not call create_order/send_order/market_order exchange API"""
    src = _get_audit_source()
    for sym in ["create_order", "send_order", "market_order"]:
        actual = _find_actual_calls(src, sym)
        assert not actual, f"Audit script calls exchange API '{sym}': {actual}"


def test_audit_script_does_not_set_ga_continuous():
    """audit script must not assign GA_CONTINUOUS=true as an env var or os.environ"""
    import re
    src = _get_audit_source()
    # Only flag actual assignment/setenv patterns, not string literals or constant lists
    bad_patterns = [
        re.compile(r'os\.environ\[.GA_CONTINUOUS.\]\s*='),
        re.compile(r'GA_CONTINUOUS.*=.*[Tt]rue'),
        re.compile(r'setenv.*GA_CONTINUOUS'),
    ]
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("-") or stripped.startswith('"') or stripped.startswith("'"):
            continue
        for pat in bad_patterns:
            if pat.search(line):
                pytest.fail(f"Audit script sets GA_CONTINUOUS: {stripped}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Import and basic execution
# ═══════════════════════════════════════════════════════════════════════════════

def test_audit_module_imports():
    """audit script can be imported without side effects"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_gene_schema", AUDIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "build_report")
    assert hasattr(mod, "validate_registry_entry")
    assert hasattr(mod, "validate_proposal_entry")
    assert hasattr(mod, "MACRO_ACTIVE_FIELDS")
    assert hasattr(mod, "MACRO_LEGACY_FIELDS")


def test_build_report_returns_dict():
    """build_report() returns a dict with expected top-level keys"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_gene_schema", AUDIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    report = mod.build_report()
    assert isinstance(report, dict)
    for key in ("phase", "summary", "dead_genes", "fixed_parameters", "macro_genes", "micro_genes"):
        assert key in report, f"Missing key '{key}' in report"


def test_build_report_no_runtime_writes(tmp_path, monkeypatch):
    """build_report() does not write any files"""
    import importlib.util

    written_files = []
    original_open = open

    def mock_open(path, mode="r", *args, **kwargs):
        if "w" in mode or "a" in mode:
            written_files.append(str(path))
            raise PermissionError(f"Test: write blocked to {path}")
        return original_open(path, mode, *args, **kwargs)

    spec = importlib.util.spec_from_file_location("audit_gene_schema", AUDIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # build_report should not open any file for writing
    monkeypatch.setattr("builtins.open", mock_open)
    report = mod.build_report()
    assert isinstance(report, dict)
    assert written_files == [], f"build_report() wrote files: {written_files}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Registry entry validation
# ═══════════════════════════════════════════════════════════════════════════════

def _load_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_gene_schema", AUDIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_valid_registry_entry_passes():
    mod = _load_mod()
    entry = {
        "name": "stop_loss_pct",
        "block": "risk",
        "type": "float",
        "min": -0.15,
        "max": -0.02,
        "default": -0.05,
        "mutation": {"method": "proportional", "clamp": True},
        "enabled": True,
        "owner": "human_approved",
    }
    errors = mod.validate_registry_entry(entry)
    assert errors == [], f"Valid entry should pass: {errors}"


def test_registry_entry_missing_type_fails():
    mod = _load_mod()
    entry = {
        "name": "stop_loss_pct",
        "min": -0.15,
        "max": -0.02,
    }
    errors = mod.validate_registry_entry(entry)
    assert any("type" in e.lower() for e in errors), f"Should fail for missing type: {errors}"


def test_registry_entry_invalid_type_fails():
    mod = _load_mod()
    entry = {
        "name": "my_gene",
        "type": "complex_number",
        "min": 0,
        "max": 1,
    }
    errors = mod.validate_registry_entry(entry)
    assert any("type" in e.lower() for e in errors), f"Should fail for invalid type: {errors}"


def test_registry_entry_invalid_range_fails():
    mod = _load_mod()
    entry = {
        "name": "bad_range_gene",
        "type": "float",
        "min": 0.5,
        "max": 0.1,
    }
    errors = mod.validate_registry_entry(entry)
    assert any("range" in e.lower() or "min" in e.lower() for e in errors), \
        f"Should fail for invalid range (min >= max): {errors}"


def test_registry_entry_unknown_mutation_method_fails():
    mod = _load_mod()
    entry = {
        "name": "test_gene",
        "type": "float",
        "min": 0.0,
        "max": 1.0,
        "mutation": {"method": "magic_wand"},
    }
    errors = mod.validate_registry_entry(entry)
    assert any("mutation" in e.lower() or "method" in e.lower() for e in errors), \
        f"Should fail for unknown mutation method: {errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Proposal validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_valid_proposal_passes():
    mod = _load_mod()
    proposal = {
        "proposal_id": "gene_prop_test_001",
        "name": "cooldown_bars",
        "block": "frequency",
        "type": "int",
        "min": 0,
        "max": 50,
        "reason": "Prevent repeated re-entry",
        "expected_effect": "Reduce fee drag",
        "risk": "May miss opportunities",
        "tests_required": ["schema_validation", "mutation_smoke_test"],
        "status": "proposed",
        "requires_human_approval": True,
    }
    errors = mod.validate_proposal_entry(proposal)
    assert errors == [], f"Valid proposal should pass: {errors}"


def test_proposal_inactive_cannot_auto_activate():
    """A proposal in 'active' status should fail validation — human approval required first."""
    mod = _load_mod()
    proposal = {
        "proposal_id": "gene_prop_auto_001",
        "name": "auto_gene",
        "reason": "AI decided to add this",
        "expected_effect": "Unknown",
        "risk": "Unknown",
        "tests_required": [],
        "status": "active",
        "requires_human_approval": True,
    }
    errors = mod.validate_proposal_entry(proposal)
    assert any("active" in e.lower() or "human" in e.lower() for e in errors), \
        f"Should reject 'active' status without approved transition: {errors}"


def test_proposal_missing_required_fields_fails():
    mod = _load_mod()
    proposal = {
        "name": "incomplete_gene",
        "status": "proposed",
    }
    errors = mod.validate_proposal_entry(proposal)
    assert len(errors) > 0, "Should fail for missing required fields"
    required_mentions = [e for e in errors if "reason" in e or "expected_effect" in e or "risk" in e]
    assert required_mentions, f"Should specifically mention missing required fields: {errors}"


def test_proposal_requires_human_approval_true():
    """requires_human_approval must be explicitly True."""
    mod = _load_mod()
    proposal = {
        "proposal_id": "gene_prop_no_approval",
        "name": "sneaky_gene",
        "reason": "Bypass approval",
        "expected_effect": "None",
        "risk": "None",
        "tests_required": [],
        "status": "proposed",
        "requires_human_approval": False,
    }
    errors = mod.validate_proposal_entry(proposal)
    assert any("human" in e.lower() or "approval" in e.lower() for e in errors), \
        f"Should reject requires_human_approval=False: {errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Dead gene detection
# ═══════════════════════════════════════════════════════════════════════════════

def test_dead_genes_detected():
    mod = _load_mod()
    dead = mod.audit_dead_genes()
    assert len(dead) > 0, "Should detect at least one dead gene"
    dead_names = {d["gene_name"] for d in dead}
    # These known dead genes must be detected
    assert "max_dca_months" in dead_names, "max_dca_months should be a dead gene"
    assert "moon_phase_pressure" in dead_names, "moon_phase_pressure should be a dead gene"
    assert "global_stop_loss (trigger)" in dead_names, "global_stop_loss trigger should be flagged"


def test_macro_active_fields_not_in_dead():
    """Active macro fields must NOT be classified as dead."""
    mod = _load_mod()
    dead = mod.audit_dead_genes()
    dead_names = {d["gene_name"] for d in dead}
    for field in mod.MACRO_ACTIVE_FIELDS:
        assert field not in dead_names, f"Active field '{field}' incorrectly listed as dead gene"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Fixed parameter detection
# ═══════════════════════════════════════════════════════════════════════════════

def test_fixed_parameters_detected():
    mod = _load_mod()
    fixed = mod.audit_fixed_parameters()
    assert len(fixed) > 0, "Should detect at least one fixed parameter"
    param_names = {fp["parameter"] for fp in fixed}
    assert "fee_rate" in param_names, "fee_rate should be in fixed parameters"
    assert "cooldown_bars" in param_names, "cooldown_bars should be in fixed parameters"
    assert "slippage_rate" in param_names, "slippage_rate should be in fixed parameters"


def test_fixed_parameters_have_required_keys():
    mod = _load_mod()
    fixed = mod.audit_fixed_parameters()
    required_keys = {"parameter", "current_value", "source_file", "should_be_gene", "priority", "reason", "recommended_block"}
    for fp in fixed:
        missing = required_keys - set(fp.keys())
        assert not missing, f"Fixed parameter '{fp.get('parameter')}' missing keys: {missing}"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Registry example is self-consistent
# ═══════════════════════════════════════════════════════════════════════════════

def test_registry_example_valid():
    """The built-in REGISTRY_EXAMPLE should pass validation for all genes."""
    mod = _load_mod()
    registry = mod.REGISTRY_EXAMPLE
    assert "genes" in registry
    for gene in registry["genes"]:
        errors = mod.validate_registry_entry(gene)
        assert errors == [], f"Registry example gene '{gene.get('name')}' is invalid: {errors}"


def test_proposal_example_valid():
    """The built-in PROPOSAL_EXAMPLE should pass validation."""
    mod = _load_mod()
    errors = mod.validate_proposal_entry(mod.PROPOSAL_EXAMPLE)
    assert errors == [], f"Proposal example is invalid: {errors}"
