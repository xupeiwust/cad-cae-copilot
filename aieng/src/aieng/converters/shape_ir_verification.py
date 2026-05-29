"""Unified Shape IR verification.

Audits a converted/compiled `.aieng` package and emits
`diagnostics/shape_ir_verification.json`: a per-node + package-level report that
honestly states, for each Shape IR node and the whole model, what backend ran,
which representation kind was produced, whether artifacts exist, how lossy the
result is, and whether B-Rep claims are real (vs mesh evidence dressed up as
B-Rep). It does NOT run a CAD kernel/mesher — it only inspects what was written.

Crucially this never *pretends*: mesh outputs (SDF/Manifold) are reported as
region-level mesh evidence, not analytic B-Rep topology.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

from .shape_ir import _shape_nodes, _node_id, _node_kind, resolve_representation

VERIFICATION_PATH = "diagnostics/shape_ir_verification.json"

_SHAPE_IR_MEMBER = "geometry/shape_ir.json"
_TOPOLOGY_MEMBER = "geometry/topology_map.json"
_FEATURE_MEMBER = "graph/feature_graph.json"
_MANIFEST_MEMBER = "provenance/conversion_manifest.json"
_SOURCE_MEMBERS = {
    "brep_build123d": "geometry/source.py",
    "nurbs_brep": "geometry/source.py",
    "implicit_sdf": "geometry/sdf_source.py",
    "manifold_mesh": "geometry/manifold_source.py",
}
_ARTIFACTS_CHECKED = (
    _SHAPE_IR_MEMBER,
    "geometry/source.py",
    "geometry/sdf_source.py",
    "geometry/manifold_source.py",
    "geometry/generated.step",
    "geometry/preview.stl",
    "geometry/preview.glb",
    _TOPOLOGY_MEMBER,
    _FEATURE_MEMBER,
    _MANIFEST_MEMBER,
)

# canonical representation -> reported representation_kind
_REPR_KIND = {
    "brep_build123d": "brep",
    "nurbs_brep": "nurbs_brep",
    "manifold_mesh": "mesh",
    "implicit_sdf": "implicit_field",
}
# representation_kind -> lossiness / cad-editability / geometry kind
_LOSSINESS = {"brep": "none", "nurbs_brep": "none", "mesh": "low", "implicit_field": "medium", "unknown": "high"}
_CAD_EDITABLE = {"brep": True, "nurbs_brep": True, "mesh": False, "implicit_field": False, "unknown": False}
_GEOMETRY_KIND = {"brep": "brep", "nurbs_brep": "brep", "mesh": "mesh", "implicit_field": "mesh", "unknown": "none"}
# node kind -> expected B-Rep surface_type (only where a clear expectation exists)
_EXPECTED_SURFACE_TYPE = {
    "nurbs_surface": "bspline", "bspline_surface": "bspline", "nurbs_patch": "bspline",
    "patch": "bspline", "surface": "bspline", "nurbs": "bspline",
}


def _read_member(zf: zipfile.ZipFile, name: str, names: set[str]) -> bytes | None:
    if name not in names:
        return None
    try:
        return zf.read(name)
    except Exception:
        return None


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    raw = _read_member(zf, name, names)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def verify_shape_ir_package(package_path: str | Path) -> dict[str, Any]:
    """Return the Shape IR verification report for a package (does not write it)."""
    package_path = Path(package_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "generated_at_utc": now,
        "verifier": "shape_ir_verification",
    }
    if not package_path.exists():
        report["status"] = "error"
        report["error"] = f"package not found: {package_path}"
        return report

    with zipfile.ZipFile(package_path, "r") as zf:
        names = set(zf.namelist())
        payload = _read_json(zf, _SHAPE_IR_MEMBER, names) or {}
        topology = _read_json(zf, _TOPOLOGY_MEMBER, names) or {}
        manifest = _read_json(zf, _MANIFEST_MEMBER, names) or {}
        artifacts = {name: (name in names) for name in _ARTIFACTS_CHECKED}
        # source text for per-node "compiled" detection
        rep_resolved = resolve_representation(payload if isinstance(payload, dict) else {})
        source_member = _SOURCE_MEMBERS.get(rep_resolved["representation"], "geometry/source.py")
        source_text = ""
        raw_src = _read_member(zf, source_member, names)
        if raw_src is not None:
            source_text = raw_src.decode("utf-8", errors="replace")

    nodes = _shape_nodes(payload) if isinstance(payload, dict) else []

    # ── representation / runtime / execution (prefer recorded manifest values) ──
    sdm = (manifest.get("source") or {}).get("source_document_metadata") or {}
    representation = str(sdm.get("representation") or rep_resolved["representation"])
    requested = str(sdm.get("requested_representation") or rep_resolved["requested_representation"])
    runtime = str(sdm.get("compile_runtime") or rep_resolved["runtime"])
    fallback = bool(sdm.get("representation_fallback", rep_resolved["fallback"]))
    geom_exec = manifest.get("geometry_execution") or {}
    executed = bool(geom_exec.get("executed"))
    backend = str(geom_exec.get("backend") or runtime)
    repr_kind = _REPR_KIND.get(representation, "unknown")
    geometry_kind = str(geom_exec.get("geometry_kind") or (_GEOMETRY_KIND[repr_kind] if executed else "none"))

    # capability level: max achieved level in the conversion manifest
    achieved = manifest.get("achieved_capability_levels") or []
    level_nums = [int(lvl.get("level")) for lvl in achieved if isinstance(lvl, dict) and isinstance(lvl.get("level"), int)]
    capability_level = f"L{max(level_nums)}" if level_nums else "L0"

    # ── topology inspection ──
    entities = topology.get("entities") if isinstance(topology, dict) else []
    entities = entities if isinstance(entities, list) else []
    faces = [e for e in entities if isinstance(e, dict) and e.get("type") == "face"]
    observed_surface_types = sorted({str(f.get("surface_type")) for f in faces if f.get("surface_type")})
    mapped_node_ids = sorted({str(e.get("source_ir_node")) for e in entities if e.get("source_ir_node")})
    topo_meta = topology.get("metadata") if isinstance(topology, dict) else {}
    topo_meta = topo_meta if isinstance(topo_meta, dict) else {}
    real_step_parsing = bool(topo_meta.get("real_step_parsing"))

    # ── per-node checks ──
    node_reports: list[dict[str, Any]] = []
    degraded = 0
    for index, node in enumerate(nodes, start=1):
        nid = _node_id(node, index)
        kind = _node_kind(node)
        compiled = (f"Shape IR node: {nid}" in source_text) or (f"Shape IR NURBS node: {nid}" in source_text)
        expected_surface = _EXPECTED_SURFACE_TYPE.get(kind)
        node_reports.append({
            "id": nid,
            "kind": kind,
            "representation_kind": repr_kind,
            "compiled": compiled,
            "source_ir_node_mapped": nid in mapped_node_ids,
            "expected_surface_type": expected_surface,
            "status": "ok" if compiled else "uncompiled",
        })
        if not compiled:
            degraded += 1
    # bbox-proxy degradations are emitted as comments by the compilers
    bbox_proxy_count = source_text.count("bbox proxy")

    # ── surface-type expectation (aggregate; per-node linkage is PR2/object_registry) ──
    nurbs_expected = repr_kind == "nurbs_brep" or any(
        _node_kind(n) in _EXPECTED_SURFACE_TYPE for n in nodes
    )
    nurbs_bspline_ok: bool | None
    if nurbs_expected and executed and geometry_kind == "brep":
        nurbs_bspline_ok = "bspline" in observed_surface_types
    else:
        nurbs_bspline_ok = None

    # ── honesty check: mesh outputs must not claim analytic B-Rep ──
    analytic_types = {"plane", "cylinder", "cone", "sphere", "torus", "bspline", "bezier"}
    brep_topology_not_faked = True
    if geometry_kind == "mesh":
        # a mesh result must declare itself a mesh and not present analytic faces
        declared_mesh = (not real_step_parsing) and ("mesh" in str(topo_meta.get("extraction_mode", "")))
        claims_analytic = any(t in analytic_types for t in observed_surface_types)
        brep_topology_not_faked = declared_mesh and not claims_analytic

    # ── status + warnings ──
    warnings: list[str] = []
    if fallback:
        warnings.append(f"representation '{requested}' is not registered; fell back to build123d.")
    uncompiled = [n["id"] for n in node_reports if not n["compiled"]]
    if uncompiled:
        warnings.append(f"{len(uncompiled)} node(s) not found in generated source: {uncompiled}")
    if bbox_proxy_count:
        warnings.append(f"{bbox_proxy_count} node(s) degraded to a bbox proxy in the generated source.")
    if geometry_kind == "mesh":
        warnings.append("mesh evidence: faces are region-level, not analytic B-Rep faces.")
        if not brep_topology_not_faked:
            warnings.append("INTEGRITY: mesh output appears to claim analytic B-Rep topology.")
    if executed and not mapped_node_ids and repr_kind in ("brep", "nurbs_brep"):
        warnings.append("executed B-Rep topology has no per-node source_ir_node links (deferred to object_registry).")
    if nurbs_bspline_ok is False:
        warnings.append("NURBS expected but no 'bspline' face observed in executed topology.")

    if fallback:
        status = "fallback"
    elif executed:
        status = "ok"
    elif source_text:
        status = "skipped"  # compiled source emitted but not executed (runner not run)
    else:
        status = "incomplete"

    return {
        **report,
        "status": status,
        "representation": representation,
        "requested_representation": requested,
        "representation_kind": repr_kind,
        "runtime": runtime,
        "backend": backend,
        "executed": executed,
        "fallback": fallback,
        "geometry_kind": geometry_kind,
        "lossiness": _LOSSINESS.get(repr_kind, "high"),
        "cad_editable": _CAD_EDITABLE.get(repr_kind, False),
        "capability_level": capability_level,
        "artifacts": artifacts,
        "node_count": len(nodes),
        "nodes": node_reports,
        "source_ir_node_mapping": {
            "present_in_topology": bool(mapped_node_ids),
            "mapped_node_ids": mapped_node_ids,
            "note": (
                "Projected topology carries source_ir_node per node; executed B-Rep/mesh "
                "topology does not — per-node linkage is established by the object registry."
            ),
        },
        "surface_type_check": {
            "expected_bspline_for_nurbs": nurbs_expected,
            "observed_surface_types": observed_surface_types,
            "nurbs_bspline_ok": nurbs_bspline_ok,
        },
        "checks": {
            "node_coverage": {"total": len(nodes), "compiled": len(nodes) - len(uncompiled)},
            "artifacts_present": all(artifacts.get(m, False) for m in (_SHAPE_IR_MEMBER, _TOPOLOGY_MEMBER)),
            "mesh_lossiness_declared": (geometry_kind != "mesh") or (_LOSSINESS.get(repr_kind) in {"low", "medium", "high"}),
            "brep_topology_not_faked": brep_topology_not_faked,
            "degraded_node_count": bbox_proxy_count,
        },
        "warnings": warnings,
    }


def write_shape_ir_verification(package_path: str | Path) -> dict[str, Any]:
    """Compute the verification report and write it to
    ``diagnostics/shape_ir_verification.json`` inside the package. Returns the
    report. Best-effort: re-raises only if the package cannot be rewritten."""
    package_path = Path(package_path)
    report = verify_shape_ir_package(package_path)
    if not package_path.exists():
        return report
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != VERIFICATION_PATH:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(VERIFICATION_PATH, payload)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return report
