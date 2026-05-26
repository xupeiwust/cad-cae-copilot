"""Tests for post_processing.py — simulation verdict and engineering suggestions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.post_processing import _match_metric, interpret_results, compute_fos, _lookup_yield_strength, _fos_advisory


# ── _match_metric ─────────────────────────────────────────────────────────────

def test_match_metric_von_mises():
    assert _match_metric("von_mises_max_mpa") == "stress"


def test_match_metric_stress_variants():
    for name in ["max_stress", "sigma_max", "Von Mises Stress", "mises"]:
        assert _match_metric(name) == "stress", f"Expected stress for {name!r}"


def test_match_metric_displacement_variants():
    for name in ["max_displacement_mm", "deflection", "u_max", "deformation", "delta"]:
        assert _match_metric(name) == "displacement", f"Expected displacement for {name!r}"


def test_match_metric_unknown():
    assert _match_metric("weight_kg") is None
    assert _match_metric("safety_factor") is None


# ── interpret_results: no targets ─────────────────────────────────────────────

def test_no_design_targets():
    result = interpret_results(300.0, 0.5, [])
    assert result["overall"] == "no_targets"
    assert result["pass_count"] == 0
    assert result["fail_count"] == 0
    assert len(result["suggestions"]) == 1


def test_empty_design_targets_list():
    result = interpret_results(None, None, [])
    assert result["overall"] == "no_targets"


# ── interpret_results: stress pass / fail ─────────────────────────────────────

def test_stress_pass():
    targets = [{"target_id": "s1", "label": "Max stress", "metric": "von_mises_max_mpa",
                "operator": "<=", "value": 300.0, "unit": "MPa"}]
    result = interpret_results(250.0, None, targets)
    assert result["overall"] == "pass"
    assert result["pass_count"] == 1
    assert result["fail_count"] == 0
    assert result["items"][0]["status"] == "pass"
    assert len(result["suggestions"]) == 0


def test_stress_fail():
    targets = [{"target_id": "s1", "label": "Max stress", "metric": "von_mises_max_mpa",
                "operator": "<=", "value": 200.0, "unit": "MPa"}]
    result = interpret_results(350.0, None, targets)
    assert result["overall"] == "fail"
    assert result["fail_count"] == 1
    assert result["items"][0]["status"] == "fail"
    assert result["items"][0]["actual_value"] == 350.0
    assert len(result["suggestions"]) >= 1


def test_stress_fail_with_aluminum_material():
    targets = [{"target_id": "s1", "metric": "von_mises_stress", "operator": "<=",
                "value": 100.0, "unit": "MPa"}]
    result = interpret_results(250.0, None, targets, material_name="Al6061-T6")
    assert result["overall"] == "fail"
    # Should suggest stronger material
    combined = " ".join(result["suggestions"])
    assert "steel" in combined.lower() or "ti-6al" in combined.lower()


# ── interpret_results: displacement pass / fail ───────────────────────────────

def test_displacement_pass():
    targets = [{"target_id": "d1", "label": "Max deflection", "metric": "max_displacement_mm",
                "operator": "<=", "value": 1.0, "unit": "mm"}]
    result = interpret_results(None, 0.3, targets)
    assert result["overall"] == "pass"
    assert result["pass_count"] == 1


def test_displacement_fail():
    targets = [{"target_id": "d1", "metric": "displacement", "operator": "<=",
                "value": 0.5, "unit": "mm"}]
    result = interpret_results(None, 2.1, targets)
    assert result["overall"] == "fail"
    assert len(result["suggestions"]) >= 1


# ── interpret_results: partial (mixed) ───────────────────────────────────────

def test_partial_verdict():
    targets = [
        {"target_id": "s1", "metric": "von_mises_max_mpa", "operator": "<=",
         "value": 300.0, "unit": "MPa"},
        {"target_id": "d1", "metric": "max_displacement_mm", "operator": "<=",
         "value": 0.1, "unit": "mm"},
    ]
    result = interpret_results(250.0, 0.5, targets)
    assert result["overall"] == "partial"
    assert result["pass_count"] == 1
    assert result["fail_count"] == 1


# ── interpret_results: unknown metric (no actual value) ───────────────────────

def test_unknown_when_no_matching_value():
    targets = [{"target_id": "sf1", "metric": "safety_factor", "operator": ">=",
                "value": 2.0}]
    result = interpret_results(300.0, 0.5, targets)
    assert result["items"][0]["status"] == "unknown"
    assert result["overall"] == "unknown"


# ── interpret_results: within_range operator ─────────────────────────────────

def test_within_range_pass():
    targets = [{"target_id": "s1", "metric": "von_mises_max_mpa", "operator": "within_range",
                "threshold_min": 50.0, "threshold_max": 400.0, "value": 400.0}]
    result = interpret_results(200.0, None, targets)
    assert result["items"][0]["status"] == "pass"


def test_within_range_fail():
    targets = [{"target_id": "s1", "metric": "von_mises_max_mpa", "operator": "within_range",
                "threshold_min": 50.0, "threshold_max": 150.0, "value": 150.0}]
    result = interpret_results(300.0, None, targets)
    assert result["items"][0]["status"] == "fail"


# ── interpret_results: deduplication of suggestions ──────────────────────────

def test_suggestions_deduplicated():
    targets = [
        {"target_id": "s1", "metric": "von_mises_max_mpa", "operator": "<=", "value": 100.0},
        {"target_id": "s2", "metric": "max_stress", "operator": "<=", "value": 120.0},
    ]
    result = interpret_results(300.0, None, targets)
    assert len(result["suggestions"]) == len(set(result["suggestions"]))


# ── interpret_results: all fields present ────────────────────────────────────

def test_item_fields_present():
    targets = [{"target_id": "s1", "label": "Stress limit", "metric": "von_mises_max_mpa",
                "operator": "<=", "value": 300.0, "unit": "MPa"}]
    result = interpret_results(200.0, None, targets)
    item = result["items"][0]
    assert item["target_id"] == "s1"
    assert item["label"] == "Stress limit"
    assert item["metric"] == "von_mises_max_mpa"
    assert item["actual_value"] == 200.0
    assert item["threshold"] == 300.0
    assert item["operator"] == "<="
    assert item["unit"] == "MPa"


# ── _lookup_yield_strength ────────────────────────────────────────────────────

def test_yield_lookup_exact():
    assert _lookup_yield_strength("Al6061_T6") == 276.0


def test_yield_lookup_dash_variant():
    assert _lookup_yield_strength("Al6061-T6") == 276.0


def test_yield_lookup_steel():
    assert _lookup_yield_strength("Steel-1045") == 530.0


def test_yield_lookup_titanium():
    assert _lookup_yield_strength("Ti-6Al-4V") == 880.0


def test_yield_lookup_nylon():
    result = _lookup_yield_strength("Nylon-PA66")
    assert result == 85.0


def test_yield_lookup_unknown():
    assert _lookup_yield_strength("CarbonFiber123") is None


# ── compute_fos ───────────────────────────────────────────────────────────────

def test_fos_safe():
    result = compute_fos(100.0, "Al6061-T6")  # 276 / 100 = 2.76 → safe
    assert result["fos"] == 2.76
    assert result["yield_strength_mpa"] == 276.0
    assert result["rating"] == "safe"


def test_fos_marginal():
    result = compute_fos(200.0, "Al6061-T6")  # 276 / 200 = 1.38 → marginal
    assert result["rating"] == "marginal"
    assert result["fos"] is not None
    assert 1.0 <= result["fos"] < 2.0


def test_fos_critical():
    result = compute_fos(400.0, "Al6061-T6")  # 276 / 400 = 0.69 → critical
    assert result["rating"] == "critical"
    assert result["fos"] is not None
    assert result["fos"] < 1.0


def test_fos_unknown_material():
    result = compute_fos(150.0, "ExoticAlloy999")
    assert result["fos"] is None
    assert result["rating"] == "unknown"


def test_fos_none_stress():
    result = compute_fos(None, "Al6061-T6")
    assert result["fos"] is None
    assert result["rating"] == "unknown"


def test_fos_zero_stress():
    result = compute_fos(0.0, "Al6061-T6")
    assert result["fos"] is None


def test_fos_rounding():
    result = compute_fos(100.0, "Steel-1045")  # 530 / 100 = 5.30
    assert result["fos"] == 5.30


# ── interpret_results: fos included in output ─────────────────────────────────

def test_interpret_results_includes_fos():
    targets = [{"target_id": "s1", "metric": "von_mises_max_mpa", "operator": "<=", "value": 300.0}]
    result = interpret_results(100.0, None, targets, "Al6061-T6")
    assert "fos" in result
    assert result["fos"]["fos"] is not None
    assert result["fos"]["rating"] == "safe"


def test_interpret_results_fos_no_targets():
    result = interpret_results(250.0, None, [], "Steel-1045")
    assert "fos" in result
    assert result["fos"]["fos"] == round(530.0 / 250.0, 2)


def test_interpret_results_fos_unknown_material():
    result = interpret_results(150.0, None, [], "Unobtainium")
    assert result["fos"]["fos"] is None
    assert result["fos"]["rating"] == "unknown"


# ── _fos_advisory ─────────────────────────────────────────────────────────────

def test_fos_advisory_safe_returns_empty():
    advisory = _fos_advisory("safe", "Al6061-T6", 100.0, 2.76)
    assert advisory == []


def test_fos_advisory_unknown_returns_empty():
    advisory = _fos_advisory("unknown", "Al6061-T6", 100.0, 0.0)
    assert advisory == []


def test_fos_advisory_marginal_has_lines():
    advisory = _fos_advisory("marginal", "Al6061-T6", 200.0, 1.38)
    assert len(advisory) >= 2


def test_fos_advisory_critical_has_lines():
    advisory = _fos_advisory("critical", "Al6061-T6", 400.0, 0.69)
    assert len(advisory) >= 2


def test_fos_advisory_marginal_first_line_contains_numbers():
    advisory = _fos_advisory("marginal", "Al6061-T6", 200.0, 1.38)
    first = advisory[0]
    assert "1.38" in first
    assert "200" in first
    assert "276" in first


def test_fos_advisory_critical_geometry_tip():
    advisory = _fos_advisory("critical", "Al6061-T6", 400.0, 0.69)
    combined = " ".join(advisory)
    assert "yield" in combined.lower() or "wall" in combined.lower() or "thickness" in combined.lower()


def test_fos_advisory_marginal_geometry_tip():
    advisory = _fos_advisory("marginal", "Al6061-T6", 200.0, 1.38)
    combined = " ".join(advisory)
    assert "cross-section" in combined.lower() or "increase" in combined.lower()


def test_fos_advisory_suggests_alternatives_for_marginal():
    advisory = _fos_advisory("marginal", "Al6061-T6", 200.0, 1.38)
    combined = " ".join(advisory)
    assert "FoS" in combined or "fos" in combined.lower()


def test_fos_advisory_excludes_current_material():
    advisory = _fos_advisory("critical", "Al6061-T6", 400.0, 0.69)
    alt_line = next((l for l in advisory if "alternatives" in l.lower()), "")
    assert "al6061" not in alt_line.lower()


def test_fos_advisory_zero_stress_returns_empty():
    advisory = _fos_advisory("critical", "Al6061-T6", 0.0, 0.0)
    assert advisory == []


# ── interpret_results: fos_advisory field ────────────────────────────────────

def test_interpret_results_has_fos_advisory_key():
    result = interpret_results(200.0, None, [], "Al6061-T6")
    assert "fos_advisory" in result


def test_interpret_results_fos_advisory_empty_for_safe():
    result = interpret_results(50.0, None, [], "Al6061-T6")  # 276/50 = 5.52 → safe
    assert result["fos_advisory"] == []


def test_interpret_results_fos_advisory_nonempty_for_marginal():
    result = interpret_results(200.0, None, [], "Al6061-T6")  # 276/200 = 1.38 → marginal
    assert len(result["fos_advisory"]) >= 2


def test_interpret_results_fos_advisory_present_with_targets():
    targets = [{"target_id": "s1", "metric": "von_mises_max_mpa", "operator": "<=", "value": 300.0}]
    result = interpret_results(200.0, None, targets, "Al6061-T6")
    assert "fos_advisory" in result
