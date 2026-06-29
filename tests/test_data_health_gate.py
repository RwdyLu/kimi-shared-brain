import json
import subprocess
import sys
from pathlib import Path


def test_data_gate_allows_only_symbols_with_contiguous_valid_months(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import data_health_gate as gate_mod

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "BTCUSDT_4h_2020-01_2020-06.json").write_text(
        json.dumps({"valid_months": ["2020-01", "2020-02", "2020-03", "2020-04"]})
    )
    (manifest_dir / "LINKUSDT_4h_2020-01_2020-06.json").write_text(
        json.dumps({"valid_months": ["2020-01", "2020-03", "2020-05"]})
    )

    gate = gate_mod.DataHealthGate(manifest_dir, "4h", "2020-01", "2020-06", 3)
    result = gate.summarize(["BTCUSDT", "LINKUSDT", "ETHUSDT"], gate_mod.month_range("2020-01", "2020-06"))

    assert result.allowed_symbols == ["BTCUSDT"]
    assert result.blocked_symbols["LINKUSDT"] == "no_contiguous_valid_block_3_months"
    assert result.blocked_symbols["ETHUSDT"] == "missing_data_manifest"


def test_freqtrade_bridge_rejects_internal_candidate_without_smoke_flag(tmp_path):
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "manifest.json").write_text(
        json.dumps(
            {
                "strategy_id": "smoke",
                "symbol": "ETHUSDT",
                "timeframe": "4h",
                "approval_status": "internal_candidate_only",
            }
        )
    )
    out = tmp_path / "ft"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/freqtrade_dry_run_bridge.py",
            "--artifact",
            str(artifact),
            "--out-dir",
            str(out),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode != 0
    assert "Refusing to export Freqtrade dry-run strategy" in (proc.stderr + proc.stdout)
