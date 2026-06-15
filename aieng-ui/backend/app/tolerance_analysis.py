"""Deterministic 1D tolerance stack-up analysis.

Worst-case arithmetic and statistical RSS computations are intentionally simple,
read-only, and solver-free. They are meant to complement editable-parameter
design reviews, not to replace GD&T analysis.
"""

from __future__ import annotations

import math
from typing import Any


def _z_for_confidence(level: float) -> float:
    """Return a two-sided normal z-score for the given confidence level.

    Uses a small lookup table for common engineering levels; interpolates
    linearly between bracketing levels otherwise.
    """
    levels = {
        0.90: 1.645,
        0.95: 1.960,
        0.99: 2.576,
        0.999: 3.291,
    }
    if level in levels:
        return levels[level]
    sorted_levels = sorted(levels.items())
    if level <= sorted_levels[0][0]:
        return sorted_levels[0][1]
    if level >= sorted_levels[-1][0]:
        return sorted_levels[-1][1]
    for (lo, z_lo), (hi, z_hi) in zip(sorted_levels, sorted_levels[1:]):
        if lo <= level <= hi:
            frac = (level - lo) / (hi - lo)
            return z_lo + frac * (z_hi - z_lo)
    return 1.96


def analyze_tolerance_stackup(
    contributors: list[dict[str, Any]],
    *,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Compute 1D worst-case and RSS tolerance stack-up for a dimension chain.

    Each contributor is a dict with:
      - ``name`` (str): human-readable label.
      - ``nominal`` (float): central dimension value.
      - ``plus`` (float): upper deviation from nominal (>= 0).
      - ``minus`` (float): lower deviation from nominal. May be negative or a
        positive number that is subtracted; we treat ``abs(minus)`` as the
        lower-side tolerance band.
      - ``distribution`` (str, optional): ``"normal"`` (default) or ``"uniform"``.
        Currently used only for RSS sigma interpretation notes; both are
        converted to an equivalent 1-sigma of ``plus/3`` / ``abs(minus)/3``.

    Returns a dict with:
      - ``status``, ``nominal_total``
      - ``worst_case``: ``min``, ``max``, ``plus_total``, ``minus_total``
      - ``rss``: ``sigma``, ``min``, ``max`` at the requested confidence,
        ``confidence_level``
      - ``contributors``: enriched list with ``upper``, ``lower``,
        ``tolerance_band``, ``variance``
      - ``controlling_contributors``: top drivers for worst-case and RSS.
      - ``assumptions``: honesty notes about independence and distributions.
    """
    if not contributors:
        return {
            "status": "error",
            "code": "bad_input",
            "message": "contributors chain must contain at least one contributor.",
        }

    normalized: list[dict[str, Any]] = []
    for i, c in enumerate(contributors):
        try:
            nominal = float(c["nominal"])
            plus = float(c.get("plus", 0.0))
            minus = float(c.get("minus", 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "status": "error",
                "code": "bad_input",
                "message": f"contributor {i}: {exc}",
            }
        name = str(c.get("name") or f"contrib_{i}")
        distribution = str(c.get("distribution") or "normal").lower()
        if distribution not in {"normal", "uniform"}:
            distribution = "normal"

        # Tolerance bands are non-negative deviations from nominal.
        upper = nominal + plus
        lower = nominal - abs(minus)
        plus_tol = plus
        minus_tol = abs(minus)
        # For RSS, assume the stated tolerance spans +/- 3 sigma.
        sigma = (plus_tol + minus_tol) / 6.0
        variance = sigma * sigma

        normalized.append(
            {
                "index": i,
                "name": name,
                "nominal": nominal,
                "plus": plus_tol,
                "minus": minus_tol,
                "distribution": distribution,
                "upper": upper,
                "lower": lower,
                "tolerance_band": plus_tol + minus_tol,
                "sigma": sigma,
                "variance": variance,
            }
        )

    nominal_total = sum(c["nominal"] for c in normalized)
    plus_total = sum(c["plus"] for c in normalized)
    minus_total = sum(c["minus"] for c in normalized)

    worst_case_max = nominal_total + plus_total
    worst_case_min = nominal_total - minus_total

    rss_sigma = math.sqrt(sum(c["variance"] for c in normalized))
    z = _z_for_confidence(confidence_level)
    rss_max = nominal_total + z * rss_sigma
    rss_min = nominal_total - z * rss_sigma

    # Controlling contributors: largest individual effects.
    by_worst_case = sorted(
        normalized, key=lambda c: c["plus"] + c["minus"], reverse=True
    )
    by_rss = sorted(normalized, key=lambda c: c["variance"], reverse=True)

    return {
        "status": "ok",
        "nominal_total": round(nominal_total, 6),
        "worst_case": {
            "min": round(worst_case_min, 6),
            "max": round(worst_case_max, 6),
            "plus_total": round(plus_total, 6),
            "minus_total": round(minus_total, 6),
        },
        "rss": {
            "sigma": round(rss_sigma, 6),
            "confidence_level": confidence_level,
            "z": round(z, 3),
            "min": round(rss_min, 6),
            "max": round(rss_max, 6),
        },
        "contributors": [
            {
                "name": c["name"],
                "nominal": c["nominal"],
                "plus": c["plus"],
                "minus": c["minus"],
                "distribution": c["distribution"],
                "upper": round(c["upper"], 6),
                "lower": round(c["lower"], 6),
                "tolerance_band": round(c["tolerance_band"], 6),
            }
            for c in normalized
        ],
        "controlling_contributors": {
            "worst_case": [
                {"name": c["name"], "tolerance_band": round(c["tolerance_band"], 6)}
                for c in by_worst_case[:3]
            ],
            "rss": [
                {"name": c["name"], "variance": round(c["variance"], 6)}
                for c in by_rss[:3]
            ],
        },
        "assumptions": [
            "1D linear stack-up: all contributors are treated as signed scalar deviations along a single dimension.",
            "Worst-case assumes all tolerances accumulate in the same direction simultaneously.",
            "RSS assumes contributors are independent; covariance and geometric correlations are ignored.",
            "RSS sigma is derived from +/- 3 sigma coverage of each stated tolerance band.",
            "Normal-distribution confidence band is used for RSS min/max; uniform distributions are noted but still converted to +/- 3-sigma variance for RSS.",
            "This is not a GD&T solver and does not model form, orientation, or location tolerances.",
        ],
    }
