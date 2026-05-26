"""Tests for design_target_chat.py — natural language target parser + package write."""
import sys
import json
import zipfile
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.design_target_chat import parse_target_from_text, _read_targets, _write_targets


# ── parse_target_from_text ────────────────────────────────────────────────────

def test_parse_stress_mpa():
    t = parse_target_from_text("set max stress to 250 MPa")
    assert t is not None
    assert t["metric"] == "von_mises_max_mpa"
    assert t["value"] == 250.0
    assert t["unit"] == "MPa"
    assert t["operator"] == "<="


def test_parse_displacement_mm():
    t = parse_target_from_text("max displacement must be less than 0.5 mm")
    assert t is not None
    assert t["metric"] == "max_displacement_mm"
    assert t["value"] == 0.5
    assert t["unit"] == "mm"
    assert t["operator"] == "<"


def test_parse_stress_limit_shorthand():
    t = parse_target_from_text("stress limit 200 MPa")
    assert t is not None
    assert t["metric"] == "von_mises_max_mpa"
    assert t["value"] == 200.0


def test_parse_von_mises_variant():
    t = parse_target_from_text("von mises stress should not exceed 300 MPa")
    assert t is not None
    assert t["metric"] == "von_mises_max_mpa"
    assert t["operator"] == "<="
    assert t["value"] == 300.0


def test_parse_deflection_keyword():
    t = parse_target_from_text("maximum deflection at most 1.5 mm")
    assert t is not None
    assert t["metric"] == "max_displacement_mm"
    assert t["value"] == 1.5
    assert t["operator"] == "<="


def test_parse_at_least_operator():
    t = parse_target_from_text("displacement should be at least 0.1 mm")
    assert t is not None
    assert t["operator"] == ">="


def test_parse_no_metric_returns_none():
    assert parse_target_from_text("the part should be strong") is None


def test_parse_no_value_returns_none():
    assert parse_target_from_text("set stress limit to a reasonable value") is None


def test_parse_target_id_format():
    t = parse_target_from_text("set max stress to 250 MPa")
    assert t is not None
    assert "von_mises_max_mpa" in t["target_id"]
    assert "250" in t["target_id"]


def test_parse_label_is_human_readable():
    t = parse_target_from_text("set stress to 300 MPa")
    assert t is not None
    assert "stress" in t["label"].lower()


def test_parse_decimal_value():
    t = parse_target_from_text("displacement limit 0.25 mm")
    assert t is not None
    assert t["value"] == 0.25


# ── _read_targets / _write_targets ────────────────────────────────────────────

def _make_package(members: dict[str, bytes]) -> Path:
    tmp = Path(tempfile.mktemp(suffix=".aieng"))
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return tmp


def test_read_targets_empty_package():
    pkg = _make_package({})
    try:
        assert _read_targets(pkg) == []
    finally:
        pkg.unlink(missing_ok=True)


def test_read_targets_from_yaml():
    doc = {"targets": [{"target_id": "s1", "metric": "von_mises_max_mpa",
                         "operator": "<=", "value": 200.0}]}
    pkg = _make_package({"task/design_targets.yaml": yaml.safe_dump(doc).encode()})
    try:
        targets = _read_targets(pkg)
        assert len(targets) == 1
        assert targets[0]["target_id"] == "s1"
    finally:
        pkg.unlink(missing_ok=True)


def test_write_targets_round_trip():
    pkg = _make_package({})
    targets = [{"target_id": "t1", "label": "Stress", "metric": "von_mises_max_mpa",
                "operator": "<=", "value": 250.0, "unit": "MPa"}]
    try:
        _write_targets(pkg, targets)
        read_back = _read_targets(pkg)
        assert len(read_back) == 1
        assert read_back[0]["target_id"] == "t1"
        assert read_back[0]["value"] == 250.0
    finally:
        pkg.unlink(missing_ok=True)


def test_write_targets_preserves_other_members():
    pkg = _make_package({"geometry/topology_map.json": b'{"entities":[]}'})
    try:
        _write_targets(pkg, [{"target_id": "t1", "value": 100.0}])
        with zipfile.ZipFile(pkg, "r") as zf:
            assert "geometry/topology_map.json" in zf.namelist()
            assert "task/design_targets.yaml" in zf.namelist()
    finally:
        pkg.unlink(missing_ok=True)


def test_write_then_overwrite_targets():
    pkg = _make_package({})
    try:
        _write_targets(pkg, [{"target_id": "t1", "value": 100.0}])
        _write_targets(pkg, [{"target_id": "t1", "value": 200.0}])
        targets = _read_targets(pkg)
        assert len(targets) == 1
        assert targets[0]["value"] == 200.0
    finally:
        pkg.unlink(missing_ok=True)


# ── solver diagnosis (in simulation_runner) ───────────────────────────────────

def test_diagnose_singular_log():
    from app.simulation_runner import _diagnose_solver_log
    result = _diagnose_solver_log("*ERROR: ZERO PIVOT ENCOUNTERED")
    assert any("constrained" in r or "singular" in r.lower() for r in result)


def test_diagnose_divergence():
    from app.simulation_runner import _diagnose_solver_log
    result = _diagnose_solver_log("DIVERGENCE in iteration 12")
    assert any("diverge" in r.lower() or "converge" in r.lower() for r in result)


def test_diagnose_empty_nset():
    from app.simulation_runner import _diagnose_solver_log
    result = _diagnose_solver_log("*ERROR: EMPTY ELEMENT SET EALL")
    assert any("empty" in r.lower() or "set" in r.lower() for r in result)


def test_diagnose_unknown_error_gives_fallback():
    from app.simulation_runner import _diagnose_solver_log
    result = _diagnose_solver_log("some unknown error text with no pattern")
    assert len(result) >= 1
