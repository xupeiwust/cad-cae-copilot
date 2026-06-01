"""Assembly-aware topology-optimization setup v0.

Derives a *single selected design part* topology-optimization problem from
Assembly IR/Assembly CAE v0 evidence.  This is setup only: no optimizer is run
and no writeback is performed here.  Connections remain simplified proxies; real
contact, friction, bolt preload, and simultaneous multi-part optimization are out
of scope.
"""
from __future__ import annotations

import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.assembly_cae import ASSEMBLY_CAE_MODEL_PATH, ASSEMBLY_RESULT_MAP_PATH
from aieng.converters.assembly_interface_resolution import (
    ASSEMBLY_CONNECTION_GEOMETRY_PATH,
    INTERFACE_RESOLUTION_PATH,
)
from aieng.converters.assembly_ir import (
    ASSEMBLY_IR_PATH,
    CONNECTION_GRAPH_PATH,
    CONVERSION_MANIFEST_PATH,
    PART_REGISTRY_PATH,
)

ASSEMBLY_TOPOPT_PROBLEM_PATH = "analysis/assembly_topopt_problem.json"
ASSEMBLY_TOPOPT_DERIVATION_PATH = "diagnostics/assembly_topopt_derivation.json"
STANDARD_TOPOPT_PROBLEM_PATH = "analysis/topology_optimization_problem.json"

_SOURCE_ARTIFACTS = [
    ASSEMBLY_IR_PATH,
    PART_REGISTRY_PATH,
    CONNECTION_GRAPH_PATH,
    INTERFACE_RESOLUTION_PATH,
    ASSEMBLY_CONNECTION_GEOMETRY_PATH,
    ASSEMBLY_CAE_MODEL_PATH,
    ASSEMBLY_RESULT_MAP_PATH,
]
_OPTIMIZABLE_ROLES = {"design_part"}
_NON_OPTIMIZABLE_ROLES = {"reference_part", "fixture", "load_source", "fastener", "external_context"}
_PRESERVE_ROLES = {"mounting_face", "bolt_hole", "weld_face", "contact_face", "support_face"}
_STRESS_TYPES = {"stress", "von_mises_stress", "principal_stress"}
_DEFLECTION_TYPES = {"displacement", "deflection"}
_ENFORCEABLE_CONFIDENCE = {"high", "medium"}
_LIMITATIONS = [
    "Assembly-aware topology optimization v0 derives a problem for one selected design part only.",
    "Connection/interface regions are preserved from simplified proxy connection evidence.",
    "Loads/supports may be proxy-derived from assembly connections.",
    "Real nonlinear contact and bolt preload are not modeled.",
    "Reference, fixture, fastener, load_source, and frozen parts are not optimized.",
    "Result guidance is advisory unless use_result_guidance=true is explicitly requested.",
    "Multi-part simultaneous optimization is future work.",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _read_json(zf: zipfile.ZipFile, names: set[str], member: str) -> Any:
    if member not in names:
        return None
    try:
        return json.loads(zf.read(member).decode("utf-8"))
    except Exception:
        return None


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _replace_members(path: Path, members: dict[str, bytes]) -> None:
    if not path.exists() or not members:
        return
    tmp = path.with_suffix(".tmp.aieng")
    try:
        with zipfile.ZipFile(path, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename not in members:
                    dst.writestr(item, src.read(item.filename))
            for name, data in members.items():
                dst.writestr(name, data)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _bbox_center(b: list[float]) -> list[float]:
    return [(float(b[i]) + float(b[i + 3])) / 2 for i in range(3)]


def _bbox_union(boxes: list[list[float]]) -> list[float] | None:
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
        max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes),
    ]


def _bbox_diag(b: list[float]) -> float:
    return math.sqrt(sum((float(b[i + 3]) - float(b[i])) ** 2 for i in range(3)))


def _part_bbox_from_topology(topo_index: dict[str, dict[str, Any]]) -> list[float] | None:
    boxes = [e.get("bounding_box") for e in topo_index.values() if isinstance(e.get("bounding_box"), list) and len(e["bounding_box"]) == 6]
    return _bbox_union([[float(x) for x in b] for b in boxes])


def _topo_index(topo_doc: Any) -> dict[str, dict[str, Any]]:
    ents = (topo_doc or {}).get("entities") if isinstance(topo_doc, dict) else None
    return {str(e["id"]): e for e in _as_list(ents) if isinstance(e, dict) and e.get("id")}


def _build_topology_by_part(zf: zipfile.ZipFile, names: set[str], assembly: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    shared = _topo_index(_read_json(zf, names, "geometry/topology_map.json"))
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for part in _as_list(assembly.get("parts")):
        if not isinstance(part, dict) or not part.get("id"):
            continue
        pid = str(part["id"])
        idx: dict[str, dict[str, Any]] = {}
        for cand in (part.get("topology_ref"), f"parts/{pid}/topology_map.json", f"geometry/parts/{pid}/topology_map.json"):
            if cand and cand in names:
                idx = _topo_index(_read_json(zf, names, str(cand)))
                if idx:
                    break
        if not idx and shared:
            scoped = {eid: e for eid, e in shared.items() if e.get("body_id") in {pid, part.get("name")}}
            idx = scoped or shared
        if idx:
            out[pid] = idx
    return out


def _collect_interfaces(assembly: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for iface in _as_list(assembly.get("interfaces")):
        if isinstance(iface, dict) and iface.get("id"):
            out[str(iface["id"])] = iface
    for part in _as_list(assembly.get("parts")):
        if not isinstance(part, dict):
            continue
        for iface in _as_list(part.get("interfaces")):
            if isinstance(iface, dict) and iface.get("id"):
                rec = {**iface}
                rec.setdefault("part_id", part.get("id"))
                out[str(rec["id"])] = rec
    return out


def _grid_frame(bbox: list[float], *, dimension: str, resolution: int, resolution_3d: int) -> tuple[dict[str, Any], dict[str, Any]]:
    mins, maxs = bbox[:3], bbox[3:]
    ext = [max(float(maxs[i]) - float(mins[i]), 1e-9) for i in range(3)]
    axes = ["x", "y", "z"]
    if dimension == "3d":
        longest = max(ext)
        nx = max(int(round(resolution_3d * ext[0] / longest)), 2)
        ny = max(int(round(resolution_3d * ext[1] / longest)), 2)
        nz = max(int(round(resolution_3d * ext[2] / longest)), 2)
        grid = {"nx": nx, "ny": ny, "nz": nz}
        frame = {
            "origin": [float(x) for x in mins],
            "u_axis": "x", "v_axis": "y", "w_axis": "z",
            "cell_size": [round(ext[0] / nx, 6), round(ext[1] / ny, 6), round(ext[2] / nz, 6)],
        }
        return grid, frame
    u, v, w = sorted(range(3), key=lambda k: ext[k], reverse=True)
    nelx = max(int(resolution), 2)
    nely = max(int(round(resolution * ext[v] / ext[u])), 2)
    grid = {"nelx": nelx, "nely": nely}
    frame = {
        "origin": [float(x) for x in mins],
        "u_axis": axes[u], "v_axis": axes[v],
        "cell_size": [round(ext[u] / nelx, 6), round(ext[v] / nely, 6)],
        "thickness": round(ext[w], 6),
        "out_of_plane_axis": axes[w],
    }
    return grid, frame


def _axis_index(axis: str) -> int:
    return {"x": 0, "y": 1, "z": 2}[axis]


def _cell_of_point(p: list[float], bbox: list[float], grid: dict[str, Any], frame: dict[str, Any], dimension: str) -> list[int]:
    mins, maxs = bbox[:3], bbox[3:]
    ext = [max(maxs[i] - mins[i], 1e-9) for i in range(3)]
    if dimension == "3d":
        return [
            min(max(int((p[0] - mins[0]) / ext[0] * int(grid["nx"])), 0), int(grid["nx"]) - 1),
            min(max(int((p[1] - mins[1]) / ext[1] * int(grid["ny"])), 0), int(grid["ny"]) - 1),
            min(max(int((p[2] - mins[2]) / ext[2] * int(grid["nz"])), 0), int(grid["nz"]) - 1),
        ]
    u, v = _axis_index(frame["u_axis"]), _axis_index(frame["v_axis"])
    return [
        min(max(int((p[u] - mins[u]) / ext[u] * int(grid["nelx"])), 0), int(grid["nelx"]) - 1),
        min(max(int((p[v] - mins[v]) / ext[v] * int(grid["nely"])), 0), int(grid["nely"]) - 1),
    ]


def _cells_of_bbox(bb: list[float], bbox: list[float], grid: dict[str, Any], frame: dict[str, Any], dimension: str) -> list[list[int]]:
    c0 = _cell_of_point([bb[0], bb[1], bb[2]], bbox, grid, frame, dimension)
    c1 = _cell_of_point([bb[3], bb[4], bb[5]], bbox, grid, frame, dimension)
    ranges = [range(min(c0[i], c1[i]), max(c0[i], c1[i]) + 1) for i in range(len(c0))]
    if dimension == "3d":
        return [[i, j, k] for i in ranges[0] for j in ranges[1] for k in ranges[2]]
    return [[i, j] for i in ranges[0] for j in ranges[1]]


def _select_design_part(
    *,
    assembly: dict[str, Any],
    registry: dict[str, Any],
    selected_part_id: str | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str], list[str]]:
    diagnostics: list[str] = []
    warnings: list[str] = []
    parts_by_id = {p.get("id"): p for p in _as_list(assembly.get("parts")) if isinstance(p, dict)}
    reg_by_id = {p.get("part_id"): p for p in _as_list(registry.get("parts")) if isinstance(p, dict)}
    intent = assembly.get("analysis_intent") if isinstance(assembly.get("analysis_intent"), dict) else {}
    allowed = set(str(x) for x in _as_list(intent.get("allowed_optimization_parts")))
    frozen = set(str(x) for x in _as_list(intent.get("frozen_parts")))
    candidates: list[dict[str, Any]] = []
    for pid, part in parts_by_id.items():
        if not pid:
            continue
        reg = reg_by_id.get(pid, {})
        role = part.get("role") or reg.get("role")
        editable = bool(reg.get("editable", part.get("editable", role == "design_part")))
        if role in _NON_OPTIMIZABLE_ROLES or str(pid) in frozen:
            continue
        if role in _OPTIMIZABLE_ROLES and editable:
            if allowed and str(pid) not in allowed:
                continue
            candidates.append({**part, **{k: v for k, v in reg.items() if k not in part}, "part_id": pid})
    if not candidates:
        diagnostics.append("no_design_part")
        return None, candidates, diagnostics, warnings
    if selected_part_id:
        for c in candidates:
            if str(c.get("part_id") or c.get("id")) == str(selected_part_id):
                return c, candidates, diagnostics, warnings
        diagnostics.append("selected_part_not_optimizable")
        return None, candidates, diagnostics, warnings
    if len(candidates) > 1:
        diagnostics.append("multiple_design_parts_needs_selection")
        return None, candidates, diagnostics, warnings
    return candidates[0], candidates, diagnostics, warnings


def _derive_preserve_regions(
    *,
    selected_part_id: str,
    assembly: dict[str, Any],
    interface_resolution: dict[str, Any],
    connection_geometry: dict[str, Any],
    grid: dict[str, Any] | None,
    frame: dict[str, Any] | None,
    bbox: list[float] | None,
    dimension: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    interfaces = _collect_interfaces(assembly)
    resolved = interface_resolution.get("interfaces") if isinstance(interface_resolution.get("interfaces"), dict) else {}
    geo_by_id = {g.get("connection_id"): g for g in _as_list(connection_geometry.get("connections")) if isinstance(g, dict)}
    regions: list[dict[str, Any]] = []
    for idx, conn in enumerate(_as_list(assembly.get("connections"))):
        if not isinstance(conn, dict):
            continue
        cid = str(conn.get("id") or f"connection_{idx:03d}")
        geo = geo_by_id.get(cid, {})
        if geo.get("geometry_status") == "invalid":
            warnings.append(f"invalid_connection_not_preserved:{cid}")
            continue
        for side in ("a", "b"):
            if str(conn.get(f"part_{side}")) != selected_part_id:
                continue
            iid = conn.get(f"interface_{side}")
            iface = interfaces.get(str(iid)) if iid else None
            rec = resolved.get(str(iid)) if iid and isinstance(resolved, dict) else None
            role = (iface or {}).get("semantic_role")
            if role not in _PRESERVE_ROLES and str(conn.get("type")) not in {"bolted_proxy", "welded_proxy", "contact_proxy"}:
                continue
            world = (rec or {}).get("world") if isinstance(rec, dict) else {}
            rbbox = world.get("bbox") if isinstance(world, dict) else None
            centroid = world.get("centroid") if isinstance(world, dict) else None
            topo_refs = (iface or {}).get("topology_refs") if isinstance((iface or {}).get("topology_refs"), dict) else {}
            status = (rec or {}).get("resolution_status", "unresolved")
            if status == "unresolved" or not rbbox:
                warnings.append(f"unresolved_interface_preserve_warning:{iid}")
            cells = _cells_of_bbox(rbbox, bbox, grid, frame, dimension) if (rbbox and bbox and grid and frame) else []
            regions.append({
                "region_id": f"preserve_{iid or cid}",
                "reason": "proxy_connection_preserve_reason",
                "connection_id": cid,
                "connection_type": conn.get("type"),
                "interface_id": iid,
                "part_id": selected_part_id,
                "semantic_role": role,
                "topology_refs": topo_refs,
                "world_bbox": rbbox,
                "world_centroid": centroid,
                "resolution_status": status,
                "preserve_min_density": 0.95,
                "cells": cells,
                "proxy_derived": True,
            })
    return regions, warnings


def _result_guidance(
    *,
    selected_part_id: str,
    result_map: dict[str, Any],
    use_result_guidance: bool,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    preserve: list[dict[str, Any]] = []
    stiffness: list[dict[str, Any]] = []
    recorded_low: list[dict[str, Any]] = []
    for r in _as_list(result_map.get("mapped_results")):
        if not isinstance(r, dict) or str(r.get("part_id")) != selected_part_id:
            continue
        conf = str(r.get("confidence") or "low").lower()
        entry = {
            "region_id": r.get("region_id"),
            "part_id": r.get("part_id"),
            "interface_id": r.get("interface_id"),
            "connection_id": r.get("connection_id"),
            "load_case_id": r.get("load_case_id"),
            "result_type": r.get("result_type"),
            "quantity": r.get("quantity") or r.get("result_type"),
            "value": r.get("value"),
            "unit": r.get("unit"),
            "confidence": conf,
            "mapping_method": r.get("mapping_method"),
            "location": r.get("location"),
            "source_ir_node": r.get("source_ir_node"),
            "proxy_derived": bool(r.get("proxy_derived") or r.get("connection_id")),
            "enforced": bool(use_result_guidance and conf in _ENFORCEABLE_CONFIDENCE),
        }
        rtype = str(r.get("result_type") or "").lower()
        if conf not in _ENFORCEABLE_CONFIDENCE:
            recorded_low.append(entry)
            warnings.append(f"low_confidence_result_guidance_recorded:{r.get('region_id')}")
        if rtype in _STRESS_TYPES:
            preserve.append(entry)
        elif rtype in _DEFLECTION_TYPES:
            stiffness.append(entry)
    for u in _as_list(result_map.get("unmapped_regions")):
        if isinstance(u, dict):
            warnings.append(f"unmapped_region_diagnostic:{u.get('region_id')}")
    return {
        "available": bool(preserve or stiffness or recorded_low),
        "advisory_only": not use_result_guidance,
        "use_result_guidance": bool(use_result_guidance),
        "preserve_or_reinforce_regions": preserve,
        "stiffness_sensitive_regions": stiffness,
        "recorded_low_confidence_regions": recorded_low,
        "sources": {"consumed": [ASSEMBLY_RESULT_MAP_PATH]},
    }, warnings


def _derive_bcs(
    *,
    selected_part_id: str,
    assembly_model: dict[str, Any],
    preserve_regions: list[dict[str, Any]],
    bbox: list[float],
    grid: dict[str, Any],
    frame: dict[str, Any],
    dimension: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    diagnostics: list[str] = []
    iface_regions = {r.get("interface_id"): r for r in preserve_regions}
    supports: list[dict[str, Any]] = []
    loads: list[dict[str, Any]] = []
    bc = assembly_model.get("boundary_conditions") if isinstance(assembly_model.get("boundary_conditions"), dict) else {}
    for s in _as_list(bc.get("supports")):
        if not isinstance(s, dict) or str(s.get("part_id")) != selected_part_id:
            continue
        region = iface_regions.get(s.get("interface_id"))
        cells = region.get("cells") if region else []
        if cells:
            supports.append({"cells": cells, "from": s, "proxy_derived": True})
    for ld in _as_list(bc.get("loads")):
        if not isinstance(ld, dict) or str(ld.get("part_id")) != selected_part_id:
            continue
        region = iface_regions.get(ld.get("interface_id"))
        cells = region.get("cells") if region else []
        direction = ld.get("direction") or ld.get("vector") or [0.0, -1.0, 0.0]
        value = float(ld.get("value_n") or ld.get("magnitude") or ld.get("value") or 1.0)
        if not cells and ld.get("world_centroid"):
            cells = [_cell_of_point(ld["world_centroid"], bbox, grid, frame, dimension)]
        if not cells:
            continue
        if dimension == "3d":
            loads.append({
                "cells": cells,
                "fx": value * float(direction[0]), "fy": value * float(direction[1]), "fz": value * float(direction[2]),
                "from": ld, "proxy_derived": True,
            })
        else:
            u, v, w = _axis_index(frame["u_axis"]), _axis_index(frame["v_axis"]), _axis_index(frame["out_of_plane_axis"])
            fx, fy, fw = value * float(direction[u]), value * float(direction[v]), value * float(direction[w])
            if fx or fy:
                loads.append({"cells": cells, "fx": fx, "fy": fy, "from": ld, "proxy_derived": True})
            elif fw:
                warnings.append(f"load_on_interface_{ld.get('interface_id')}_out_of_plane_skipped")
    # Load transfer through fixture/reference connection acts as support on selected part.
    for r in preserve_regions:
        if r.get("semantic_role") == "load_face":
            continue
        if r.get("connection_type") in {"rigid_tie", "bonded", "bolted_proxy", "welded_proxy"} and r.get("cells"):
            if not any(s.get("from", {}).get("interface_id") == r.get("interface_id") for s in supports):
                supports.append({
                    "cells": r["cells"],
                    "from": {"interface_id": r.get("interface_id"), "connection_id": r.get("connection_id"), "type": "proxy_connection_support"},
                    "proxy_derived": True,
                })
    if not supports or not loads:
        diagnostics.append("missing_loads_supports")
    return {"supports": supports, "loads": loads}, diagnostics, warnings


def derive_assembly_topopt_problem(
    *,
    assembly: dict[str, Any],
    part_registry: dict[str, Any],
    connection_graph: dict[str, Any] | None = None,
    interface_resolution: dict[str, Any] | None = None,
    connection_geometry: dict[str, Any] | None = None,
    assembly_cae_model: dict[str, Any] | None = None,
    assembly_result_map: dict[str, Any] | None = None,
    topology_by_part: dict[str, dict[str, dict[str, Any]]] | None = None,
    selected_part_id: str | None = None,
    dimension: str = "2d",
    resolution: int = 48,
    resolution_3d: int = 16,
    volfrac: float = 0.5,
    penalty: float = 3.0,
    rmin: float = 1.5,
    max_iters: int = 40,
    use_result_guidance: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """Derive assembly-aware topopt setup and optional standard optimizer problem."""
    del connection_graph  # reserved for future graph-specific heuristics
    assembly = assembly if isinstance(assembly, dict) else {}
    part_registry = part_registry if isinstance(part_registry, dict) else {}
    interface_resolution = interface_resolution if isinstance(interface_resolution, dict) else {}
    connection_geometry = connection_geometry if isinstance(connection_geometry, dict) else {}
    assembly_cae_model = assembly_cae_model if isinstance(assembly_cae_model, dict) else {}
    assembly_result_map = assembly_result_map if isinstance(assembly_result_map, dict) else {}
    topology_by_part = topology_by_part or {}
    diagnostics: list[str] = []
    warnings: list[str] = []

    target, candidates, d, w = _select_design_part(
        assembly=assembly, registry=part_registry, selected_part_id=selected_part_id)
    diagnostics.extend(d)
    warnings.extend(w)
    if target is None:
        problem = _empty_problem(
            status="needs_user_input",
            diagnostics=diagnostics,
            warnings=warnings,
            candidates=candidates,
            selected_part_id=selected_part_id,
        )
        return problem, _diag(problem), None
    pid = str(target.get("part_id") or target.get("id"))
    topo = topology_by_part.get(pid, {})
    bbox = _part_bbox_from_topology(topo)
    if not topo:
        diagnostics.append("missing_topology")
    if not bbox:
        diagnostics.append("missing_design_space_bbox")
    geom = target.get("geometry_ref")
    if geom and not str(geom).lower().endswith((".step", ".stp", ".json", ".shape_ir.json", ".shape.json")):
        diagnostics.append("unsupported_geometry_ref")
        warnings.append("unsupported_geometry_ref")
    if not bbox:
        problem = _empty_problem(
            status="needs_user_input",
            diagnostics=diagnostics,
            warnings=warnings,
            candidates=candidates,
            selected_part_id=pid,
            target=target,
        )
        return problem, _diag(problem), None

    dim = "3d" if str(dimension).lower() == "3d" else "2d"
    grid, frame = _grid_frame(bbox, dimension=dim, resolution=resolution, resolution_3d=resolution_3d)
    preserve_regions, pw = _derive_preserve_regions(
        selected_part_id=pid,
        assembly=assembly,
        interface_resolution=interface_resolution,
        connection_geometry=connection_geometry,
        grid=grid,
        frame=frame,
        bbox=bbox,
        dimension=dim,
    )
    warnings.extend(pw)
    result_guidance, gw = _result_guidance(
        selected_part_id=pid,
        result_map=assembly_result_map,
        use_result_guidance=use_result_guidance,
    )
    warnings.extend(gw)
    bcs, bd, bw = _derive_bcs(
        selected_part_id=pid,
        assembly_model=assembly_cae_model,
        preserve_regions=preserve_regions,
        bbox=bbox,
        grid=grid,
        frame=frame,
        dimension=dim,
    )
    diagnostics.extend(bd)
    warnings.extend(bw)
    runnable = bool(bcs.get("supports") and bcs.get("loads"))
    status = "ready" if runnable else "needs_user_input"
    target_block = {
        "part_id": pid,
        "geometry_ref": target.get("geometry_ref"),
        "source_ir_node": target.get("source_ir_node"),
        "role": target.get("role"),
        "editable": target.get("editable", True),
        "topology_available": bool(topo),
        "design_space_bbox": bbox,
        "design_space_node": target.get("source_ir_node") or pid,
    }
    standard = None
    if runnable:
        standard = {
            "grid": grid,
            "volfrac": volfrac,
            "penalty": penalty,
            "rmin": rmin,
            "max_iters": max_iters,
            "objective": "compliance_minimization",
            "bcs": bcs,
            "design_space_node": target_block["design_space_node"],
            "source_ir_node": target.get("source_ir_node") or pid,
            "load_case_id": (assembly_cae_model or {}).get("load_case_id") or "assembly_load_case_1",
            "material": target.get("material"),
            "constraints": {
                "preserve_regions": preserve_regions,
                "preserve_min_density": 0.95,
                "derived_from_assembly_proxy_model": True,
            },
            "result_guidance": result_guidance,
            "use_result_guidance": bool(use_result_guidance),
            "preserve_min_density": 0.95,
            "derivation": {
                "source": "assembly_cae_v0",
                "selected_part_id": pid,
                "frame": frame,
                "design_space_bbox": bbox,
                "derived": True,
                "warnings": warnings,
                "limitations": list(_LIMITATIONS),
                "proxy_load_transfer": any(x.get("proxy_derived") for x in _as_list(bcs.get("supports")) + _as_list(bcs.get("loads"))),
                "derived_from_assembly_proxy_model": True,
                "contact_physics_modeled": False,
                "bolt_preload_modeled": False,
            },
        }
    problem = {
        "format": "aieng.assembly_topopt_problem",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "generated_at_utc": _now(),
        "status": status,
        "selected_part_id": pid,
        "target_part": target_block,
        "candidate_parts": [
            {"part_id": c.get("part_id") or c.get("id"), "role": c.get("role"), "editable": c.get("editable", True)}
            for c in candidates
        ],
        "dimension_recommendation": dim,
        "grid": grid,
        "frame": frame,
        "bcs": bcs,
        "preserve_regions": preserve_regions,
        "preserve_mask_guidance": {
            "available": bool(any(r.get("cells") for r in preserve_regions)),
            "preserve_min_density": 0.95,
            "cell_regions": [{"region_id": r.get("region_id"), "cells": r.get("cells", [])} for r in preserve_regions],
        },
        "result_guidance": result_guidance,
        "standard_problem_emitted": standard is not None,
        "diagnostics": diagnostics,
        "warnings": warnings,
        "limitations": list(_LIMITATIONS),
        "provenance": {
            "created_by": "aieng.assembly_topopt_v0",
            "source_artifacts": list(_SOURCE_ARTIFACTS),
            "derived_from_assembly_proxy_model": True,
            "contact_physics_modeled": False,
            "bolt_preload_modeled": False,
            "production_ready": False,
        },
    }
    return problem, _diag(problem), standard


def _empty_problem(
    *,
    status: str,
    diagnostics: list[str],
    warnings: list[str],
    candidates: list[dict[str, Any]],
    selected_part_id: str | None,
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "format": "aieng.assembly_topopt_problem",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "generated_at_utc": _now(),
        "status": status,
        "selected_part_id": selected_part_id,
        "target_part": target,
        "candidate_parts": [
            {"part_id": c.get("part_id") or c.get("id"), "role": c.get("role"), "editable": c.get("editable", True)}
            for c in candidates
        ],
        "standard_problem_emitted": False,
        "diagnostics": diagnostics,
        "warnings": warnings,
        "limitations": list(_LIMITATIONS),
        "provenance": {
            "created_by": "aieng.assembly_topopt_v0",
            "source_artifacts": list(_SOURCE_ARTIFACTS),
            "derived_from_assembly_proxy_model": True,
            "contact_physics_modeled": False,
            "bolt_preload_modeled": False,
            "production_ready": False,
        },
    }


def _diag(problem: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "aieng.assembly_topopt_derivation",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "status": problem.get("status"),
        "selected_part_id": problem.get("selected_part_id"),
        "diagnostics": problem.get("diagnostics") or [],
        "warnings": problem.get("warnings") or [],
        "summary": {
            "candidate_count": len(problem.get("candidate_parts") or []),
            "preserve_region_count": len(problem.get("preserve_regions") or []),
            "standard_problem_emitted": bool(problem.get("standard_problem_emitted")),
        },
        "limitations": list(_LIMITATIONS),
        "provenance": problem.get("provenance") or {},
    }


def _update_manifest(manifest: dict[str, Any], problem: dict[str, Any], standard: dict[str, Any] | None) -> dict[str, Any]:
    manifest = manifest if isinstance(manifest, dict) else {"format": "aieng.conversion_manifest"}
    asm = manifest.setdefault("assembly", {})
    if not isinstance(asm, dict):
        asm = {}
        manifest["assembly"] = asm
    asm["assembly_topopt_status"] = problem.get("status")
    asm["assembly_topopt_selected_part_id"] = problem.get("selected_part_id")
    asm["assembly_topopt_standard_problem_emitted"] = standard is not None
    asm["assembly_topopt_limitations"] = list(_LIMITATIONS)
    return manifest


def write_assembly_topopt_problem(
    package_path: str | Path,
    *,
    selected_part_id: str | None = None,
    dimension: str = "2d",
    resolution: int = 48,
    resolution_3d: int = 16,
    volfrac: float = 0.5,
    penalty: float = 3.0,
    rmin: float = 1.5,
    max_iters: int = 40,
    use_result_guidance: bool = False,
    emit_standard: bool = True,
) -> dict[str, Any]:
    """Read package assembly artifacts, derive/write assembly topopt setup."""
    package_path = Path(package_path)
    if not package_path.exists():
        return {"assembly_present": False, "reason": "package not found"}
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            if ASSEMBLY_IR_PATH not in names:
                return {"assembly_present": False}
            assembly = _read_json(zf, names, ASSEMBLY_IR_PATH) or {}
            part_registry = _read_json(zf, names, PART_REGISTRY_PATH) or {}
            connection_graph = _read_json(zf, names, CONNECTION_GRAPH_PATH) or {}
            interface_resolution = _read_json(zf, names, INTERFACE_RESOLUTION_PATH) or {}
            connection_geometry = _read_json(zf, names, ASSEMBLY_CONNECTION_GEOMETRY_PATH) or {}
            assembly_cae_model = _read_json(zf, names, ASSEMBLY_CAE_MODEL_PATH) or {}
            assembly_result_map = _read_json(zf, names, ASSEMBLY_RESULT_MAP_PATH) or {}
            manifest = _read_json(zf, names, CONVERSION_MANIFEST_PATH) or {"format": "aieng.conversion_manifest"}
            topology_by_part = _build_topology_by_part(zf, names, assembly)
    except Exception as exc:  # noqa: BLE001
        return {"assembly_present": False, "error": f"{type(exc).__name__}: {exc}"}

    problem, diag, standard = derive_assembly_topopt_problem(
        assembly=assembly,
        part_registry=part_registry,
        connection_graph=connection_graph,
        interface_resolution=interface_resolution,
        connection_geometry=connection_geometry,
        assembly_cae_model=assembly_cae_model,
        assembly_result_map=assembly_result_map,
        topology_by_part=topology_by_part,
        selected_part_id=selected_part_id,
        dimension=dimension,
        resolution=resolution,
        resolution_3d=resolution_3d,
        volfrac=volfrac,
        penalty=penalty,
        rmin=rmin,
        max_iters=max_iters,
        use_result_guidance=use_result_guidance,
    )
    members = {
        ASSEMBLY_TOPOPT_PROBLEM_PATH: _dumps(problem),
        ASSEMBLY_TOPOPT_DERIVATION_PATH: _dumps(diag),
        CONVERSION_MANIFEST_PATH: _dumps(_update_manifest(manifest, problem, standard if emit_standard else None)),
    }
    if standard is not None and emit_standard:
        members[STANDARD_TOPOPT_PROBLEM_PATH] = _dumps(standard)
    _replace_members(package_path, members)
    return {
        "assembly_present": True,
        "status": problem.get("status"),
        "selected_part_id": problem.get("selected_part_id"),
        "standard_problem_emitted": bool(standard is not None and emit_standard),
        "diagnostics": problem.get("diagnostics") or [],
        "warnings": problem.get("warnings") or [],
        "artifacts": sorted(members.keys()),
        "problem": problem,
        "standard_problem": standard if emit_standard else None,
    }
