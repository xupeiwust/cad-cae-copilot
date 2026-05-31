"""B-Rep stitching READINESS + edge matching for generated analytic face candidates.

Analyzes validated plane/cylinder face candidates and produces a STITCHING PLAN before any
sewing is attempted: it extracts approximate boundary edges, matches them across faces by
geometry tolerance (using mesh-region adjacency as a prior), and reports readiness +
blocking issues. It does NOT sew faces, does NOT create a shell/solid, and does NOT export
STEP. NURBS/freeform fitting is out of scope.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_brep_face_generation import PARTIAL_BREP_FACES_PATH
from aieng.converters.mesh_brep_reconstruction import PARTIAL_BREP_SURFACES_PATH
from aieng.converters.mesh_region_segmentation import MESH_REGION_GRAPH_PATH

MESH_BREP_STITCHING_PLAN_PATH = "graph/mesh_brep_stitching_plan.json"
MESH_BREP_STITCHING_READINESS_PATH = "diagnostics/mesh_brep_stitching_readiness.json"

_TOL_FRAC = 0.01        # endpoint-gap tolerance as a fraction of the model bbox diagonal
_NEAR_FRAC = 4.0        # gaps within NEAR_FRAC*tol of a match are "near-miss" (gapped)
_LEN_REL = 0.1          # max relative edge-length difference for a match
_CLOSED_MIN_FACES = 4


def _honesty() -> dict[str, Any]:
    return {"shell_created": False, "solid_created": False, "step_exported": False,
            "cad_editable": False, "stitching_plan_only": True}


def _dist(a, b) -> float:
    return math.sqrt(sum((float(a[k]) - float(b[k])) ** 2 for k in range(3)))


def _perp_basis(axis):
    import numpy as np
    a = np.asarray(axis, dtype=float)
    a = a / (np.linalg.norm(a) or 1.0)
    ref = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(a, ref); e1 = e1 / (np.linalg.norm(e1) or 1.0)
    e2 = np.cross(a, e1)
    return a, e1, e2


def _plane_edges(loop: list) -> list[tuple]:
    pts = [[float(p[0]), float(p[1]), float(p[2])] for p in loop]
    if len(pts) >= 2 and _dist(pts[0], pts[-1]) < 1e-9:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        return []
    return [(pts[i], pts[(i + 1) % n]) for i in range(n)]


def _cylinder_edges(cand: dict[str, Any]) -> list[tuple]:
    a = cand.get("analytic") or {}
    b = cand.get("boundary") or {}
    angular = b.get("angular_range") or a.get("angular_range")
    axial = a.get("axial_range") or b.get("axial_range")
    origin = a.get("axis_origin")
    axis = a.get("axis_direction")
    radius = a.get("radius")
    if not (angular and axial and origin and axis and radius):
        return []   # insufficient boundary -> no edges (do NOT fabricate)
    import numpy as np
    ax, e1, e2 = _perp_basis(axis)
    o = np.asarray(origin, dtype=float)
    r = float(radius)
    a0, a1 = float(axial[0]), float(axial[1])
    u0, u1 = float(angular[0]), float(angular[1])

    def pt(u, a):
        return list(o + (a - a0) * ax + r * (math.cos(u) * e1 + math.sin(u) * e2))
    # the two axial straight edges (well-defined endpoints) at the angular ends
    return [(pt(u0, a0), pt(u0, a1)), (pt(u1, a0), pt(u1, a1))]


def _edge_alignment(e1: tuple, e2: tuple) -> tuple[float, str]:
    """Best endpoint gap + orientation ('reversed' is the manifold-consistent case)."""
    (p0, p1), (q0, q1) = e1, e2
    d_same = max(_dist(p0, q0), _dist(p1, q1))
    d_rev = max(_dist(p0, q1), _dist(p1, q0))
    return (d_same, "same") if d_same <= d_rev else (d_rev, "reversed")


def plan_brep_stitching(
    faces_doc: dict[str, Any] | None,
    surfaces_doc: dict[str, Any] | None,
    region_graph: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Match boundary edges across generated faces and report stitching readiness.

    Returns ``(plan, readiness)``. Pure. Plan only — no sewing, no shell, no STEP."""
    prov_src = (faces_doc or {}).get("provenance") or (surfaces_doc or {}).get("provenance") or {}
    provenance = {
        "source_mesh_artifact": prov_src.get("source_mesh_artifact"),
        "source_ir_node": prov_src.get("source_ir_node"),
        "design_space_node": prov_src.get("design_space_node"),
        "runtime": prov_src.get("runtime"),
        "partial_brep_faces": PARTIAL_BREP_FACES_PATH,
        "representation_kind": "mesh", "geometry_kind": "mesh",
        **_honesty(),
        "limitations": [
            "Stitching plan only: approximate boundary-edge matching toward a future shell. "
            "No faces are sewn, no watertight solid is built, no STEP is exported, not CAD-editable.",
        ],
    }
    warnings: list[str] = []
    missing: list[str] = []
    if not isinstance(faces_doc, dict):
        missing.append(PARTIAL_BREP_FACES_PATH)
    if not isinstance(surfaces_doc, dict):
        missing.append(PARTIAL_BREP_SURFACES_PATH)

    # candidate boundaries keyed by face id
    cand_by_id: dict[str, dict[str, Any]] = {}
    for c in (surfaces_doc or {}).get("face_candidates") or []:
        cand_by_id[str(c.get("face_candidate_id"))] = c

    generated = [f for f in ((faces_doc or {}).get("faces") or []) if f.get("status") == "generated"]
    edges: list[dict[str, Any]] = []
    faces_without_boundary: list[str] = []
    generated_region_ids: set[str] = set()
    for f in generated:
        fid = str(f.get("face_id"))
        rid = str(f.get("source_region_id"))
        generated_region_ids.add(rid)
        cand = cand_by_id.get(fid) or {}
        if f.get("face_type") == "plane":
            segs = _plane_edges((cand.get("boundary") or {}).get("loop_world") or [])
        elif f.get("face_type") == "cylinder":
            segs = _cylinder_edges(cand)
        else:
            segs = []
        if not segs:
            faces_without_boundary.append(fid)
        for k, (p0, p1) in enumerate(segs):
            edges.append({"edge_id": f"{fid}::e{k}", "face_id": fid, "region_id": rid,
                          "p0": p0, "p1": p1, "length": _dist(p0, p1)})

    # tolerance from the model scale
    if edges:
        coords = [[p[k] for e in edges for p in (e["p0"], e["p1"])] for k in range(3)]
        diag = math.sqrt(sum((max(c) - min(c)) ** 2 for c in coords)) or 1.0
    else:
        diag = 1.0
    tol = max(diag * _TOL_FRAC, 1e-6)
    near = tol * _NEAR_FRAC

    # region adjacency prior
    adj_set: set[frozenset] = set()
    for e in (region_graph or {}).get("adjacency") or []:
        ra, rb = e.get("region_a"), e.get("region_b")
        if ra is not None and rb is not None:
            adj_set.add(frozenset((str(ra), str(rb))))

    matches: list[dict[str, Any]] = []
    match_count: dict[int, int] = {}
    near_miss = 0
    gaps: list[float] = []
    orientation_conflicts = 0
    matched_region_pairs: set[frozenset] = set()
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            if edges[i]["face_id"] == edges[j]["face_id"]:
                continue
            gap, orientation = _edge_alignment((edges[i]["p0"], edges[i]["p1"]),
                                               (edges[j]["p0"], edges[j]["p1"]))
            li, lj = edges[i]["length"], edges[j]["length"]
            len_ok = abs(li - lj) <= _LEN_REL * max(li, lj, 1e-9) + tol
            if gap <= tol and len_ok:
                ra, rb = edges[i]["region_id"], edges[j]["region_id"]
                adjacent = frozenset((ra, rb)) in adj_set
                matches.append({
                    "edge_a": edges[i]["edge_id"], "edge_b": edges[j]["edge_id"],
                    "face_a": edges[i]["face_id"], "face_b": edges[j]["face_id"],
                    "region_a": ra, "region_b": rb,
                    "gap": round(gap, 6), "orientation": orientation,
                    "region_adjacent": adjacent,
                    "confidence": "high" if adjacent else "low",
                })
                match_count[i] = match_count.get(i, 0) + 1
                match_count[j] = match_count.get(j, 0) + 1
                gaps.append(gap)
                if orientation == "same":
                    orientation_conflicts += 1
                if ra != rb:
                    matched_region_pairs.add(frozenset((ra, rb)))
            elif tol < gap <= near and len_ok:
                near_miss += 1

    matched_edge_ids = {m["edge_a"] for m in matches} | {m["edge_b"] for m in matches}
    unmatched_edges = [e["edge_id"] for e in edges if e["edge_id"] not in matched_edge_ids]
    conflicting = [eid for eid, n in
                   {edges[i]["edge_id"]: c for i, c in match_count.items()}.items() if n > 1]

    # adjacency coverage among generated faces
    gen_adj_pairs = [p for p in adj_set
                     if all(r in generated_region_ids for r in p)]
    covered = [p for p in gen_adj_pairs if p in matched_region_pairs]
    adjacency_covered_fraction = round(len(covered) / len(gen_adj_pairs), 4) if gen_adj_pairs else (
        1.0 if len(generated) <= 1 else 0.0)
    # unreconstructed neighbours: region adjacent to a generated region but not itself generated
    unreconstructed_neighbors = sorted({
        r for p in adj_set for r in p
        if (p & generated_region_ids) and r not in generated_region_ids})

    matched_pair_count = len(matches)
    unmatched_count = len(unmatched_edges)
    can_partial = len(generated) >= 2 and matched_pair_count >= 1
    can_closed = (len(generated) >= _CLOSED_MIN_FACES and unmatched_count == 0
                  and not conflicting and near_miss == 0
                  and adjacency_covered_fraction >= 1.0 and not unreconstructed_neighbors)
    confidence = "high" if can_closed else ("medium" if can_partial else "low")

    blocking: list[dict[str, Any]] = []
    if len(generated) < 2:
        blocking.append({"issue": "insufficient_generated_faces", "detail": len(generated)})
    if edges and unmatched_count / len(edges) > 0.25:
        blocking.append({"issue": "too_many_unmatched_edges",
                         "detail": f"{unmatched_count}/{len(edges)} boundary edges unmatched"})
    if faces_without_boundary:
        blocking.append({"issue": "missing_boundaries", "detail": faces_without_boundary})
    if conflicting:
        blocking.append({"issue": "conflicting_edge_matches", "detail": conflicting})
    if near_miss:
        blocking.append({"issue": "large_edge_gaps",
                         "detail": f"{near_miss} near-miss edge pair(s) within {near:.3g} but > tol {tol:.3g}"})
    if unreconstructed_neighbors:
        blocking.append({"issue": "unreconstructed_neighbor_regions", "detail": unreconstructed_neighbors})

    summary = {
        "generated_face_count": len(generated),
        "boundary_edge_count": len(edges),
        "matched_edge_pair_count": matched_pair_count,
        "unmatched_edge_count": unmatched_count,
        "adjacency_covered_fraction": adjacency_covered_fraction,
        "orientation_conflicts": orientation_conflicts,
        "conflicting_edge_count": len(conflicting),
        "can_attempt_partial_shell": bool(can_partial),
        "can_attempt_closed_shell": bool(can_closed),
        "confidence": confidence,
    }
    if missing:
        warnings.append(f"missing inputs: {', '.join(missing)}")

    plan = {
        "format": "aieng.mesh_brep_stitching_plan",
        "format_version": FORMAT_VERSION, "schema_version": "0.1",
        "summary": summary,
        "edge_matches": matches,
        "unmatched_edges": unmatched_edges,
        "provenance": provenance,
        "claim_boundary": "Edge-matching plan toward a FUTURE shell. No faces are sewn, no "
                          "solid is built, no STEP is exported.",
    }
    readiness = {
        "format": "aieng.mesh_brep_stitching_readiness",
        "schema_version": "0.1",
        "available": not bool(missing),
        "summary": summary,
        "blocking_issues": blocking,
        "edge_gap_statistics": {
            "match_count": len(gaps),
            "max_gap": round(max(gaps), 6) if gaps else 0.0,
            "rms_gap": round(math.sqrt(sum(g * g for g in gaps) / len(gaps)), 6) if gaps else 0.0,
            "near_miss_pairs": near_miss,
        },
        "tolerances": {"endpoint_gap_tol": round(tol, 6), "near_miss_tol": round(near, 6),
                       "tol_fraction_of_bbox_diag": _TOL_FRAC, "length_rel_tol": _LEN_REL},
        "adjacency_prior": {
            "region_adjacency_pairs": len(adj_set),
            "generated_adjacency_pairs": len(gen_adj_pairs),
            "covered_pairs": len(covered),
            "high_confidence_matches": sum(1 for m in matches if m["confidence"] == "high"),
            "low_confidence_matches": sum(1 for m in matches if m["confidence"] == "low"),
        },
        "faces_without_boundary": faces_without_boundary,
        "warnings": warnings,
        "provenance": provenance,
    }
    return plan, readiness


# ── package integration ──────────────────────────────────────────────────────

def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def build_brep_stitching_plan(package_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read generated faces + candidate boundaries + region adjacency from a package and
    return ``(plan, readiness)``. Missing inputs degrade honestly."""
    package_path = Path(package_path)
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            faces_doc = _read_json(zf, PARTIAL_BREP_FACES_PATH, names)
            surfaces_doc = _read_json(zf, PARTIAL_BREP_SURFACES_PATH, names)
            region_graph = _read_json(zf, MESH_REGION_GRAPH_PATH, names)
    except Exception:  # noqa: BLE001
        return plan_brep_stitching(None, None, None)
    return plan_brep_stitching(faces_doc, surfaces_doc, region_graph)


def write_brep_stitching_plan(package_path: str | Path) -> dict[str, Any]:
    """Build + write graph/mesh_brep_stitching_plan.json and
    diagnostics/mesh_brep_stitching_readiness.json. Best-effort; never sews / exports STEP."""
    package_path = Path(package_path)
    plan, readiness = build_brep_stitching_plan(package_path)
    if not package_path.exists():
        return plan
    members = {
        MESH_BREP_STITCHING_PLAN_PATH: (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode(),
        MESH_BREP_STITCHING_READINESS_PATH: (json.dumps(readiness, indent=2, sort_keys=True) + "\n").encode(),
    }
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename not in members:
                    dst.writestr(item, src.read(item.filename))
            for name, data in members.items():
                dst.writestr(name, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return plan
