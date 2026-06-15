"""Tests for deterministic 1D tolerance stack-up analysis."""

from __future__ import annotations

import math

import pytest

from app.tolerance_analysis import analyze_tolerance_stackup


def test_three_link_chain_hand_calculation() -> None:
    """A 3-link chain with symmetric tolerances.

    Nominal total = 10 + 20 + 30 = 60
    Worst-case band = +/-(0.1 + 0.2 + 0.3) = +/-0.6  => [59.4, 60.6]
    RSS sigma = sqrt(3*((0.6)/6)^2) = sqrt(3*0.01) = sqrt(0.03) ≈ 0.173205
    95% band = +/-1.96*sigma ≈ +/-0.339482
    """
    contributors = [
        {"name": "link_a", "nominal": 10.0, "plus": 0.1, "minus": 0.1},
        {"name": "link_b", "nominal": 20.0, "plus": 0.2, "minus": 0.2},
        {"name": "link_c", "nominal": 30.0, "plus": 0.3, "minus": 0.3},
    ]
    result = analyze_tolerance_stackup(contributors)

    assert result["status"] == "ok"
    assert result["nominal_total"] == 60.0
    assert result["worst_case"]["min"] == pytest.approx(59.4)
    assert result["worst_case"]["max"] == pytest.approx(60.6)
    assert result["worst_case"]["plus_total"] == pytest.approx(0.6)
    assert result["worst_case"]["minus_total"] == pytest.approx(0.6)

    expected_sigma = math.sqrt(
        ((0.2) / 6) ** 2 + ((0.4) / 6) ** 2 + ((0.6) / 6) ** 2
    )
    assert result["rss"]["sigma"] == pytest.approx(expected_sigma)
    assert result["rss"]["min"] == pytest.approx(60.0 - 1.96 * expected_sigma)
    assert result["rss"]["max"] == pytest.approx(60.0 + 1.96 * expected_sigma)

    # Top controlling contributor is link_c by both methods.
    assert result["controlling_contributors"]["worst_case"][0]["name"] == "link_c"
    assert result["controlling_contributors"]["rss"][0]["name"] == "link_c"
    assert len(result["assumptions"]) >= 3


def test_asymmetric_minus_is_treated_as_magnitude() -> None:
    contributors = [
        {"name": "hole", "nominal": 10.0, "plus": 0.05, "minus": -0.1},
    ]
    result = analyze_tolerance_stackup(contributors)
    assert result["worst_case"]["min"] == pytest.approx(9.9)
    assert result["worst_case"]["max"] == pytest.approx(10.05)


def test_uniform_distribution_still_uses_three_sigma_variance() -> None:
    contributors = [
        {"name": "u", "nominal": 0.0, "plus": 0.3, "minus": 0.3, "distribution": "uniform"},
    ]
    result = analyze_tolerance_stackup(contributors)
    # We still convert stated band to +/-3-sigma variance for RSS comparison.
    assert result["rss"]["sigma"] == pytest.approx(0.6 / 6)
    assert result["contributors"][0]["distribution"] == "uniform"


def test_confidence_level_99_percent() -> None:
    contributors = [
        {"name": "x", "nominal": 0.0, "plus": 0.3, "minus": 0.3},
    ]
    result = analyze_tolerance_stackup(contributors, confidence_level=0.99)
    sigma = 0.6 / 6
    assert result["rss"]["z"] == pytest.approx(2.576)
    assert result["rss"]["max"] == pytest.approx(sigma * 2.576)


def test_empty_contributors_returns_error() -> None:
    result = analyze_tolerance_stackup([])
    assert result["status"] == "error"
    assert result["code"] == "bad_input"


def test_bad_contributor_value_returns_error() -> None:
    result = analyze_tolerance_stackup([{"name": "bad", "nominal": "oops", "plus": 0.1, "minus": 0.1}])
    assert result["status"] == "error"
    assert result["code"] == "bad_input"

