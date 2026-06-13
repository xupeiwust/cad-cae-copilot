"""Advisory multi-part topology/size optimization problem derivation (#203)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.assembly_topopt import (
    ASSEMBLY_MULTIPART_TOPOPT_PROBLEM_PATH,
    derive_multipart_topopt_problem,
    write_multipart_topopt_problem,
)


def _solid(sid: str, bbox: list[float]) -> dict:
    return {"id": sid, "type": "solid", "bounding_box": bbox}


def _topo(*pids: str) -> dict:
    return {pid: {f"{pid}_body": _solid(f"{pid}_body", [0, 0, 0, 10, 10, 10])} for pid in pids}


def _resolution(*iface_ids: str) -> dict:
    return {"interfaces": {
        iid: {"resolution_status": "resolved", "world": {"bbox": [0, 0, 0, 5, 5, 5], "centroid": [2.5, 2.5, 2.5]}}
        for iid in iface_ids
    }}


def _assembly(parts: list[dict], *, connections=None, interfaces=None, frozen=None) -> dict:
    return {
        "format": "aieng.assembly_ir", "unit": "mm",
        "parts": parts,
        "interfaces": interfaces or [],
        "connections": connections or [],
        "analysis_intent": {"frozen_parts": frozen or []},
    }


def _derive(assembly, *, selected, resolution=None):
    return derive_multipart_topopt_problem(
        assembly=assembly, part_registry={}, interface_resolution=resolution or {},
        connection_geometry={}, topology_by_part=_topo(*[p["id"] for p in assembly["parts"]]),
        selected_part_ids=selected,
    )


def test_safe_multipart_case_is_ready() -> None:
    asm = _assembly(
        [
            {"id": "p1", "role": "design_part"},
            {"id": "p2", "role": "design_part"},
            {"id": "wall", "role": "reference_part"},
            {"id": "bolt", "role": "fastener"},
        ],
        interfaces=[
            {"id": "if1", "part_id": "p1", "semantic_role": "mounting_face"},
            {"id": "if2", "part_id": "p2", "semantic_role": "mounting_face"},
        ],
        connections=[{"id": "c1", "type": "bonded", "part_a": "p1", "part_b": "p2",
                      "interface_a": "if1", "interface_b": "if2"}],
    )
    problem, derivation = _derive(asm, selected=["p1", "p2"], resolution=_resolution("if1", "if2"))

    assert problem["status"] == "ready"
    assert {dp["part_id"] for dp in problem["design_parts"]} == {"p1", "p2"}
    p1 = next(dp for dp in problem["design_parts"] if dp["part_id"] == "p1")
    assert p1["design_space"]["bbox"] is not None
    assert {v["type"] for v in p1["variables"]} == {"topology_density", "sizing"}
    # non-design parts preserved + marked
    nd = {p["part_id"]: p for p in problem["non_design_parts"]}
    assert nd["wall"]["preserved"] is True and nd["bolt"]["reason"].startswith("non_optimizable_role")
    # coupling between the two design parts recorded as resolved
    c1 = next(c for c in problem["couplings"] if c["connection_id"] == "c1")
    assert c1["kind"] == "design_design" and c1["interface_a_resolved"] and c1["interface_b_resolved"]
    assert problem["refusals"] == []
    assert problem["honesty"]["advisory_only"] is True
    assert problem["honesty"]["optimizer_executed"] is False
    assert problem["honesty"]["baseline_modified"] is False
    assert derivation["summary"]["design_parts"] == 2


def test_fastener_selection_is_refused() -> None:
    asm = _assembly([
        {"id": "p1", "role": "design_part"},
        {"id": "bolt", "role": "fastener"},
    ])
    problem, _ = _derive(asm, selected=["bolt"])
    assert problem["status"] == "needs_user_input"
    reasons = {r.get("reason") for r in problem["refusals"]}
    assert any(str(r).startswith("non_optimizable_role") for r in reasons)


def test_ambiguous_ownership_design_and_frozen_is_refused() -> None:
    asm = _assembly(
        [{"id": "p1", "role": "design_part"}],
        frozen=["p1"],  # design role but also declared frozen -> ambiguous
    )
    problem, _ = _derive(asm, selected=["p1"])
    assert problem["status"] == "needs_user_input"
    assert {r.get("reason") for r in problem["refusals"]} == {"ambiguous_ownership_design_and_frozen"}


def test_missing_interface_constraint_between_design_parts_refused() -> None:
    asm = _assembly(
        [{"id": "p1", "role": "design_part"}, {"id": "p2", "role": "design_part"}],
        interfaces=[
            {"id": "if1", "part_id": "p1"}, {"id": "if2", "part_id": "p2"},
        ],
        connections=[{"id": "c1", "type": "bonded", "part_a": "p1", "part_b": "p2",
                      "interface_a": "if1", "interface_b": "if2"}],
    )
    # only if1 resolved; if2 is missing -> coupled design-design constraint incomplete
    problem, _ = _derive(asm, selected=["p1", "p2"], resolution=_resolution("if1"))
    assert problem["status"] == "needs_user_input"
    assert any(r.get("reason") == "missing_interface_constraint" and r.get("connection_id") == "c1"
               for r in problem["refusals"])


def test_no_selection_needs_user_input() -> None:
    asm = _assembly([{"id": "p1", "role": "design_part"}])
    problem, _ = _derive(asm, selected=[])
    assert problem["status"] == "needs_user_input"
    assert any(r.get("reason") == "no_parts_selected" for r in problem["refusals"])


def test_write_multipart_problem_is_advisory(tmp_path: Path) -> None:
    asm = _assembly(
        [{"id": "p1", "role": "design_part"}, {"id": "p2", "role": "design_part"}],
        interfaces=[{"id": "if1", "part_id": "p1"}, {"id": "if2", "part_id": "p2"}],
        connections=[{"id": "c1", "type": "bonded", "part_a": "p1", "part_b": "p2",
                      "interface_a": "if1", "interface_b": "if2"}],
    )
    pkg = tmp_path / "asm.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("assembly/assembly_ir.json", json.dumps(asm))
        zf.writestr("assembly/interface_resolution.json", json.dumps(_resolution("if1", "if2")))
        for pid in ("p1", "p2"):
            zf.writestr(f"parts/{pid}/topology_map.json",
                        json.dumps({"entities": [_solid(f"{pid}_body", [0, 0, 0, 10, 10, 10])]}))

    res = write_multipart_topopt_problem(pkg, selected_part_ids=["p1", "p2"])
    assert res["assembly_present"] is True
    assert res["status"] == "ready"
    assert set(res["design_parts"]) == {"p1", "p2"}
    assert res["baseline_modified"] is False

    with zipfile.ZipFile(pkg) as zf:
        problem = json.loads(zf.read(ASSEMBLY_MULTIPART_TOPOPT_PROBLEM_PATH))
    assert problem["honesty"]["optimizer_executed"] is False
    assert problem["honesty"]["production_grade_simultaneous_optimization"] is False
