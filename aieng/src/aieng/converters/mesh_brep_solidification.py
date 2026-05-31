"""Conservative mesh-derived B-Rep sewing, STEP export, and roundtrip checks.

Starts from the PR34 stitching plan and validated analytic face candidates.
Honesty rules:
- sewn shells are not solids,
- partial/invalid shells do not export STEP,
- only an OCC-valid closed solid writes ``geometry/reconstructed.step``.
Freeform/NURBS fitting and production CAD certification are out of scope.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.mesh_brep_face_generation import PARTIAL_BREP_FACES_PATH
from aieng.converters.mesh_brep_reconstruction import MESH_BREP_PLAN_PATH, PARTIAL_BREP_SURFACES_PATH
from aieng.converters.mesh_brep_stitching import (
    MESH_BREP_STITCHING_PLAN_PATH,
    MESH_BREP_STITCHING_READINESS_PATH,
)
from aieng.converters.mesh_reconstruction_readiness import MESH_RECONSTRUCTION_READINESS_PATH
from aieng.converters.mesh_region_segmentation import MESH_REGION_GRAPH_PATH
from aieng.converters.mesh_surface_fitting import MESH_SURFACE_FIT_PATH

MESH_BREP_SEWING_PATH = "diagnostics/mesh_brep_sewing.json"
RECONSTRUCTED_SHELL_STATUS_PATH = "geometry/reconstructed_shell_status.json"
RECONSTRUCTED_STEP_PATH = "geometry/reconstructed.step"
RECONSTRUCTED_TOPOLOGY_PATH = "geometry/reconstructed_topology_map.json"
MESH_BREP_STEP_EXPORT_PATH = "diagnostics/mesh_brep_step_export.json"
MESH_BREP_ROUNDTRIP_PATH = "diagnostics/mesh_brep_roundtrip_verification.json"
CONVERSION_MANIFEST_PATH = "provenance/conversion_manifest.json"
TOPOLOGY_MAP_PATH = "geometry/topology_map.json"

_DEFAULT_SEWING_TOLERANCE = 1.0e-5
_AREA_TOL = 1.0e-9
_SOURCE_ARTIFACTS = [
    "geometry/shape_ir.json",
    MESH_REGION_GRAPH_PATH,
    MESH_SURFACE_FIT_PATH,
    MESH_RECONSTRUCTION_READINESS_PATH,
    MESH_BREP_PLAN_PATH,
    PARTIAL_BREP_SURFACES_PATH,
    PARTIAL_BREP_FACES_PATH,
    MESH_BREP_STITCHING_PLAN_PATH,
    MESH_BREP_STITCHING_READINESS_PATH,
    MESH_BREP_SEWING_PATH,
]


def _honesty(
    *,
    shell_created: bool = False,
    solid_created: bool = False,
    step_exported: bool = False,
    cad_editable: str | bool = False,
) -> dict[str, Any]:
    return {
        "source_is_mesh_derived": True,
        "shell_created": bool(shell_created),
        "solid_created": bool(solid_created),
        "step_exported": bool(step_exported),
        "cad_editable": cad_editable,
        "production_ready": False,
        "source_mesh_remains_lossy": True,
    }


def _occ() -> dict[str, Any] | None:
    try:
        from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt
        from OCP.BRepBuilderAPI import (
            BRepBuilderAPI_MakeFace,
            BRepBuilderAPI_MakePolygon,
            BRepBuilderAPI_MakeSolid,
            BRepBuilderAPI_Sewing,
        )
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepGProp import BRepGProp
        from OCP.Geom import Geom_CylindricalSurface
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        return {
            "Pnt": gp_Pnt,
            "Dir": gp_Dir,
            "Ax3": gp_Ax3,
            "MakePolygon": BRepBuilderAPI_MakePolygon,
            "MakeFace": BRepBuilderAPI_MakeFace,
            "Sewing": BRepBuilderAPI_Sewing,
            "MakeSolid": BRepBuilderAPI_MakeSolid,
            "Cyl": Geom_CylindricalSurface,
            "Analyzer": BRepCheck_Analyzer,
            "GProps": GProp_GProps,
            "BRepGProp": BRepGProp,
            "Explorer": TopExp_Explorer,
            "FACE": TopAbs_FACE,
            "SHELL": TopAbs_SHELL,
            "EDGE": TopAbs_EDGE,
            "TopoDS": TopoDS,
            "STEPWriter": STEPControl_Writer,
            "STEPAsIs": STEPControl_AsIs,
            "RetDone": IFSelect_RetDone,
        }
    except Exception:
        return None


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    try:
        return json.loads(zf.read(name).decode("utf-8"))
    except Exception:
        return None


def _read_package_inputs(package_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"package_path": str(package_path), "missing_inputs": []}
    if not package_path.exists():
        out["missing_inputs"] = ["package"]
        return out
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            out["names"] = names
            for key, path in {
                "faces_doc": PARTIAL_BREP_FACES_PATH,
                "surfaces_doc": PARTIAL_BREP_SURFACES_PATH,
                "stitching_plan": MESH_BREP_STITCHING_PLAN_PATH,
                "stitching_readiness": MESH_BREP_STITCHING_READINESS_PATH,
                "reconstruction_plan": MESH_BREP_PLAN_PATH,
                "surface_fit": MESH_SURFACE_FIT_PATH,
                "conversion_manifest": CONVERSION_MANIFEST_PATH,
            }.items():
                out[key] = _read_json(zf, path, names)
                if (
                    path
                    in {
                        PARTIAL_BREP_FACES_PATH,
                        PARTIAL_BREP_SURFACES_PATH,
                        MESH_BREP_STITCHING_PLAN_PATH,
                        MESH_BREP_STITCHING_READINESS_PATH,
                    }
                    and not isinstance(out[key], dict)
                ):
                    out["missing_inputs"].append(path)
    except Exception as exc:  # noqa: BLE001
        out["read_error"] = f"{type(exc).__name__}: {exc}"
        out["missing_inputs"] = ["package_readable"]
    return out


def _base_provenance(inputs: dict[str, Any]) -> dict[str, Any]:
    src: dict[str, Any] = {}
    for key in ("stitching_plan", "faces_doc", "surfaces_doc", "reconstruction_plan", "surface_fit"):
        doc = inputs.get(key)
        if isinstance(doc, dict) and isinstance(doc.get("provenance"), dict):
            src = doc["provenance"]
            break
    return {
        "source_mesh_artifact": src.get("source_mesh_artifact"),
        "source_ir_node": src.get("source_ir_node"),
        "design_space_node": src.get("design_space_node"),
        "runtime": src.get("runtime"),
        "source_artifacts": list(_SOURCE_ARTIFACTS),
        "representation_kind": "mesh",
        "geometry_kind": "mesh",
        "limitations": [
            "Mesh-to-CAD reconstruction is conservative and mesh-derived/lossy.",
            "Partial shells are not solids and are not exported as STEP.",
            "Only a closed OCC-valid solid may be exported as geometry/reconstructed.step.",
            "No production CAD certification, original design history, or freeform/NURBS fitting is claimed.",
        ],
    }


def _dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((float(a[k]) - float(b[k])) ** 2 for k in range(3)))


def _dedup_loop(loop: list[Any]) -> list[list[float]]:
    out: list[list[float]] = []
    for p in loop or []:
        q = [float(p[0]), float(p[1]), float(p[2])]
        if not out or _dist(q, out[-1]) > 1e-9:
            out.append(q)
    if len(out) >= 2 and _dist(out[0], out[-1]) < 1e-9:
        out.pop()
    return out


def _face_area(occ: dict[str, Any], face: Any) -> float:
    props = occ["GProps"]()
    occ["BRepGProp"].SurfaceProperties_s(face, props)
    return float(props.Mass())


def _make_plane_face(occ: dict[str, Any], cand: dict[str, Any]) -> tuple[Any | None, str | None]:
    loop = _dedup_loop((cand.get("boundary") or {}).get("loop_world") or [])
    if len(loop) < 3:
        return None, "plane boundary has < 3 distinct points"
    try:
        mp = occ["MakePolygon"]()
        for p in loop:
            mp.Add(occ["Pnt"](p[0], p[1], p[2]))
        mp.Close()
        if not mp.IsDone():
            return None, "could not build a closed boundary polygon"
        mf = occ["MakeFace"](mp.Wire(), True)
        if not mf.IsDone():
            return None, "BRepBuilderAPI_MakeFace failed for planar wire"
        face = mf.Face()
        valid = bool(occ["Analyzer"](face).IsValid())
        area = _face_area(occ, face)
        if not valid or area <= _AREA_TOL:
            return None, f"invalid or degenerate plane face (valid={valid}, area={area:.3g})"
        return face, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _perp_axis(axis: list[float]) -> list[float]:
    import numpy as np

    a = np.asarray(axis, dtype=float)
    a = a / (np.linalg.norm(a) or 1.0)
    return list(a)


def _make_cylinder_face(occ: dict[str, Any], cand: dict[str, Any]) -> tuple[Any | None, str | None]:
    a = cand.get("analytic") or {}
    b = cand.get("boundary") or {}
    origin, axis, radius = a.get("axis_origin"), a.get("axis_direction"), a.get("radius")
    axial = a.get("axial_range") or b.get("axial_range")
    angular = b.get("angular_range") or a.get("angular_range")
    if not (origin and axis and radius and axial and angular):
        return None, "cylinder boundary insufficient for OCC face (axis/radius/axial/angular required)"
    try:
        u0, u1 = float(angular[0]), float(angular[1])
        a0, a1 = float(axial[0]), float(axial[1])
        if u1 <= u0 or a1 <= a0:
            return None, "empty cylinder angular or axial span"
        ax = _perp_axis(axis)
        shifted_origin = [float(origin[k]) + a0 * ax[k] for k in range(3)]
        cyl = occ["Cyl"](
            occ["Ax3"](occ["Pnt"](*shifted_origin), occ["Dir"](*[float(x) for x in ax])),
            float(radius),
        )
        mf = occ["MakeFace"](cyl, u0, u1, 0.0, a1 - a0, 1e-6)
        if not mf.IsDone():
            return None, "BRepBuilderAPI_MakeFace failed for cylindrical patch"
        face = mf.Face()
        valid = bool(occ["Analyzer"](face).IsValid())
        area = _face_area(occ, face)
        if not valid or area <= _AREA_TOL:
            return None, f"invalid or degenerate cylinder face (valid={valid}, area={area:.3g})"
        return face, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _build_occ_faces(
    occ: dict[str, Any], faces_doc: dict[str, Any], surfaces_doc: dict[str, Any]
) -> tuple[list[tuple[str, Any]], list[dict[str, Any]]]:
    candidates = {str(c.get("face_candidate_id")): c for c in (surfaces_doc.get("face_candidates") or [])}
    out: list[tuple[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for rec in faces_doc.get("faces") or []:
        fid = str(rec.get("face_id"))
        if rec.get("status") != "generated":
            skipped.append({"face_id": fid, "reason": rec.get("reason") or "face record is not generated"})
            continue
        cand = candidates.get(fid)
        if not cand:
            skipped.append({"face_id": fid, "reason": "missing source face candidate boundary"})
            continue
        if rec.get("face_type") == "plane":
            shape, reason = _make_plane_face(occ, cand)
        elif rec.get("face_type") == "cylinder":
            shape, reason = _make_cylinder_face(occ, cand)
        else:
            shape, reason = None, f"unsupported face_type {rec.get('face_type')!r}"
        if shape is None:
            skipped.append({"face_id": fid, "reason": reason})
        else:
            out.append((fid, shape))
    return out, skipped


def _count_shapes(occ: dict[str, Any], shape: Any, kind: Any) -> int:
    exp = occ["Explorer"](shape, kind)
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def _first_shell(occ: dict[str, Any], shape: Any) -> Any | None:
    exp = occ["Explorer"](shape, occ["SHELL"])
    if not exp.More():
        return None
    try:
        return occ["TopoDS"].Shell_s(exp.Current())
    except AttributeError:
        return occ["TopoDS"].Shell(exp.Current())
    except Exception:
        return exp.Current()


def _edge_diagnostics(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "unmatched_edges": (inputs.get("stitching_plan") or {}).get("unmatched_edges") or [],
        "large_gaps": [
            b
            for b in ((inputs.get("stitching_readiness") or {}).get("blocking_issues") or [])
            if b.get("issue") == "large_edge_gaps"
        ],
        "readiness_blocking_issues": (inputs.get("stitching_readiness") or {}).get("blocking_issues") or [],
    }


def _source_face_records(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "face_id": rec.get("face_id"),
            "source_region_id": rec.get("source_region_id"),
            "source_surface_id": rec.get("source_surface_id"),
            "face_type": rec.get("face_type"),
            "status": rec.get("status"),
        }
        for rec in ((inputs.get("faces_doc") or {}).get("faces") or [])
        if isinstance(rec, dict)
    ]


def _empty_shell_status() -> dict[str, Any]:
    return {
        "format": "aieng.reconstructed_shell_status",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "shell_created": False,
        "shell_type": "failed",
        "closed": False,
        "valid": False,
        "solid_created": False,
        "step_exported": False,
        "cad_editable": "not_cad",
        "production_ready": False,
    }


def _failed_sewing(
    inputs: dict[str, Any],
    provenance: dict[str, Any],
    *,
    occ_available: bool,
    summary: dict[str, Any] | None = None,
    blocking: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    skipped_faces: list[dict[str, Any]] | None = None,
    tolerance: float = _DEFAULT_SEWING_TOLERANCE,
) -> dict[str, Any]:
    return {
        "format": "aieng.mesh_brep_sewing",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "occ_available": occ_available,
        "available": not bool(inputs.get("missing_inputs")),
        "summary": summary
        or {
            "shell_created": False,
            "shell_type": "failed",
            "face_count_in": 0,
            "face_count_sewn": 0,
            "free_edge_count": None,
            "closed": False,
            "valid": False,
            "sewing_tolerance": tolerance,
        },
        "skipped_faces": skipped_faces or [],
        "blocking_issues": blocking or [],
        "warnings": warnings or [],
        "stitching_summary": ((inputs.get("stitching_plan") or {}).get("summary") or {}),
        "edge_diagnostics": _edge_diagnostics(inputs),
        "source_face_records": _source_face_records(inputs),
        "provenance": {**provenance, **_honesty(cad_editable="not_cad")},
        "claim_boundary": "No shell/solid/STEP produced.",
    }


def _sew(
    inputs: dict[str, Any], *, tolerance: float = _DEFAULT_SEWING_TOLERANCE
) -> tuple[dict[str, Any], dict[str, Any], Any | None, dict[str, Any] | None]:
    provenance = _base_provenance(inputs)
    missing = list(inputs.get("missing_inputs") or [])
    occ = _occ()
    if missing or occ is None:
        warnings = []
        if missing:
            warnings.append(f"missing inputs: {', '.join(missing)}")
        if occ is None:
            warnings.append("OCC/OCP unavailable; sewing not attempted")
        return (
            _failed_sewing(
                inputs,
                provenance,
                occ_available=occ is not None,
                blocking=[{"issue": "missing_inputs", "detail": missing}] if missing else [],
                warnings=warnings,
                tolerance=tolerance,
            ),
            _empty_shell_status(),
            None,
            occ,
        )

    stitching_summary = (inputs.get("stitching_plan") or {}).get("summary") or {}
    if not stitching_summary.get("can_attempt_partial_shell"):
        return (
            _failed_sewing(
                inputs,
                provenance,
                occ_available=True,
                blocking=[{"issue": "stitching_not_ready", "detail": stitching_summary}],
                warnings=["stitching plan did not authorize even a partial shell attempt"],
                tolerance=tolerance,
            ),
            _empty_shell_status(),
            None,
            occ,
        )

    occ_faces, skipped_faces = _build_occ_faces(occ, inputs["faces_doc"], inputs["surfaces_doc"])
    face_count_in = len([f for f in (inputs["faces_doc"].get("faces") or []) if f.get("status") == "generated"])
    if not occ_faces:
        return (
            _failed_sewing(
                inputs,
                provenance,
                occ_available=True,
                summary={
                    "shell_created": False,
                    "shell_type": "failed",
                    "face_count_in": face_count_in,
                    "face_count_sewn": 0,
                    "free_edge_count": None,
                    "closed": False,
                    "valid": False,
                    "sewing_tolerance": tolerance,
                },
                blocking=[{"issue": "no_valid_occ_faces", "detail": len(skipped_faces)}],
                warnings=["no valid OCC faces could be rebuilt for sewing"],
                skipped_faces=skipped_faces,
                tolerance=tolerance,
            ),
            _empty_shell_status(),
            None,
            occ,
        )

    sewer = occ["Sewing"](float(tolerance))
    for _fid, face in occ_faces:
        sewer.Add(face)
    try:
        sewer.Perform()
        sewn_shape = sewer.SewedShape()
    except Exception as exc:  # noqa: BLE001
        return (
            _failed_sewing(
                inputs,
                provenance,
                occ_available=True,
                summary={
                    "shell_created": False,
                    "shell_type": "failed",
                    "face_count_in": face_count_in,
                    "face_count_sewn": 0,
                    "free_edge_count": None,
                    "closed": False,
                    "valid": False,
                    "sewing_tolerance": tolerance,
                },
                blocking=[{"issue": "occ_sewing_failed", "detail": f"{type(exc).__name__}: {exc}"}],
                skipped_faces=skipped_faces,
                tolerance=tolerance,
            ),
            _empty_shell_status(),
            None,
            occ,
        )

    face_count_sewn = _count_shapes(occ, sewn_shape, occ["FACE"])
    shell_count = _count_shapes(occ, sewn_shape, occ["SHELL"])
    shell = _first_shell(occ, sewn_shape)
    free_edge_count = int(sewer.NbFreeEdges())
    closed = shell is not None and free_edge_count == 0
    valid = bool(occ["Analyzer"](shell if shell is not None else sewn_shape).IsValid())
    shell_created = shell is not None or face_count_sewn > 0
    shell_type = "closed_shell" if closed and valid else ("partial_shell" if shell_created else "failed")
    blockers: list[dict[str, Any]] = []
    if skipped_faces:
        blockers.append({"issue": "faces_skipped", "detail": len(skipped_faces)})
    if free_edge_count:
        blockers.append({"issue": "free_edges", "detail": free_edge_count})
    if not valid:
        blockers.append({"issue": "invalid_shell", "detail": "OCC BRepCheck_Analyzer reported invalid shell/shape"})
    summary = {
        "shell_created": bool(shell_created),
        "shell_type": shell_type,
        "face_count_in": face_count_in,
        "face_count_rebuilt": len(occ_faces),
        "face_count_sewn": face_count_sewn,
        "shell_count": shell_count,
        "free_edge_count": free_edge_count,
        "closed": bool(closed),
        "valid": bool(valid),
        "sewing_tolerance": tolerance,
        "occ_free_edges": free_edge_count,
        "occ_contiguous_edges": int(sewer.NbContigousEdges()),
        "occ_multiple_edges": int(sewer.NbMultipleEdges()),
        "occ_deleted_faces": int(sewer.NbDeletedFaces()),
        "occ_degenerated_shapes": int(sewer.NbDegeneratedShapes()),
    }
    sewing = {
        "format": "aieng.mesh_brep_sewing",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "occ_available": True,
        "available": True,
        "summary": summary,
        "skipped_faces": skipped_faces,
        "blocking_issues": blockers,
        "warnings": [],
        "stitching_summary": stitching_summary,
        "edge_diagnostics": _edge_diagnostics(inputs),
        "source_faces": [fid for fid, _ in occ_faces],
        "source_face_records": _source_face_records(inputs),
        "provenance": {**provenance, **_honesty(shell_created=shell_created, cad_editable="shell_candidate_only")},
        "claim_boundary": "Sewn shell candidate only. No solid/STEP is produced by the sewing stage.",
    }
    shell_status = {
        **_empty_shell_status(),
        "shell_created": bool(shell_created),
        "shell_type": shell_type,
        "closed": bool(closed),
        "valid": bool(valid),
        "face_count_sewn": face_count_sewn,
        "free_edge_count": free_edge_count,
        "source_faces": [fid for fid, _ in occ_faces],
        "provenance": sewing["provenance"],
    }
    return sewing, shell_status, shell, occ


def _write_step_bytes(occ: dict[str, Any], shape: Any) -> tuple[bytes | None, str | None]:
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        writer = occ["STEPWriter"]()
        transfer_status = writer.Transfer(shape, occ["STEPAsIs"])
        if transfer_status != occ["RetDone"]:
            return None, f"STEP transfer failed (status={transfer_status})"
        write_status = writer.Write(path)
        if write_status != occ["RetDone"]:
            return None, f"STEP writer failed (status={write_status})"
        data = Path(path).read_bytes()
        if not data.startswith(b"ISO-10303-21"):
            return None, "STEP writer produced unexpected non-STEP header"
        return data, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _make_solid_and_export(
    sewing: dict[str, Any], shell: Any | None, occ: dict[str, Any] | None, provenance: dict[str, Any]
) -> tuple[dict[str, Any], bytes | None]:
    s = sewing.get("summary") or {}
    reason = ""
    if occ is None:
        reason = "OCC/OCP unavailable"
    elif shell is None:
        reason = "no shell available from sewing"
    elif not (s.get("shell_created") and s.get("closed") and s.get("valid")):
        reason = f"sewing did not produce a valid closed shell (shell_type={s.get('shell_type')})"
    if reason:
        return (
            {
                "format": "aieng.mesh_brep_step_export",
                "schema_version": "0.1",
                "attempted": False,
                "solid_created": False,
                "solid_valid": False,
                "step_exported": False,
                "step_path": None,
                "reason": reason,
                "summary": {"export_allowed": False},
                "provenance": {**provenance, **_honesty(shell_created=bool(s.get("shell_created")), cad_editable="not_cad")},
                "claim_boundary": "No STEP exported because there is no valid closed OCC solid.",
            },
            None,
        )
    try:
        maker = occ["MakeSolid"]()
        maker.Add(shell)
        maker.Build()
        if not maker.IsDone():
            raise RuntimeError("BRepBuilderAPI_MakeSolid did not complete")
        solid = maker.Solid()
        valid = bool(occ["Analyzer"](solid).IsValid())
    except Exception as exc:  # noqa: BLE001
        return (
            {
                "format": "aieng.mesh_brep_step_export",
                "schema_version": "0.1",
                "attempted": True,
                "solid_created": False,
                "solid_valid": False,
                "step_exported": False,
                "step_path": None,
                "reason": f"solid creation failed: {type(exc).__name__}: {exc}",
                "summary": {"export_allowed": False},
                "provenance": {**provenance, **_honesty(shell_created=True, cad_editable="not_cad")},
                "claim_boundary": "No STEP exported because solid creation failed.",
            },
            None,
        )
    if not valid:
        return (
            {
                "format": "aieng.mesh_brep_step_export",
                "schema_version": "0.1",
                "attempted": True,
                "solid_created": True,
                "solid_valid": False,
                "step_exported": False,
                "step_path": None,
                "reason": "OCC BRepCheck_Analyzer reported invalid solid",
                "summary": {"export_allowed": False},
                "provenance": {**provenance, **_honesty(shell_created=True, solid_created=True, cad_editable="not_cad")},
                "claim_boundary": "No STEP exported because the solid is invalid.",
            },
            None,
        )
    step_bytes, err = _write_step_bytes(occ, solid)
    if err or not step_bytes:
        return (
            {
                "format": "aieng.mesh_brep_step_export",
                "schema_version": "0.1",
                "attempted": True,
                "solid_created": True,
                "solid_valid": True,
                "step_exported": False,
                "step_path": None,
                "reason": err or "empty STEP bytes",
                "summary": {"export_allowed": False},
                "provenance": {**provenance, **_honesty(shell_created=True, solid_created=True, cad_editable="not_cad")},
                "claim_boundary": "Solid was valid, but STEP export failed; no STEP artifact recorded.",
            },
            None,
        )
    return (
        {
            "format": "aieng.mesh_brep_step_export",
            "format_version": FORMAT_VERSION,
            "schema_version": "0.1",
            "attempted": True,
            "solid_created": True,
            "solid_valid": True,
            "step_exported": True,
            "step_path": RECONSTRUCTED_STEP_PATH,
            "step_size_bytes": len(step_bytes),
            "reason": None,
            "summary": {"export_allowed": True, "geometry_kind": "brep", "representation_kind": "brep"},
            "provenance": {
                **provenance,
                **_honesty(shell_created=True, solid_created=True, step_exported=True, cad_editable="reconstructed_brep_step"),
            },
            "claim_boundary": "Validated closed OCC solid exported as mesh-derived reconstructed STEP; not production CAD certified.",
        },
        step_bytes,
    )


def _extract_topology(step_bytes: bytes) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from aieng.geometry.backend import OCCGeometryBackend

        topo = OCCGeometryBackend().extract_topology(step_bytes)
        meta = topo.setdefault("metadata", {})
        meta["source_geometry"] = RECONSTRUCTED_STEP_PATH
        meta["mesh_brep_reconstruction"] = True
        meta["production_ready"] = False
        return topo, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _bbox_from_candidates(surfaces_doc: dict[str, Any] | None) -> list[float] | None:
    pts: list[list[float]] = []
    for cand in (surfaces_doc or {}).get("face_candidates") or []:
        for p in (cand.get("boundary") or {}).get("loop_world") or []:
            try:
                pts.append([float(p[0]), float(p[1]), float(p[2])])
            except Exception:
                pass
    if not pts:
        return None
    return [min(p[i] for p in pts) for i in range(3)] + [max(p[i] for p in pts) for i in range(3)]


def _bbox_diag(bb: list[float] | None) -> float:
    if not bb or len(bb) < 6:
        return 1.0
    return math.sqrt(sum((float(bb[i + 3]) - float(bb[i])) ** 2 for i in range(3))) or 1.0


def _roundtrip_verify(
    inputs: dict[str, Any],
    export_diag: dict[str, Any],
    step_bytes: bytes | None,
    topology_map: dict[str, Any] | None,
    topology_error: str | None,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    if not export_diag.get("step_exported") or not step_bytes:
        status = "warning"
        warnings.append(export_diag.get("reason") or "no reconstructed STEP artifact exported")
        if ((inputs.get("stitching_plan") or {}).get("summary") or {}).get("can_attempt_closed_shell"):
            status = "failed"
    elif topology_map is None:
        status = "failed"
        errors.append(topology_error or "topology extraction failed")
    else:
        expected_count = len([f for f in (inputs.get("faces_doc") or {}).get("faces") or [] if f.get("status") == "generated"])
        observed_faces = [e for e in topology_map.get("entities", []) if e.get("type") == "face"]
        if len(observed_faces) != expected_count:
            warnings.append(f"observed face count {len(observed_faces)} differs from expected {expected_count}")
        expected_types = sorted(
            {
                str(c.get("surface_type"))
                for c in (inputs.get("surfaces_doc") or {}).get("face_candidates") or []
                if c.get("surface_type") in {"plane", "cylinder"}
            }
        )
        observed_types = sorted({str(f.get("surface_type")) for f in observed_faces if f.get("surface_type")})
        missing_types = sorted(set(expected_types) - set(observed_types))
        if missing_types:
            warnings.append(f"expected surface types missing after roundtrip: {missing_types}")
        src_bbox = _bbox_from_candidates(inputs.get("surfaces_doc"))
        body_bboxes = [
            e.get("bounding_box")
            for e in topology_map.get("entities", [])
            if e.get("type") == "solid" and isinstance(e.get("bounding_box"), list)
        ]
        if src_bbox and body_bboxes:
            delta = max(abs(float(src_bbox[i]) - float(body_bboxes[0][i])) for i in range(6))
            if delta > max(_bbox_diag(src_bbox) * 0.02, 1e-5):
                warnings.append(f"bbox mismatch exceeds tolerance: max_delta={delta:.6g}")
        elif src_bbox:
            warnings.append("source bbox available but roundtrip solid bbox missing")
        status = "passed" if not warnings else "warning"
    return {
        "format": "aieng.mesh_brep_roundtrip_verification",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": status,
        "step_path": RECONSTRUCTED_STEP_PATH if export_diag.get("step_exported") else None,
        "checks": {
            "step_exported": bool(export_diag.get("step_exported")),
            "topology_extracted": topology_map is not None,
            "expected_face_candidate_count": len(
                [f for f in (inputs.get("faces_doc") or {}).get("faces") or [] if f.get("status") == "generated"]
            ),
            "observed_face_count": len([e for e in (topology_map or {}).get("entities", []) if e.get("type") == "face"]),
            "expected_surface_types": sorted(
                {
                    str(c.get("surface_type"))
                    for c in (inputs.get("surfaces_doc") or {}).get("face_candidates") or []
                    if c.get("surface_type") in {"plane", "cylinder"}
                }
            ),
            "observed_surface_types": sorted(
                {
                    str(e.get("surface_type"))
                    for e in (topology_map or {}).get("entities", [])
                    if e.get("type") == "face" and e.get("surface_type")
                }
            ),
        },
        "warnings": warnings,
        "errors": errors,
        "limitations": provenance.get("limitations") or [],
        "provenance": {
            **provenance,
            **_honesty(
                shell_created=bool(export_diag.get("provenance", {}).get("shell_created")),
                solid_created=bool(export_diag.get("solid_created")),
                step_exported=bool(export_diag.get("step_exported")),
                cad_editable="reconstructed_brep_step" if export_diag.get("step_exported") else "not_cad",
            ),
        },
    }


def _replace_members(path: Path, members: dict[str, bytes]) -> None:
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


def _json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _update_manifest(inputs: dict[str, Any], export_diag: dict[str, Any], topology_written: bool) -> dict[str, Any]:
    manifest = inputs.get("conversion_manifest") if isinstance(inputs.get("conversion_manifest"), dict) else {}
    manifest.setdefault("format", "aieng.conversion_manifest")
    base = _base_provenance(inputs)
    recon = {
        "status": "exported" if export_diag.get("step_exported") else "not_exported",
        "production_ready": False,
        "source_mesh_remains_lossy": True,
        "reconstruction_level": "full_closed_solid" if export_diag.get("step_exported") else "partial_or_failed",
        "source_artifacts": list(_SOURCE_ARTIFACTS),
        "artifacts": [MESH_BREP_SEWING_PATH, MESH_BREP_STEP_EXPORT_PATH, MESH_BREP_ROUNDTRIP_PATH],
        "limitations": base.get("limitations") or [],
    }
    if export_diag.get("step_exported"):
        artifacts = [RECONSTRUCTED_STEP_PATH, MESH_BREP_SEWING_PATH, MESH_BREP_STEP_EXPORT_PATH, MESH_BREP_ROUNDTRIP_PATH]
        if topology_written:
            artifacts.extend([TOPOLOGY_MAP_PATH, RECONSTRUCTED_TOPOLOGY_PATH])
        recon["artifacts"] = artifacts
        manifest["geometry_execution"] = {
            "executed": True,
            "backend": "mesh_brep_reconstruction",
            "actual_runtime": "mesh_brep_reconstruction",
            "source": "mesh_brep_reconstruction",
            "geometry_kind": "brep",
            "representation_kind": "brep",
            "artifacts": artifacts,
            "source_artifacts": list(_SOURCE_ARTIFACTS),
            "production_ready": False,
            "reconstruction_level": "full_closed_solid",
            "source_mesh_remains_lossy": True,
            "source_ir_node": base.get("source_ir_node"),
            "design_space_node": base.get("design_space_node"),
        }
    manifest["mesh_brep_reconstruction"] = recon
    return manifest


def reconstruct_brep_step(package_path: str | Path, *, tolerance: float = _DEFAULT_SEWING_TOLERANCE) -> dict[str, Any]:
    """Run sewing -> solid -> STEP -> roundtrip verification on a package.

    Diagnostics are written in all cases. ``geometry/reconstructed.step`` and B-Rep
    topology are written only when a valid closed OCC solid is produced.
    """
    package_path = Path(package_path)
    inputs = _read_package_inputs(package_path)
    provenance = _base_provenance(inputs)
    sewing, shell_status, shell, occ = _sew(inputs, tolerance=tolerance)
    export_diag, step_bytes = _make_solid_and_export(sewing, shell, occ, provenance)
    topology_map = None
    topology_error = None
    if step_bytes:
        topology_map, topology_error = _extract_topology(step_bytes)
        if topology_error:
            export_diag.setdefault("warnings", []).append(f"topology extraction failed: {topology_error}")
    roundtrip = _roundtrip_verify(inputs, export_diag, step_bytes, topology_map, topology_error, provenance)
    if export_diag.get("step_exported") and roundtrip["status"] == "failed":
        export_diag.setdefault("warnings", []).append("roundtrip verification failed; see diagnostics")
    members: dict[str, bytes] = {
        MESH_BREP_SEWING_PATH: _json_bytes(sewing),
        RECONSTRUCTED_SHELL_STATUS_PATH: _json_bytes(shell_status),
        MESH_BREP_STEP_EXPORT_PATH: _json_bytes(export_diag),
        MESH_BREP_ROUNDTRIP_PATH: _json_bytes(roundtrip),
    }
    if step_bytes and export_diag.get("step_exported"):
        members[RECONSTRUCTED_STEP_PATH] = step_bytes
    if topology_map is not None and export_diag.get("step_exported"):
        members[RECONSTRUCTED_TOPOLOGY_PATH] = _json_bytes(topology_map)
        members[TOPOLOGY_MAP_PATH] = _json_bytes(topology_map)
    members[CONVERSION_MANIFEST_PATH] = _json_bytes(
        _update_manifest(inputs, export_diag, topology_map is not None and export_diag.get("step_exported"))
    )
    if package_path.exists():
        _replace_members(package_path, members)
    return {
        "status": "ok",
        "sewing": sewing,
        "step_export": export_diag,
        "roundtrip_verification": roundtrip,
        "written_artifacts": sorted(members),
    }
