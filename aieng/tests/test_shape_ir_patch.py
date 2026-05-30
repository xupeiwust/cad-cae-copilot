"""Tests for the Shape IR patch format + apply."""
from __future__ import annotations

import copy

from aieng.converters.shape_ir_patch import (
    apply_shape_ir_patch,
    build_patch_report,
    validate_shape_ir,
)


def _box_payload():
    return {"parts": [
        {"id": "plate", "type": "box", "dimensions": [40, 30, 6], "parameters": {"RADIUS": 4}},
        {"id": "post", "type": "cylinder", "radius": 5, "height": 20},
    ]}


def _nurbs_payload():
    return {"representation": "nurbs_brep", "parts": [
        {"id": "patch", "type": "nurbs_surface", "control_net": [
            [[0, 0, 0], [10, 0, 0]],
            [[0, 10, 0], [10, 10, 0]],
        ]},
    ]}


def test_set_parameter():
    payload = _box_payload()
    original = copy.deepcopy(payload)
    patch = {"operations": [{"op": "set_parameter", "target": "plate", "parameter": "RADIUS",
                             "value": 12, "reason": "stiffen corner"}]}
    res = apply_shape_ir_patch(payload, patch)
    assert res["ok"] is True and not res["failed"]
    assert res["new_payload"]["parts"][0]["parameters"]["RADIUS"] == 12
    assert payload == original  # input never mutated
    assert res["operations"][0]["status"] == "applied"
    assert res["operations"][0]["reason"] == "stiffen corner"


def test_move_control_point_delta_and_value():
    res = apply_shape_ir_patch(_nurbs_payload(), {"operations": [
        {"op": "move_control_point", "target": "patch", "path": [0, 1], "delta": [0, 0, 5]},
    ]})
    assert res["ok"] is True
    assert res["new_payload"]["parts"][0]["control_net"][0][1] == [10.0, 0.0, 5.0]

    res2 = apply_shape_ir_patch(_nurbs_payload(), {"operations": [
        {"op": "move_control_point", "target": "patch", "path": [1, 1], "value": [10, 10, 7]},
    ]})
    assert res2["new_payload"]["parts"][0]["control_net"][1][1] == [10.0, 10.0, 7.0]

    # out-of-range index fails atomically (original untouched)
    bad = apply_shape_ir_patch(_nurbs_payload(), {"operations": [
        {"op": "move_control_point", "target": "patch", "path": [9, 9], "delta": [0, 0, 1]},
    ]})
    assert bad["ok"] is False and bad["failed"][0]["op"] == "move_control_point"


def test_add_node_and_duplicate():
    res = apply_shape_ir_patch(_box_payload(), {"operations": [
        {"op": "add_node", "node": {"id": "rib", "type": "box", "dimensions": [30, 4, 20]}},
    ]})
    assert res["ok"] is True
    ids = [p["id"] for p in res["new_payload"]["parts"]]
    assert ids == ["plate", "post", "rib"]

    dup = apply_shape_ir_patch(_box_payload(), {"operations": [
        {"op": "add_node", "node": {"id": "plate", "type": "box"}},
    ]})
    assert dup["ok"] is False and "already exists" in dup["failed"][0]["message"]


def test_invalid_patch_target_and_atomicity():
    payload = _box_payload()
    original = copy.deepcopy(payload)
    # second op targets a missing node; first op must NOT be committed (atomic)
    res = apply_shape_ir_patch(payload, {"operations": [
        {"op": "set_parameter", "target": "plate", "parameter": "RADIUS", "value": 99},
        {"op": "set_parameter", "target": "ghost", "parameter": "X", "value": 1},
    ]})
    assert res["ok"] is False
    statuses = [o["status"] for o in res["operations"]]
    assert statuses == ["applied", "failed"]
    assert payload == original  # nothing written back


def test_remove_only_node_fails_validation():
    # removing every node yields an empty 'parts' -> invalid Shape IR -> reject
    res = apply_shape_ir_patch({"parts": [{"id": "only", "type": "box"}]}, {"operations": [
        {"op": "remove_node", "target": "only"},
    ]})
    assert res["ok"] is False
    assert res["validation"]["ok"] is False


def test_change_representation_backend():
    ok = apply_shape_ir_patch(_box_payload(), {"operations": [
        {"op": "change_representation_backend", "value": "manifold_mesh"},
    ]})
    assert ok["ok"] is True and ok["new_payload"]["representation"] == "manifold_mesh"
    bad = apply_shape_ir_patch(_box_payload(), {"operations": [
        {"op": "change_representation_backend", "value": "not_a_backend"},
    ]})
    assert bad["ok"] is False


def test_connect_disconnect():
    res = apply_shape_ir_patch(_box_payload(), {"operations": [
        {"op": "connect", "connection": {"source": "plate", "target": "post", "type": "joined_to"}},
    ]})
    assert res["ok"] is True
    assert {"source": "plate", "target": "post", "type": "joined_to"} in res["new_payload"]["adjacency"]
    # disconnect a non-existent edge fails
    bad = apply_shape_ir_patch(_box_payload(), {"operations": [
        {"op": "disconnect", "connection": {"source": "plate", "target": "post"}},
    ]})
    assert bad["ok"] is False


def test_dry_run_does_not_imply_commit():
    res = apply_shape_ir_patch(_box_payload(), {"operations": [
        {"op": "set_parameter", "target": "plate", "parameter": "RADIUS", "value": 20},
    ]}, dry_run=True)
    assert res["ok"] is True and res["dry_run"] is True
    assert res["new_payload"]["parts"][0]["parameters"]["RADIUS"] == 20
    report = build_patch_report({"author": "tester", "tool": "pytest"}, res)
    assert report["dry_run"] is True
    assert report["provenance"]["committed"] is False  # dry-run never commits
    assert report["applied_count"] == 1


def test_validate_shape_ir():
    assert validate_shape_ir({"parts": [{"id": "a"}]})[0] is True
    assert validate_shape_ir({"parts": []})[0] is False
    assert validate_shape_ir({"parts": [{"id": "a"}, {"id": "a"}]})[0] is False
    assert validate_shape_ir({})[0] is False
