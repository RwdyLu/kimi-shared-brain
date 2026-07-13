from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "revalidation_keeper_loop.sh"


def test_keeper_requires_recent_activity_before_holdout_by_default() -> None:
    text = SCRIPT.read_text()

    assert (
        'HOLDOUT_AUDITOR_REQUIRE_RECENT_ACTIVITY="${REVALIDATION_HOLDOUT_AUDITOR_REQUIRE_RECENT_ACTIVITY:-1}"'
        in text
    )
    assert 'auditor_args+=(--require-recent-activity-before-holdout)' in text
    assert "REVALIDATION_HOLDOUT_AUDITOR_REQUIRE_RECENT_ACTIVITY must be 0 or 1" in text


def test_keeper_defaults_allow_holdout_while_parallel_search_runs() -> None:
    text = SCRIPT.read_text()

    assert 'RUNNER_MAX_PYTHON_FACTORY="${REVALIDATION_RUNNER_MAX_PYTHON_FACTORY:-4}"' in text
    assert (
        'HOLDOUT_AUDITOR_MAX_PYTHON_FACTORY="${REVALIDATION_HOLDOUT_AUDITOR_MAX_PYTHON_FACTORY:-4}"'
        in text
    )
