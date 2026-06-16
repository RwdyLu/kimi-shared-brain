"""Phase B tests for staged GA eligibility rules."""

from app.genetic_engine.eligibility import check_stage_eligibility, get_stage_for_epoch


def _valid_metrics(**overrides):
    metrics = {
        "avg_alpha": 0.02,
        "ruin_probability": 0.02,
        "max_drawdown": 0.10,
        "profit_factor": 1.25,
        "sharpe_ratio": 0.8,
        "win_rate": 0.48,
        "total_trades": 300,
        "profitable_symbols": 6,
        "worst_symbol_alpha": -0.02,
        "single_symbol_profit_contribution": 0.40,
        "symbols_tested": 10,
        "data_invalid": False,
    }
    metrics.update(overrides)
    return metrics


def _failed_metrics(result):
    return {rule["metric"] for rule in result["failed_rules"]}


def test_epoch_number_maps_to_expected_stage():
    assert get_stage_for_epoch(1) == "stage1_explore"
    assert get_stage_for_epoch(10) == "stage1_explore"
    assert get_stage_for_epoch(11) == "stage2_converge"
    assert get_stage_for_epoch(30) == "stage2_converge"
    assert get_stage_for_epoch(31) == "stage3_validate"


def test_stage1_passing_strategy_is_seed_candidate_not_challenger():
    result = check_stage_eligibility(
        _valid_metrics(avg_alpha=-0.005, ruin_probability=0.15, max_drawdown=0.20),
        "stage1_explore",
    )

    assert result["eligible"] is True
    assert result["challenger_eligible"] is False
    assert result["candidate_status"] == "seed_candidate"


def test_stage2_passing_strategy_is_seed_candidate_not_challenger():
    result = check_stage_eligibility(
        _valid_metrics(avg_alpha=0.002, ruin_probability=0.08, max_drawdown=0.15),
        "stage2_converge",
    )

    assert result["eligible"] is True
    assert result["challenger_eligible"] is False
    assert result["candidate_status"] == "seed_candidate"


def test_stage3_passing_strategy_can_be_challenger():
    result = check_stage_eligibility(_valid_metrics(), "stage3_validate")

    assert result["eligible"] is True
    assert result["challenger_eligible"] is True
    assert result["candidate_status"] == "qualified_challenger"


def test_negative_alpha_strategy_does_not_pass_stage3():
    result = check_stage_eligibility(_valid_metrics(avg_alpha=-0.0496), "stage3_validate")

    assert result["eligible"] is False
    assert "avg_alpha" in _failed_metrics(result)
    assert "avg_alpha" in result["rejected_reason"]


def test_ruin_probability_one_is_direct_rejected():
    result = check_stage_eligibility(
        {
            "avg_alpha": -0.0496,
            "ruin_probability": 1.0,
            "total_trades": 2669,
            "symbols_tested": 10,
            "data_invalid": False,
        },
        "stage3_validate",
    )

    assert result["eligible"] is False
    assert result["challenger_eligible"] is False
    assert "ruin_probability" in _failed_metrics(result)
    assert "ruin_probability" in result["rejected_reason"]


def test_missing_required_metric_fails_instead_of_using_mock():
    metrics = _valid_metrics()
    del metrics["profit_factor"]

    result = check_stage_eligibility(metrics, "stage3_validate")

    assert result["eligible"] is False
    assert "profit_factor" in _failed_metrics(result)
    assert "metric missing: profit_factor" in result["rejected_reason"]


def test_symbols_tested_below_ten_fails():
    result = check_stage_eligibility(_valid_metrics(symbols_tested=9), "stage3_validate")

    assert result["eligible"] is False
    assert "symbols_tested" in _failed_metrics(result)


def test_data_invalid_fails():
    result = check_stage_eligibility(_valid_metrics(data_invalid=True), "stage3_validate")

    assert result["eligible"] is False
    assert "data_invalid" in _failed_metrics(result)


def test_profitable_symbols_below_stage_threshold_fails():
    result = check_stage_eligibility(_valid_metrics(profitable_symbols=4), "stage3_validate")

    assert result["eligible"] is False
    assert "profitable_symbols" in _failed_metrics(result)


def test_single_symbol_profit_contribution_too_high_fails():
    result = check_stage_eligibility(
        _valid_metrics(single_symbol_profit_contribution=0.80),
        "stage3_validate",
    )

    assert result["eligible"] is False
    assert "single_symbol_profit_contribution" in _failed_metrics(result)


def test_ruin_probability_can_come_from_monte_carlo_final_review():
    metrics = _valid_metrics()
    metrics.pop("ruin_probability")
    metrics["monte_carlo_final_review"] = {"ruin_probability": 0.02}

    result = check_stage_eligibility(metrics, "stage3_validate")

    assert result["eligible"] is True
    assert result["metrics"]["ruin_probability"] == 0.02
