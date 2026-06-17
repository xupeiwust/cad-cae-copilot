"""Tests for the geometry target validator v0 (#291)."""
from __future__ import annotations

from aieng.converters.geometry_targets import validate_geometry_targets


def _topo(parts: list[tuple[str, list[float]]]) -> dict:
    return {"entities": [
        {"id": f"b{i}", "type": "solid", "name": n, "bounding_box": bb}
        for i, (n, bb) in enumerate(parts)
    ]}


def _fg(named: tuple[str, ...] = (), ftypes: tuple[str, ...] = ()) -> dict:
    feats = [{"id": f"f_{n}", "type": "named_part", "name": n} for n in named]
    feats += [{"id": f"t_{t}", "type": t, "name": t} for t in ftypes]
    return {"features": feats}


def _statuses(report: dict) -> list[str]:
    return [t["status"] for t in report["targets"]]


def test_named_part_present_pass_and_fail() -> None:
    r = validate_geometry_targets(
        _topo([("housing", [0, 0, 0, 120, 80, 60])]), _fg(named=("housing",)),
        [{"kind": "named_part_present", "part": "housing"},
         {"kind": "named_part_present", "part": "ghost"}],
    )
    assert _statuses(r) == ["pass", "fail"]
    assert r["verdict"] == "fail"


def test_overall_and_part_size() -> None:
    topo = _topo([("housing", [0, 0, 0, 120, 80, 60]), ("cover", [0, 0, 60, 120, 80, 66])])
    r = validate_geometry_targets(topo, _fg(named=("housing", "cover")), [
        {"kind": "overall_size", "size_mm": [120, 80, 66], "tolerance_mm": 1},   # union → pass
        {"kind": "part_size", "part": "cover", "size_mm": [120, 80, 6], "tolerance_mm": 1},  # pass
        {"kind": "part_size", "part": "cover", "size_mm": [100, 80, 6], "tolerance_mm": 1},  # fail (x dev 20)
        {"kind": "part_size", "part": "ghost", "size_mm": [1, 1, 1]},            # fail (missing part)
    ])
    assert _statuses(r) == ["pass", "pass", "fail", "fail"]


def test_part_center_and_count() -> None:
    r = validate_geometry_targets(
        _topo([("a", [0, 0, 0, 10, 10, 10])]), _fg(named=("a",)),
        [{"kind": "part_center", "part": "a", "center_mm": [5, 5, 5], "tolerance_mm": 0.5},
         {"kind": "part_count", "count": 1},
         {"kind": "part_count", "min": 2}],
    )
    assert _statuses(r) == ["pass", "pass", "fail"]


def test_feature_present_and_unknown() -> None:
    r = validate_geometry_targets(
        _topo([("a", [0, 0, 0, 10, 10, 10])]), _fg(named=("a",), ftypes=("fillet",)),
        [{"kind": "feature_present", "feature_type": "fillet"},
         {"kind": "feature_present", "feature_type": "loft"},
         {"kind": "overall_size", "size_mm": "bad"},   # unknown (malformed)
         {"kind": "frobnicate"}],                       # unknown (unknown kind)
    )
    assert _statuses(r) == ["pass", "fail", "unknown", "unknown"]
    assert r["verdict"] == "fail"


def test_no_floating_and_deep_overlap() -> None:
    far = _topo([("a", [0, 0, 0, 10, 10, 10]), ("b", [200, 200, 200, 210, 210, 210])])
    assert validate_geometry_targets(far, _fg(named=("a", "b")),
                                     [{"kind": "no_floating_parts"}])["targets"][0]["status"] == "fail"
    over = _topo([("a", [0, 0, 0, 20, 20, 20]), ("b", [2, 2, 2, 18, 18, 18])])  # b buried in a
    assert validate_geometry_targets(over, _fg(named=("a", "b")),
                                     [{"kind": "no_deep_overlap"}])["targets"][0]["status"] == "fail"
    touching = _topo([("a", [0, 0, 0, 10, 10, 10]), ("b", [10, 0, 0, 20, 10, 10])])  # share a face
    rok = validate_geometry_targets(touching, _fg(named=("a", "b")),
                                    [{"kind": "no_floating_parts"}, {"kind": "no_deep_overlap"}])
    assert all(t["status"] == "pass" for t in rok["targets"])


def test_all_pass_verdict() -> None:
    r = validate_geometry_targets(
        _topo([("housing", [0, 0, 0, 120, 80, 60])]), _fg(named=("housing",)),
        [{"kind": "named_part_present", "part": "housing"},
         {"kind": "overall_size", "size_mm": [120, 80, 60], "tolerance_mm": 1}],
    )
    assert r["verdict"] == "pass"
    assert r["summary"] == {"total": 2, "pass": 2, "fail": 0, "unknown": 0}


def test_brep_targets_unknown_without_brep_results() -> None:
    r = validate_geometry_targets(
        _topo([("shaft", [0, 0, 0, 10, 10, 50]), ("bore", [0, 0, 0, 12, 12, 50])]),
        _fg(named=("shaft", "bore")),
        [
            {"id": "t1", "kind": "no_interference", "part_a": "shaft", "part_b": "bore"},
            {"id": "t2", "kind": "coaxial_within", "part_a": "shaft", "part_b": "bore", "tolerance_mm": 0.1},
            {"id": "t3", "kind": "faces_flush_within", "part_a": "shaft", "part_b": "bore", "tolerance_mm": 0.1},
            {"id": "t4", "kind": "clearance_within", "part_a": "shaft", "part_b": "bore", "min_clearance_mm": 0.1, "max_clearance_mm": 0.5},
        ],
    )
    assert all(t["status"] == "unknown" for t in r["targets"])
    assert r["verdict"] == "unknown"


def test_brep_targets_merge_pass_and_fail() -> None:
    brep_results = {
        "t1": {"status": "pass", "detail": "no interference", "measured": 0.0,
               "expected": {"intersection_volume_mm3": 0}},
        "t2": {"status": "fail", "detail": "axis offset 2.0mm", "measured": {"axis_distance_mm": 2.0},
               "expected": {"max_axis_distance_mm": 0.1}},
        "t3": {"status": "pass", "detail": "flush", "measured": {"plane_distance_mm": 0.0}},
        "t4": {"status": "pass", "detail": "clearance ok", "measured": 0.3},
    }
    r = validate_geometry_targets(
        _topo([("shaft", [0, 0, 0, 10, 10, 50]), ("bore", [0, 0, 0, 12, 12, 50])]),
        _fg(named=("shaft", "bore")),
        [
            {"id": "t1", "kind": "no_interference", "part_a": "shaft", "part_b": "bore"},
            {"id": "t2", "kind": "coaxial_within", "part_a": "shaft", "part_b": "bore", "tolerance_mm": 0.1},
            {"id": "t3", "kind": "faces_flush_within", "part_a": "shaft", "part_b": "bore", "tolerance_mm": 0.1},
            {"id": "t4", "kind": "clearance_within", "part_a": "shaft", "part_b": "bore", "min_clearance_mm": 0.1, "max_clearance_mm": 0.5},
        ],
        brep_results=brep_results,
    )
    statuses = {t["id"]: t["status"] for t in r["targets"]}
    assert statuses == {"t1": "pass", "t2": "fail", "t3": "pass", "t4": "pass"}
    assert r["verdict"] == "fail"


def test_brep_clearance_recomputed_from_measured() -> None:
    # When the subprocess only returns measured distance, geometry_targets recomputes pass/fail.
    r = validate_geometry_targets(
        _topo([("a", [0, 0, 0, 10, 10, 10]), ("b", [20, 0, 0, 30, 10, 10])]),
        _fg(named=("a", "b")),
        [{"id": "c1", "kind": "clearance_within", "part_a": "a", "part_b": "b",
          "min_clearance_mm": 0.1, "max_clearance_mm": 0.5}],
        brep_results={"c1": {"status": "unknown", "measured": 10.0, "detail": ""}},
    )
    assert r["targets"][0]["status"] == "fail"
    assert r["targets"][0]["measured"] == 10.0
