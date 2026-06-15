"""Tests for the ASME V&V-20 mesh-convergence analyzer.

Synthetic series follow phi(h) = phi_ext + C*h^p, so the apparent order, the
Richardson-extrapolated asymptote, and the GCI are known in closed form and can be
asserted exactly.
"""
from __future__ import annotations

import pytest

from aieng.converters.mesh_convergence import analyze_mesh_convergence


def _levels(pairs):
    # pairs: list of (size, value)
    return [{"size": s, "value": v} for s, v in pairs]


def test_not_converged_coarse_series_recovers_order_and_asymptote() -> None:
    # phi_ext=10, C=1, p=2 at h=[1,2,4] -> phi=[11,14,26]
    report = analyze_mesh_convergence(_levels([(1.0, 11.0), (2.0, 14.0), (4.0, 26.0)]),
                                      metric_name="max_von_mises_stress")
    assert report["apparent_order"] == pytest.approx(2.0, rel=1e-3)
    assert report["extrapolated_value"] == pytest.approx(10.0, rel=1e-3)
    # GCI_fine = 1.25 * (3/11) / (2^2 - 1) = 11.36%
    assert report["gci_fine_percent"] == pytest.approx(11.3636, rel=1e-3)
    assert report["converged"] is False
    assert report["verdict"] == "not_converged_refine_further"


def test_converged_fine_series_is_in_asymptotic_range() -> None:
    # Same p=2, phi_ext=10, but finer h=[0.25,0.5,1.0] -> near asymptote
    report = analyze_mesh_convergence(_levels([(0.25, 10.0625), (0.5, 10.25), (1.0, 11.0)]))
    assert report["apparent_order"] == pytest.approx(2.0, rel=1e-3)
    assert report["extrapolated_value"] == pytest.approx(10.0, rel=1e-3)
    assert report["gci_fine_percent"] == pytest.approx(0.7764, rel=1e-2)
    assert report["converged"] is True
    assert report["verdict"] == "converged"
    assert report["asymptotic_range"] is True  # GCI ratio ≈ 1


def test_two_grids_reports_relative_change_only() -> None:
    report = analyze_mesh_convergence(_levels([(1.0, 10.1), (2.0, 10.3)]))
    assert report["verdict"] == "two_grid_relative_change_only"
    assert report["apparent_order"] is None
    assert report["gci_fine_percent"] is None
    assert report["relative_change_finest_pair_percent"] == pytest.approx(
        abs((10.3 - 10.1) / 10.1) * 100.0, rel=1e-3
    )


def test_insufficient_grids() -> None:
    assert analyze_mesh_convergence(_levels([(1.0, 10.0)]))["verdict"] == "insufficient_grids"
    assert analyze_mesh_convergence([])["verdict"] == "insufficient_grids"


def test_flat_series_is_converged_flat() -> None:
    report = analyze_mesh_convergence(_levels([(1.0, 10.0), (2.0, 10.0), (4.0, 10.0)]))
    assert report["verdict"] == "converged_flat"
    assert report["converged"] is True


def test_oscillatory_series_flagged_non_monotonic() -> None:
    # sign change in successive deltas -> oscillatory, not in asymptotic range
    report = analyze_mesh_convergence(_levels([(1.0, 10.1), (2.0, 9.9), (4.0, 10.3)]))
    assert report["non_monotonic"] is True
    assert report["converged"] is False
    assert report["verdict"] == "oscillatory_not_converged"


def test_drops_failed_values_and_keeps_node_count() -> None:
    levels = [
        {"size": 1.0, "value": 11.0, "node_count": 9000},
        {"size": 2.0, "value": None},          # failed solve — dropped
        {"size": 4.0, "value": 26.0, "node_count": 1200},
    ]
    report = analyze_mesh_convergence(levels)
    # only two usable grids remain
    assert report["level_count"] == 2
    assert report["verdict"] == "two_grid_relative_change_only"
    assert report["levels"][0]["node_count"] == 9000


def test_unequal_refinement_ratios_still_estimates_positive_order() -> None:
    # h = [1, 1.5, 3] (r21=1.5, r32=2), phi = 10 + h^2
    report = analyze_mesh_convergence(_levels([(1.0, 11.0), (1.5, 12.25), (3.0, 19.0)]))
    assert report["apparent_order"] is not None
    assert report["apparent_order"] > 0
    assert report["extrapolated_value"] == pytest.approx(10.0, abs=0.5)


def test_honesty_block_always_present() -> None:
    report = analyze_mesh_convergence(_levels([(1.0, 11.0), (2.0, 14.0), (4.0, 26.0)]))
    h = report["honesty"]
    assert h["is_discretization_uncertainty_only"] is True
    assert h["model_validated"] is False
    assert h["production_ready"] is False
