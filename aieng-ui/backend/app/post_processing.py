"""Post-processing intelligence: interpret simulation results against design targets.

Compares raw solver metrics (von_mises_max_mpa, displacement_max_mm) against the
project's design targets and produces a structured verdict with engineering suggestions.
Also computes the static Factor-of-Safety (FoS = yield_strength / σ_max).

Pure functions — no I/O, no external calls.
"""
from __future__ import annotations

from typing import Any


# ── Material yield strength catalog (MPa) ─────────────────────────────────────

_MATERIAL_YIELD_MPa: dict[str, float] = {
    # Aluminium alloys
    "al6061":     276.0,
    "al6061_t6":  276.0,
    "al6061-t6":  276.0,
    "al7075":     503.0,
    "al7075_t6":  503.0,
    "al7075-t6":  503.0,
    # Steel grades
    "steel_1045": 530.0,
    "steel-1045": 530.0,
    "1045":       530.0,
    "steel_316l": 290.0,
    "steel-316l": 290.0,
    "316l":       290.0,
    "steel":      250.0,   # generic mild steel fallback
    # Titanium
    "ti_6al_4v":  880.0,
    "ti-6al-4v":  880.0,
    "ti6al4v":    880.0,
    "titanium":   880.0,
    # Cast iron
    "cast_iron_grey": 200.0,
    "cast-iron-grey": 200.0,
    "grey_cast_iron": 200.0,
    "castiron":       200.0,
    # Polymers
    "nylon_pa66": 85.0,
    "nylon-pa66": 85.0,
    "nylon":      85.0,
    "petg_cf":    60.0,
    "petg-cf":    60.0,
    "petg":       50.0,
}


def _lookup_yield_strength(material_name: str) -> float | None:
    """Return yield strength in MPa for a known material, or None."""
    key = material_name.lower().replace(" ", "_")
    # Exact match first
    if key in _MATERIAL_YIELD_MPa:
        return _MATERIAL_YIELD_MPa[key]
    # Substring search (longest key that appears in the material name wins)
    matches = [(k, v) for k, v in _MATERIAL_YIELD_MPa.items() if k in key]
    if matches:
        return max(matches, key=lambda x: len(x[0]))[1]
    return None


def compute_fos(
    von_mises_max_mpa: float | None,
    material_name: str,
) -> dict[str, Any]:
    """Compute static Factor-of-Safety = yield_strength / σ_max.

    Returns:
        {
            "fos": float | None,
            "yield_strength_mpa": float | None,
            "rating": "safe" | "marginal" | "critical" | "unknown",
        }
    """
    yield_mpa = _lookup_yield_strength(material_name)
    if von_mises_max_mpa is None or von_mises_max_mpa <= 0 or yield_mpa is None:
        return {"fos": None, "yield_strength_mpa": yield_mpa, "rating": "unknown"}

    fos = yield_mpa / von_mises_max_mpa
    if fos >= 2.0:
        rating = "safe"
    elif fos >= 1.0:
        rating = "marginal"
    else:
        rating = "critical"

    return {"fos": round(fos, 2), "yield_strength_mpa": yield_mpa, "rating": rating}


# ── Metric name → kind mapping ────────────────────────────────────────────────

_STRESS_KEYWORDS = frozenset({
    "stress", "von_mises", "mises", "sigma", "sigma_max", "s_max",
    "von_mises_stress", "von_mises_max", "max_stress",
})
_DISP_KEYWORDS = frozenset({
    "displacement", "deflection", "deformation", "delta", "u_max",
    "d_max", "max_displacement", "max_deflection",
})


def _match_metric(metric_name: str) -> str | None:
    """Map a design-target metric name to 'stress' or 'displacement', or None."""
    lower = metric_name.lower().replace("-", "_").replace(" ", "_")
    for kw in _STRESS_KEYWORDS:
        if kw in lower:
            return "stress"
    for kw in _DISP_KEYWORDS:
        if kw in lower:
            return "displacement"
    return None


# ── Scalar comparison ─────────────────────────────────────────────────────────

def _compare(operator: str, actual: float, target: dict[str, Any]) -> str:
    """Return 'pass', 'fail', 'not_evaluated', or 'unknown'."""
    value = target.get("value") if target.get("value") is not None else target.get("threshold")
    if operator == "within_range":
        lo = target.get("threshold_min")
        hi = target.get("threshold_max")
        if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
            return "unknown"
        return "pass" if float(lo) <= actual <= float(hi) else "fail"
    if operator in {"preserve", "priority"}:
        return "not_evaluated"
    if not isinstance(value, (int, float)):
        return "unknown"
    v = float(value)
    if operator == "<=":
        return "pass" if actual <= v else "fail"
    if operator == "<":
        return "pass" if actual < v else "fail"
    if operator == ">=":
        return "pass" if actual >= v else "fail"
    if operator == ">":
        return "pass" if actual > v else "fail"
    if operator == "==":
        return "pass" if actual == v else "fail"
    return "unknown"


# ── FoS advisory ─────────────────────────────────────────────────────────────

# Canonical material names and yield strengths for advisory output.
# Ordered from lowest to highest yield (best-fit alternatives shown first).
_ADVISORY_MATERIALS: list[tuple[str, float]] = [
    ("Cast-Iron-Grey", 200.0),
    ("Nylon-PA66",      85.0),
    ("PETG-CF",         60.0),
    ("Steel-316L",     290.0),
    ("Al6061-T6",      276.0),
    ("Al7075-T6",      503.0),
    ("Steel-1045",     530.0),
    ("Ti-6Al-4V",      880.0),
]


def _fos_advisory(
    rating: str,
    material_name: str,
    von_mises_max_mpa: float,
    fos_value: float,
) -> list[str]:
    """Generate specific, number-rich FoS advisory messages for marginal/critical ratings.

    Returns an empty list for safe/unknown ratings or when input data is insufficient.
    Each string in the return list is one standalone advisory sentence.
    """
    if rating not in ("marginal", "critical") or von_mises_max_mpa <= 0:
        return []

    TARGET_FOS = 2.0
    current_yield = _lookup_yield_strength(material_name)
    advisory: list[str] = []

    # ── Line 1: state the problem ─────────────────────────────────────────────
    if current_yield:
        advisory.append(
            f"FoS {fos_value:.2f} ({rating}) — σ_max {von_mises_max_mpa:.1f} MPa "
            f"vs yield {current_yield:.0f} MPa ({material_name}). "
            f"Target FoS ≥ {TARGET_FOS:.0f} requires σ_max ≤ {current_yield / TARGET_FOS:.0f} MPa."
        )
    else:
        advisory.append(
            f"FoS {fos_value:.2f} ({rating}) — σ_max {von_mises_max_mpa:.1f} MPa. "
            f"Target FoS ≥ {TARGET_FOS:.0f}."
        )

    # ── Line 2: material alternatives that achieve FoS ≥ 2.0 ─────────────────
    norm_current = material_name.lower().replace(" ", "_").replace("-", "_")
    alternatives = []
    for mat_name, yield_mpa in _ADVISORY_MATERIALS:
        norm_cand = mat_name.lower().replace(" ", "_").replace("-", "_")
        # Skip current material (by name or yield match)
        if norm_cand in norm_current or norm_current in norm_cand:
            continue
        if current_yield and abs(yield_mpa - current_yield) < 1.0:
            continue
        proj_fos = yield_mpa / von_mises_max_mpa
        if proj_fos >= TARGET_FOS:
            alternatives.append((mat_name, yield_mpa, proj_fos))

    if alternatives:
        # Sort by projected FoS ascending so the "just enough" option comes first
        alternatives.sort(key=lambda x: x[2])
        parts = [
            f"{name} (yield {y:.0f} MPa → FoS {f:.2f})"
            for name, y, f in alternatives[:3]
        ]
        advisory.append("Material alternatives that achieve FoS ≥ 2.0: " + "; ".join(parts) + ".")

    # ── Line 3: load reduction with current material ──────────────────────────
    if current_yield:
        safe_stress = current_yield / TARGET_FOS
        if safe_stress < von_mises_max_mpa:
            reduction_pct = round((1.0 - safe_stress / von_mises_max_mpa) * 100)
            advisory.append(
                f"Keep {material_name}: reduce applied load by ≈{reduction_pct}% "
                f"to bring σ_max to {safe_stress:.0f} MPa (FoS = {TARGET_FOS:.0f})."
            )

    # ── Line 4: geometry tip ──────────────────────────────────────────────────
    if rating == "critical":
        advisory.append(
            "Part is likely yielding under current load — increase wall thickness, "
            "add ribs, or move the load attachment point before manufacturing."
        )
    else:
        advisory.append(
            "Increase cross-section at the peak-stress region to reduce σ_max "
            "without changing the overall geometry."
        )

    return advisory


# ── Engineering suggestions ───────────────────────────────────────────────────

def _stress_suggestions(actual: float, threshold: float, material: str) -> list[str]:
    ratio = actual / threshold if threshold > 0 else 1.0
    suggestions: list[str] = []
    if ratio > 2.0:
        suggestions.append(
            f"σ_max is {ratio:.1f}× over the limit — significantly redesign the load path or add a gusset plate"
        )
    else:
        pct = max(1, int((ratio - 1.0) * 100))
        suggestions.append(
            f"Increase minimum cross-section area by ~{pct}% to bring σ_max within the target"
        )
    mat_lower = material.lower()
    if "al" in mat_lower or "aluminum" in mat_lower or "aluminium" in mat_lower:
        suggestions.append(
            "Consider Steel-1045 (yield ~530 MPa) or Ti-6Al-4V (yield ~880 MPa) for a higher strength margin"
        )
    else:
        suggestions.append(
            "Redistribute load over a larger contact area to reduce peak stress concentration"
        )
    return suggestions


def _disp_suggestions(actual: float, threshold: float, material: str) -> list[str]:
    ratio = actual / threshold if threshold > 0 else 1.0
    suggestions: list[str] = []
    if ratio > 2.0:
        suggestions.append(
            "Add stiffening ribs or gussets — displacement exceeds 2× the limit"
        )
    else:
        pct = max(1, int((ratio - 1.0) * 100))
        suggestions.append(
            f"Increase section depth or moment of inertia by ~{pct}% to reduce peak displacement"
        )
    mat_lower = material.lower()
    if "al" in mat_lower or "aluminum" in mat_lower or "aluminium" in mat_lower:
        suggestions.append(
            "Steel has ~3× the Young's modulus of aluminum — switching material would significantly reduce stiffness-driven displacement"
        )
    else:
        suggestions.append(
            "Consider adding a second support point to shorten the effective span"
        )
    return suggestions


# ── Main entry point ──────────────────────────────────────────────────────────

def interpret_results(
    von_mises_max_mpa: float | None,
    displacement_max_mm: float | None,
    design_targets: list[dict[str, Any]],
    material_name: str = "",
) -> dict[str, Any]:
    """Compare solver metrics against design targets; emit verdict + engineering suggestions.

    Returns:
        {
            "overall": "pass" | "fail" | "partial" | "no_targets" | "unknown",
            "pass_count": int,
            "fail_count": int,
            "items": [{"target_id", "label", "metric", "status",
                       "actual_value", "threshold", "operator", "unit"}, ...],
            "suggestions": [str, ...],
            "fos": {"fos", "yield_strength_mpa", "rating"},
        }
    """
    fos_result = compute_fos(von_mises_max_mpa, material_name)

    if not design_targets:
        return {
            "overall": "no_targets",
            "pass_count": 0,
            "fail_count": 0,
            "items": [],
            "suggestions": [
                "No design targets defined — add targets to task/design_targets.yaml to enable pass/fail assessment"
            ],
            "fos": fos_result,
            "fos_advisory": _fos_advisory(
                fos_result["rating"],
                material_name,
                von_mises_max_mpa or 0.0,
                fos_result["fos"] or 0.0,
            ),
        }

    items: list[dict[str, Any]] = []
    suggestions: list[str] = []

    for t in design_targets:
        if not isinstance(t, dict):
            continue
        metric = t.get("metric") or t.get("target_type") or ""
        kind = _match_metric(str(metric))
        operator = str(t.get("operator") or t.get("comparator") or "")
        threshold = t.get("value") if t.get("value") is not None else t.get("threshold")
        unit = str(t.get("unit") or "")
        label = str(t.get("label") or metric)
        tid = str(t.get("target_id") or t.get("id") or metric)

        actual_value: float | None = None
        if kind == "stress" and von_mises_max_mpa is not None:
            actual_value = von_mises_max_mpa
        elif kind == "displacement" and displacement_max_mm is not None:
            actual_value = displacement_max_mm

        if actual_value is None:
            status = "unknown"
        else:
            status = _compare(operator, actual_value, t)

        items.append({
            "target_id": tid,
            "label": label,
            "metric": metric,
            "status": status,
            "actual_value": actual_value,
            "threshold": threshold,
            "operator": operator,
            "unit": unit,
        })

        if status == "fail" and actual_value is not None and isinstance(threshold, (int, float)):
            if kind == "stress":
                suggestions.extend(_stress_suggestions(actual_value, float(threshold), material_name))
            elif kind == "displacement":
                suggestions.extend(_disp_suggestions(actual_value, float(threshold), material_name))

    pass_count = sum(1 for i in items if i["status"] == "pass")
    fail_count = sum(1 for i in items if i["status"] == "fail")
    unknown_count = sum(1 for i in items if i["status"] in {"unknown", "not_evaluated"})

    if fail_count > 0 and pass_count > 0:
        overall = "partial"
    elif fail_count > 0:
        overall = "fail"
    elif pass_count > 0 and unknown_count == 0:
        overall = "pass"
    elif pass_count > 0:
        overall = "partial"
    else:
        overall = "unknown"

    # Deduplicate suggestions preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    return {
        "overall": overall,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "items": items,
        "suggestions": deduped,
        "fos": fos_result,
        "fos_advisory": _fos_advisory(
            fos_result["rating"],
            material_name,
            von_mises_max_mpa or 0.0,
            fos_result["fos"] or 0.0,
        ),
    }
