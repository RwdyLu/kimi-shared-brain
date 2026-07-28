from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "watch_train_only_artifact_ingest.sh"


def write_fake_ingest_script(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "v9_ingest_train_only_artifact.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path('ingested.txt').write_text(' '.join(sys.argv[1:]))\n"
    )


def run_watcher(tmp_path: Path, output_json: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "WATCH_TRAIN_ONLY_INGEST_POLL_SEC": "1",
        "WATCH_TRAIN_ONLY_INGEST_TIMEOUT_SEC": "5",
    }
    return subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--task-name",
            "unit_task",
            "--preset",
            "unit_preset",
            "--output-json",
            str(output_json),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_watch_ingests_completed_artifact_without_progress_files(tmp_path) -> None:
    write_fake_ingest_script(tmp_path)
    output_json = tmp_path / "artifact.json"
    output_json.write_text('{"kind": "unit"}')

    result = run_watcher(tmp_path, output_json)

    assert result.returncode == 0, result.stderr
    assert "ingesting completed artifact" in result.stdout
    assert "unit_task" in (tmp_path / "ingested.txt").read_text()


def test_watch_ingests_completed_artifact_with_stale_progress_files(tmp_path) -> None:
    write_fake_ingest_script(tmp_path)
    output_json = tmp_path / "artifact.json"
    output_json.write_text('{"kind": "unit"}')
    output_json.with_suffix(".progress.jsonl").write_text("{}\n")
    output_json.with_suffix(".progress.meta.json").write_text('{"total_rows": 1}\n')

    result = run_watcher(tmp_path, output_json)

    assert result.returncode == 0, result.stderr
    assert "stale progress files" in result.stdout
    assert "unit_task" in (tmp_path / "ingested.txt").read_text()
