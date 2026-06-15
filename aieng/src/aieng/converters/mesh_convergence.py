"""Mesh-convergence analysis — ASME V&V-20 Richardson extrapolation + GCI.

After a static solve answers *"what is the stress/deflection?"*, the next
engineering question is *"can I trust it, or is it mesh noise?"* This module is the
deterministic answer: given the same metric solved on ≥3 progressively finer
meshes, it estimates the apparent order of convergence, the mesh-independent
(extrapolated) value, and the **Grid Convergence Index (GCI)** — the standard
ASME V&V-20 / Roache measure of discretization uncertainty — and returns an honest
converged / not-converged verdict.

Honesty boundary: the GCI is a *numerical discretization* uncertainty estimate for
THIS metric on THIS geometry and refinement sequence. It is not a proof of model
validity, not a claim about solver/material/boundary-condition correctness, and not
a certification. Three grids in the asymptotic range are assumed; the report flags
when that assumption looks violated (non-monotonic / out-of-range order).

Pure and dependency-free.
"""
from __future__ import annotations

import math
from typing import Any

# ASME V&V-20 recommends a 1.25 factor of safety for GCI with ≥3 grids
# (1.5 for only 2 grids / less-careful studies).
DEFAULT_GCI_SAFETY_FACTOR = 1.25
DEFAULT_CONVERGED_GCI_PERCENT = 5.0


def _clean_levels(levels: list[dict[str, Any]]) -> list[dict[str, float]]:
    """Keep levels with a positive representative size and a finite value; sort
    FINE→COARSE (ascending size). Deduplicate identical sizes (keep first)."""
    out: list[dict[str, float]] = []
    seen_sizes: set[float] = set()
    for lvl in levels or []:
        if not isinstance(lvl, dict):
            continue
        size = lvl.get("size")
        value = lvl.get("value")
        if not isinstance(size, (int, float)) or isinstance(size, bool) or size <= 0:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if not math.isfinite(float(size)) or not math.isfinite(float(value)):
            continue
        if float(size) in seen_sizes:
            continue
        seen_sizes.add(float(size))
        entry = {"size": float(size), "value": float(value)}
        if isinstance(lvl.get("node_count"), (int, float)) and not isinstance(lvl.get("node_count"), bool):
            entry["node_count"] = float(lvl["node_count"])
        out.append(entry)
    out.sort(key=lambda e: e["size"])  # ascending size = fine → coarse
    return out


def analyze_mesh_convergence(
    levels: list[dict[str, Any]],
    *,
    metric_name: str | None = None,
    safety_factor: float = DEFAULT_GCI_SAFETY_FACTOR,
    converged_gci_percent: float = DEFAULT_CONVERGED_GCI_PERCENT,
) -> dict[str, Any]:
    """Estimate convergence of ONE metric across refined meshes (ASME V&V-20 GCI).

    Args:
        levels: per-mesh results — ``{size, value, [node_count]}`` where ``size`` is
            the representative element size *h* (smaller = finer) and ``value`` is
            the metric at that mesh. Failed/missing values are dropped.
        metric_name: echoed into the report.
        safety_factor: GCI factor of safety (default 1.25 for ≥3 grids).
        converged_gci_percent: GCI threshold (%) below which the finest mesh is
            deemed converged (default 5%).

    Returns:
        A report with ``apparent_order``, ``extrapolated_value``,
        ``gci_fine_percent`` / ``gci_coarse_percent``, ``asymptotic_range``,
        ``converged`` + ``verdict``, per-pair deltas, and an honesty block. With
        <3 usable grids it degrades to ``indeterminate`` (2 grids → relative change
        only) rather than guessing.
    """
    clean = _clean_levels(levels)
    base: dict[str, Any] = {
        "metric": metric_name,
        "levels": clean,
        "level_count": len(clean),
        "safety_factor": safety_factor,
        "converged_gci_percent": converged_gci_percent,
        "honesty": {
            "is_discretization_uncertainty_only": True,
            "model_validated": False,
            "production_ready": False,
            "note": (
                "GCI estimates numerical discretization uncertainty for this metric "
                "on this geometry/refinement only — not model validity or certification."
            ),
        },
    }

    if len(clean) < 2:
        base.update({
            "converged": None,
            "verdict": "insufficient_grids",
            "message": "need at least 2 (ideally 3) refined meshes to assess convergence",
        })
        return base

    # Use the THREE finest grids for the GCI triple (or the only two available).
    f = clean[0]   # finest
    m = clean[1]   # medium
    phi_f, phi_m = f["value"], m["value"]
    r_mf = m["size"] / f["size"] if f["size"] > 0 else float("nan")  # refinement ratio ≥ 1

    # Pairwise relative change between the two finest grids (always available).
    denom_f = abs(phi_f) if phi_f != 0 else None
    rel_change_fine = (abs(phi_m - phi_f) / denom_f) if denom_f else None
    base["relative_change_finest_pair_percent"] = (
        round(rel_change_fine * 100.0, 4) if rel_change_fine is not None else None
    )
    base["refinement_ratio_finest_pair"] = round(r_mf, 4) if math.isfinite(r_mf) else None

    if len(clean) < 3:
        # Two grids: report the relative change; GCI's order estimate needs three.
        conv = rel_change_fine is not None and rel_change_fine * 100.0 <= converged_gci_percent
        base.update({
            "apparent_order": None,
            "extrapolated_value": None,
            "gci_fine_percent": None,
            "converged": bool(conv) if rel_change_fine is not None else None,
            "verdict": "two_grid_relative_change_only",
            "message": (
                "only two grids — reporting relative change; add a third (finer) mesh "
                "for a Grid Convergence Index and an order-of-accuracy estimate"
            ),
        })
        return base

    c = clean[2]  # coarse
    phi_c = c["value"]
    r_cm = c["size"] / m["size"] if m["size"] > 0 else float("nan")

    eps_mf = phi_m - phi_f   # medium − fine
    eps_cm = phi_c - phi_m   # coarse − medium

    pairs = [
        {"pair": "fine_medium", "delta": round(eps_mf, 6), "r": round(r_mf, 4)},
        {"pair": "medium_coarse", "delta": round(eps_cm, 6), "r": round(r_cm, 4)},
    ]
    base["pairs"] = pairs

    # Oscillatory / converged-flat handling: if either difference is ~0 the order
    # estimate is undefined. Near-flat finest pair ⇒ effectively converged.
    if abs(eps_mf) < 1e-12 or abs(eps_cm) < 1e-12:
        converged = abs(eps_mf) < 1e-9 or (rel_change_fine is not None and rel_change_fine * 100.0 <= converged_gci_percent)
        base.update({
            "apparent_order": None,
            "extrapolated_value": round(phi_f, 6),
            "gci_fine_percent": 0.0 if abs(eps_mf) < 1e-12 else None,
            "asymptotic_range": None,
            "converged": bool(converged),
            "verdict": "converged_flat" if converged else "indeterminate_flat",
            "message": "metric change between grids is negligible",
        })
        return base

    ratio = eps_cm / eps_mf
    non_monotonic = ratio < 0  # sign change ⇒ oscillatory convergence

    # Apparent order p. For constant refinement ratio r, p = ln|eps_cm/eps_mf| / ln(r).
    # For unequal ratios, solve the V&V-20 fixed-point including q(p); we keep the
    # equal-ratio closed form (the common halving case) and note unequal ratios.
    p: float | None = None
    if math.isfinite(r_mf) and r_mf > 1.0:
        try:
            if abs(r_cm - r_mf) < 1e-6:
                p = math.log(abs(ratio)) / math.log(r_mf)
            else:
                # Unequal ratios: iterate p = (1/ln r21)|ln|eps32/eps21| + q(p)|.
                s = 1.0 if ratio > 0 else -1.0
                p_iter = math.log(abs(ratio)) / math.log(r_mf)
                for _ in range(50):
                    q = math.log((r_mf ** p_iter - s) / (r_cm ** p_iter - s))
                    p_next = abs(math.log(abs(ratio)) + q) / math.log(r_mf)
                    if abs(p_next - p_iter) < 1e-8:
                        p_iter = p_next
                        break
                    p_iter = p_next
                p = p_iter
        except (ValueError, ZeroDivisionError):
            p = None

    extrapolated: float | None = None
    gci_fine: float | None = None
    gci_coarse: float | None = None
    asymptotic_ratio: float | None = None

    if p is not None and math.isfinite(p) and r_mf > 1.0:
        rp = r_mf ** p
        if abs(rp - 1.0) > 1e-9:
            # Fine-grid Richardson extrapolation (Roache): phi_ext = phi_f + (phi_f − phi_m)/(r^p − 1).
            extrapolated = phi_f + (phi_f - phi_m) / (rp - 1.0)
            e_a_fine = abs((phi_f - phi_m) / phi_f) if phi_f != 0 else None
            if e_a_fine is not None:
                gci_fine = safety_factor * e_a_fine / (rp - 1.0)
            rp_cm = r_cm ** p
            if abs(rp_cm - 1.0) > 1e-9 and phi_m != 0:
                e_a_coarse = abs((phi_m - phi_c) / phi_m)
                gci_coarse = safety_factor * e_a_coarse / (rp_cm - 1.0)
            # Asymptotic-range check: GCI_coarse / (r^p · GCI_fine) ≈ 1.
            if gci_fine and gci_coarse and gci_fine > 0:
                asymptotic_ratio = gci_coarse / (rp * gci_fine)

    gci_fine_pct = round(gci_fine * 100.0, 4) if gci_fine is not None else None
    gci_coarse_pct = round(gci_coarse * 100.0, 4) if gci_coarse is not None else None
    in_asymptotic = (
        asymptotic_ratio is not None and abs(asymptotic_ratio - 1.0) <= 0.10
    )

    if gci_fine_pct is None:
        verdict = "indeterminate"
        converged = None
    elif gci_fine_pct <= converged_gci_percent and not non_monotonic:
        verdict = "converged"
        converged = True
    elif non_monotonic:
        verdict = "oscillatory_not_converged"
        converged = False
    else:
        verdict = "not_converged_refine_further"
        converged = False

    base.update({
        "apparent_order": round(p, 4) if p is not None and math.isfinite(p) else None,
        "extrapolated_value": round(extrapolated, 6) if extrapolated is not None else None,
        "gci_fine_percent": gci_fine_pct,
        "gci_coarse_percent": gci_coarse_pct,
        "asymptotic_range": in_asymptotic,
        "asymptotic_ratio": round(asymptotic_ratio, 4) if asymptotic_ratio is not None else None,
        "non_monotonic": non_monotonic,
        "converged": converged,
        "verdict": verdict,
        "message": _verdict_message(verdict, gci_fine_pct, converged_gci_percent),
    })
    return base


def _verdict_message(verdict: str, gci_fine_pct: float | None, threshold: float) -> str:
    if verdict == "converged":
        return (
            f"finest-grid GCI {gci_fine_pct}% ≤ {threshold}% — the metric is "
            "mesh-converged within the discretization-uncertainty band"
        )
    if verdict == "not_converged_refine_further":
        return (
            f"finest-grid GCI {gci_fine_pct}% > {threshold}% — refine the mesh "
            "further; the reported value still carries this discretization uncertainty"
        )
    if verdict == "oscillatory_not_converged":
        return "metric changes non-monotonically with refinement — not in the asymptotic range; refine/inspect"
    return "could not estimate a Grid Convergence Index from these grids"
