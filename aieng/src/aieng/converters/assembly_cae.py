"""Assembly-level CAE v0: simplified proxy model, optional deck/execution, mapping.

This module is intentionally contract-first and solver-neutral.  It consumes the
Assembly IR v0 artifacts plus interface-resolution / connection-geometry evidence
and emits a simplified assembly CAE model.  Connections remain proxies:
``rigid_tie``/``bonded`` become tie-like proxies, ``bolted_proxy`` never models
preload, ``contact_proxy`` is unsupported unless a future simplified contact proxy
is explicitly added.  Production contact accuracy is never claimed.
"""
from __future__ import annotations

import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.assembly_interface_resolution import (
    ASSEMBLY_CONNECTION_GEOMETRY_PATH,
    INTERFACE_RESOLUTION_PATH,
)
from aieng.converters.credibility import classify_credibility
from aieng.converters.assembly_ir import (
    ASSEMBLY_CAE_DRAFT_PATH,
    ASSEMBLY_IR_PATH,
    CONNECTION_GRAPH_PATH,
    CONVERSION_MANIFEST_PATH,
    PART_REGISTRY_PATH,
)
from aieng.converters.cae_result_contract import (
    CAE_CONTRACT_VERSION,
    COMPUTED_METRICS_FORMAT,
    FIELD_REGIONS_FORMAT,
)

ASSEMBLY_CAE_MODEL_PATH = "simulation/assembly_cae_model.json"
ASSEMBLY_CAE_MODEL_DIAGNOSTICS_PATH = "diagnostics/assembly_cae_model_diagnostics.json"
ASSEMBLY_SOLVER_DECK_PATH = "simulation/assembly_calculix.inp"
ASSEMBLY_SOLVER_DECK_DIAGNOSTICS_PATH = "diagnostics/assembly_solver_deck_generation.json"
ASSEMBLY_SOLVER_EXECUTION_DIAGNOSTICS_PATH = "diagnostics/assembly_solver_execution.json"
ASSEMBLY_COMPUTED_METRICS_PATH = "analysis/assembly_computed_metrics.json"
ASSEMBLY_FIELD_REGIONS_PATH = "analysis/assembly_field_regions.json"
ASSEMBLY_RESULT_MAP_PATH = "analysis/assembly_result_map.json"
ASSEMBLY_RESULT_MAPPING_DIAGNOSTICS_PATH = "diagnostics/assembly_result_mapping.json"
ASSEMBLY_BOLT_PRELOAD_DIAGNOSTICS_PATH = "diagnostics/assembly_bolt_preload.json"

# Optional generic/fake result fixtures accepted by the v0 normalizer.  They are
# not solver-native; they already describe neutral assembly-level observations.
ASSEMBLY_GENERIC_SOLVER_RESULT_PATHS = (
    "analysis/assembly_solver_result.json",
    "results/assembly_solver_result.json",
    "simulation/assembly_solver_result.json",
)

_SUPPORTED_PROXY_TYPES = {
    "tie_proxy",
    "bonded_proxy",
    "bolted_connector_proxy",
    "welded_tie_proxy",
    "spring_proxy",
}
_PROXY_MAP = {
    "rigid_tie": "tie_proxy",
    "bonded": "bonded_proxy",
    "bolted_proxy": "bolted_connector_proxy",
    "welded_proxy": "welded_tie_proxy",
    "spring_proxy": "spring_proxy",
    "contact_proxy": "unsupported_contact_proxy",
    "unknown": "unsupported_contact_proxy",
}
_SOURCE_ARTIFACTS = [
    ASSEMBLY_IR_PATH,
    PART_REGISTRY_PATH,
    CONNECTION_GRAPH_PATH,
    INTERFACE_RESOLUTION_PATH,
    ASSEMBLY_CONNECTION_GEOMETRY_PATH,
    ASSEMBLY_CAE_DRAFT_PATH,
]
_LIMITATIONS = [
    "Assembly CAE v0 uses simplified proxy connections only.",
    "Nonlinear/frictional contact is not modeled.",
    "Bolt preload is not modeled.",
    "Proxy connection stresses are proxy-derived and not real contact stress.",
    "Assembly meshing and solver execution are best-effort and optional.",
    "production_ready=false for all assembly CAE v0 artifacts.",
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


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    if not package_path.exists() or not members:
        return
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


def _conn_id(conn: dict[str, Any], idx: int) -> str:
    return str(conn.get("id") or conn.get("connection_id") or f"connection_{idx:03d}")


def _conn_load_transfer(conn: dict[str, Any]) -> bool:
    behaviors = [str(x) for x in _as_list(conn.get("behavior"))]
    if "load_transfer" in behaviors:
        return True
    if "positioning_only" in behaviors:
        return False
    return str(conn.get("type")) in {"rigid_tie", "bonded", "bolted_proxy", "welded_proxy", "spring_proxy"}


def _pos_num(value: Any) -> float | None:
    """Positive finite number, else None (bool rejected)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 and n == n else None


def _bolt_preload_intent(conn: dict[str, Any]) -> dict[str, Any]:
    """Read EXPLICIT bolt-preload intent off a connection.

    Preload is honored only when explicitly specified (``preload.axial_force_n``);
    it is never inferred from a bolt designation or BOM/standard-part entry.
    """
    preload = conn.get("preload")
    preload = preload if isinstance(preload, dict) else {}
    axial = _pos_num(preload.get("axial_force_n"))
    intent = axial is not None
    return {
        "intent_present": intent,
        "axial_force_n": axial,
        "method": str(preload.get("method") or "axial_force") if intent else None,
        "fastener_id": preload.get("fastener_id") or conn.get("fastener_id"),
        "modeled": False,  # v0 proxy deck cannot apply pretension; only deck/solver evidence flips this
    }


def _proxy_limitations(ctype: str, proxy_type: str, explicit: list[Any]) -> list[str]:
    out = [str(x) for x in explicit if x]
    if proxy_type == "bolted_connector_proxy":
        out.append("Bolted proxy is a connector/tie simplification; bolt preload is not modeled.")
    elif proxy_type == "welded_tie_proxy":
        out.append("Welded proxy is represented as a bonded/tie simplification.")
    elif proxy_type == "spring_proxy":
        out.append("Spring proxy is a simplified connector; local contact detail is not modeled.")
    elif proxy_type == "unsupported_contact_proxy":
        out.append(f"{ctype!r} is unsupported/draft-only in assembly CAE v0; no real contact physics is modeled.")
    elif proxy_type in {"tie_proxy", "bonded_proxy"}:
        out.append("Tie/bonded proxy transfers load kinematically; interface compliance is not modeled.")
    return sorted(set(out))


def _bbox_contains(bbox: Any, p: list[float], pad: float = 1e-6) -> bool:
    return isinstance(bbox, list) and len(bbox) == 6 and all(bbox[i] - pad <= p[i] <= bbox[i + 3] + pad for i in range(3))


def _bbox_center(bbox: list[float]) -> list[float]:
    return [(bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2, (bbox[2] + bbox[5]) / 2]


def _bbox_union(boxes: list[list[float]]) -> list[float] | None:
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
        max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes),
    ]


def _dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def _world_bbox(iface: dict[str, Any]) -> list[float] | None:
    b = ((iface.get("world") or {}).get("bbox") if isinstance(iface, dict) else None)
    return [float(x) for x in b] if isinstance(b, list) and len(b) == 6 else None


def _world_centroid(iface: dict[str, Any]) -> list[float] | None:
    c = ((iface.get("world") or {}).get("centroid") if isinstance(iface, dict) else None)
    return [float(x) for x in c] if isinstance(c, list) and len(c) == 3 else None


def _interface_record(
    iface: dict[str, Any],
    resolved: dict[str, Any] | None,
) -> dict[str, Any]:
    world = (resolved or {}).get("world") if isinstance(resolved, dict) else {}
    refs = iface.get("topology_refs") if isinstance(iface.get("topology_refs"), dict) else {}
    return {
        "interface_id": iface.get("id"),
        "part_id": iface.get("part_id"),
        "semantic_role": iface.get("semantic_role"),
        "topology_refs": refs or {},
        "resolved_topology_refs": {
            "resolution_status": (resolved or {}).get("resolution_status", "unresolved"),
            "topology_entity_count": (resolved or {}).get("topology_entity_count", 0),
            "unresolved_refs": (resolved or {}).get("unresolved_refs", []),
        },
        "world_centroid": world.get("centroid") if isinstance(world, dict) else None,
        "world_bbox": world.get("bbox") if isinstance(world, dict) else None,
        "world_normal": world.get("normal") if isinstance(world, dict) else None,
        "area": world.get("area") if isinstance(world, dict) else None,
        "resolution_status": (resolved or {}).get("resolution_status", "unresolved"),
    }


def build_assembly_cae_model(
    *,
    assembly: dict[str, Any] | None,
    part_registry: dict[str, Any] | None = None,
    connection_graph: dict[str, Any] | None = None,
    interface_resolution: dict[str, Any] | None = None,
    connection_geometry: dict[str, Any] | None = None,
    setup_draft: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a solver-neutral assembly CAE model plus diagnostics."""
    assembly = assembly if isinstance(assembly, dict) else {}
    part_registry = part_registry if isinstance(part_registry, dict) else {}
    connection_graph = connection_graph if isinstance(connection_graph, dict) else {}
    interface_resolution = interface_resolution if isinstance(interface_resolution, dict) else {}
    connection_geometry = connection_geometry if isinstance(connection_geometry, dict) else {}
    setup_draft = setup_draft if isinstance(setup_draft, dict) else {}
    warnings: list[str] = []
    needs_user_input: list[str] = []

    reg_by_part = {p.get("part_id"): p for p in _as_list(part_registry.get("parts")) if isinstance(p, dict)}
    parts = []
    for part in _as_list(assembly.get("parts")):
        if not isinstance(part, dict):
            continue
        pid = part.get("id")
        reg = reg_by_part.get(pid, {})
        material = part.get("material", reg.get("material"))
        if material is None:
            warnings.append(f"part '{pid}' has no material")
        parts.append({
            "part_id": pid,
            "role": part.get("role") or reg.get("role") or "external_context",
            "geometry_ref": part.get("geometry_ref") or reg.get("geometry_ref"),
            "mesh_ref": part.get("mesh_ref") or part.get("cae_mesh_ref") or reg.get("mesh_ref"),
            "transform": part.get("transform") or reg.get("transform"),
            "material": material,
            "editable": bool(reg.get("editable", part.get("editable", False))),
            "topology_available": bool(reg.get("topology_available") or part.get("topology_ref") or part.get("geometry_ref")),
            "topology_ref": part.get("topology_ref") or reg.get("topology_ref"),
            "source_ir_node": part.get("source_ir_node") or reg.get("source_ir_node"),
        })

    raw_ifaces = _collect_interfaces(assembly)
    resolved_by_id = (interface_resolution.get("interfaces") or {}) if isinstance(interface_resolution.get("interfaces"), dict) else {}
    interfaces = [
        _interface_record(iface, resolved_by_id.get(iid))
        for iid, iface in sorted(raw_ifaces.items())
    ]
    if raw_ifaces and not resolved_by_id:
        warnings.append("interface resolution artifact is missing; interfaces remain unresolved")

    geo_by_conn = {
        c.get("connection_id"): c for c in _as_list(connection_geometry.get("connections")) if isinstance(c, dict)
    }
    graph_by_conn = {
        e.get("id"): e for e in _as_list(connection_graph.get("edges")) if isinstance(e, dict)
    }
    conns = []
    for idx, conn in enumerate(_as_list(assembly.get("connections"))):
        if not isinstance(conn, dict):
            continue
        cid = _conn_id(conn, idx)
        ctype = str(conn.get("type") or "unknown")
        proxy_type = _PROXY_MAP.get(ctype, "unsupported_contact_proxy")
        geo = geo_by_conn.get(cid, {})
        gedge = graph_by_conn.get(cid, {})
        geometry_status = geo.get("geometry_status") or gedge.get("geometry_status") or "unknown"
        load_transfer = _conn_load_transfer(conn)
        disabled_reasons: list[str] = []
        if proxy_type not in _SUPPORTED_PROXY_TYPES:
            disabled_reasons.append("unsupported_proxy_type")
        if not load_transfer:
            disabled_reasons.append("positioning_only_no_load_transfer")
        if not (conn.get("interface_a") and conn.get("interface_b")):
            disabled_reasons.append("missing_interface")
        if geometry_status in {"invalid", "insufficient_data"}:
            disabled_reasons.append(f"geometry_{geometry_status}")
        for iid in (conn.get("interface_a"), conn.get("interface_b")):
            rec = resolved_by_id.get(iid)
            if iid and isinstance(rec, dict) and rec.get("resolution_status") == "unresolved":
                disabled_reasons.append("unresolved_interface")
        enabled = not disabled_reasons
        if "missing_interface" in disabled_reasons:
            needs_user_input.append(f"connection '{cid}' is missing interface references")
        elif any(r in disabled_reasons for r in ("geometry_invalid", "geometry_insufficient_data", "unresolved_interface")):
            needs_user_input.append(f"connection '{cid}' is not solver-enabled: {', '.join(disabled_reasons)}")
        conns.append({
            "connection_id": cid,
            "type": ctype,
            "proxy_model_type": proxy_type,
            "part_a": conn.get("part_a"),
            "part_b": conn.get("part_b"),
            "interface_a": conn.get("interface_a"),
            "interface_b": conn.get("interface_b"),
            "geometry_status": geometry_status,
            "geometry_reasons": geo.get("reasons") or gedge.get("geometry_reasons") or [],
            "load_transfer": bool(load_transfer),
            "enabled_for_solver": enabled,
            "disabled_reason": "; ".join(sorted(set(disabled_reasons))) if disabled_reasons else None,
            "limitations": _proxy_limitations(ctype, proxy_type, _as_list(conn.get("limitations"))),
            "bolt_preload": _bolt_preload_intent(conn) if ctype == "bolted_proxy" else None,
        })

    loads = []
    for item in _as_list(setup_draft.get("loads")):
        if isinstance(item, dict):
            loads.append({**item, "target_kind": "interface" if item.get("interface_id") else "part"})
    supports = []
    for item in _as_list(setup_draft.get("supports")):
        if isinstance(item, dict):
            supports.append({**item, "target_kind": "interface" if item.get("interface_id") else "part"})

    mesh_refs = [p.get("mesh_ref") for p in parts if p.get("mesh_ref")]
    model_status = "needs_user_input" if needs_user_input else "ready"
    if not parts:
        model_status = "needs_user_input"
        needs_user_input.append("assembly declares no parts")
    model = {
        "format": "aieng.assembly_cae_model",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "generated_at_utc": _now(),
        "status": model_status,
        "units": {"length": assembly.get("unit") or "mm"},
        "load_case_id": (setup_draft.get("load_case_id") or "assembly_load_case_1"),
        "parts": parts,
        "interfaces": interfaces,
        "connections": conns,
        "boundary_conditions": {
            "supports": supports,
            "loads": loads,
        },
        "solver_hints": {
            "recommended_solver": "calculix",
            "meshing_required": True,
            "mesh_refs_available": len(mesh_refs),
            "connection_strategy": "simplified_proxy_connections",
            "simplified_proxy_connections": True,
            "contact_physics_modeled": False,
            "bolt_preload_modeled": False,
            "production_ready": False,
        },
        "limitations": list(_LIMITATIONS),
        "provenance": {
            "created_by": "aieng.assembly_cae_v0",
            "source_artifacts": list(_SOURCE_ARTIFACTS),
            "assumptions": [
                "enabled proxy connections transfer load through simplified tie/connector/spring abstractions",
                "disabled or unresolved connections are not included in solver deck generation",
            ],
            "contract_version": "0.1",
            "solver_executed": False,
            "production_ready": False,
        },
    }
    diagnostics = {
        "format": "aieng.assembly_cae_model_diagnostics",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "status": model_status,
        "warnings": warnings,
        "needs_user_input": needs_user_input,
        "summary": {
            "part_count": len(parts),
            "interface_count": len(interfaces),
            "connection_count": len(conns),
            "enabled_connection_count": sum(1 for c in conns if c["enabled_for_solver"]),
            "disabled_connection_count": sum(1 for c in conns if not c["enabled_for_solver"]),
            "proxy_connection_types": sorted({c["proxy_model_type"] for c in conns}),
        },
        "limitations": list(_LIMITATIONS),
        "provenance": model["provenance"],
    }
    return model, diagnostics


def generate_assembly_solver_deck(
    model: dict[str, Any] | None,
    *,
    available_members: set[str] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Generate an optional simplified CalculiX deck when mesh refs exist.

    If assembly meshing/deck prerequisites are absent, returns ``(None, skipped)``
    and does not fake a deck.
    """
    model = model if isinstance(model, dict) else {}
    members = available_members
    enabled = [c for c in _as_list(model.get("connections")) if isinstance(c, dict) and c.get("enabled_for_solver")]
    parts = [p for p in _as_list(model.get("parts")) if isinstance(p, dict)]
    mesh_refs = [str(p.get("mesh_ref")) for p in parts if p.get("mesh_ref")]
    missing_mesh = [p.get("part_id") for p in parts if not p.get("mesh_ref")]
    missing_members = [m for m in mesh_refs if members is not None and m not in members]
    warnings: list[str] = []
    if not enabled:
        status = "skipped"
        reason = "no enabled simplified proxy connections"
    elif missing_mesh:
        status = "skipped"
        reason = "missing assembly part mesh references"
    elif missing_members:
        status = "skipped"
        reason = "mesh_ref members missing from package"
    else:
        status = "generated"
        reason = None

    diag = {
        "format": "aieng.assembly_solver_deck_generation",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "status": status,
        "solver": "calculix",
        "deck_path": ASSEMBLY_SOLVER_DECK_PATH if status == "generated" else None,
        "reason": reason,
        "warnings": warnings,
        "skipped_connections": [
            {"connection_id": c.get("connection_id"), "reason": c.get("disabled_reason")}
            for c in _as_list(model.get("connections")) if isinstance(c, dict) and not c.get("enabled_for_solver")
        ],
        "metadata": {
            "simplified_proxy_connections": True,
            "contact_physics_modeled": False,
            "bolt_preload_modeled": False,
            "production_ready": False,
        },
        "bolt_preload_intents_unsupported": [
            c.get("connection_id") for c in enabled
            if isinstance(c.get("bolt_preload"), dict) and c["bolt_preload"].get("intent_present")
        ],
        "limitations": list(_LIMITATIONS),
    }
    if status != "generated":
        return None, diag

    lines = [
        "** AIENG assembly CAE v0 simplified proxy deck",
        "** simplified_proxy_connections=true",
        "** contact_physics_modeled=false",
        "** bolt_preload_modeled=false",
        "** production_ready=false",
    ]
    for mesh in mesh_refs:
        lines.append(f"*INCLUDE, INPUT={mesh}")
    lines.append("*MATERIAL, NAME=AIENG_PLACEHOLDER")
    lines.append("*ELASTIC")
    lines.append("210000., 0.3")
    for conn in enabled:
        ctype = conn.get("proxy_model_type")
        if ctype == "spring_proxy":
            lines.extend([f"** SPRING PROXY {conn.get('connection_id')}: simplified connector placeholder", "*SPRING", "1.0"])
        else:
            lines.append(
                f"** TIE PROXY {conn.get('connection_id')}: {conn.get('interface_a')} -> {conn.get('interface_b')}"
            )
        bp = conn.get("bolt_preload") if isinstance(conn.get("bolt_preload"), dict) else None
        if bp and bp.get("intent_present"):
            lines.append(
                f"** BOLT PRELOAD INTENT {conn.get('connection_id')} axial_force_n={bp.get('axial_force_n')} "
                "NOT MODELED (proxy deck; *PRE-TENSION SECTION unsupported in v0)"
            )
    lines.append("*STEP")
    lines.append("*STATIC")
    lines.append("1., 1.")
    lines.append("*END STEP")
    return "\n".join(lines) + "\n", diag


def normalize_assembly_solver_result(native: dict[str, Any] | None, *, load_case_id: str = "assembly_load_case_1") -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize a generic/fake assembly solver result to neutral assembly artifacts."""
    native = native if isinstance(native, dict) else {}
    solver = native.get("solver") if isinstance(native.get("solver"), dict) else {
        "name": "generic_assembly",
        "version": None,
        "adapter": "assembly_generic_v0",
    }
    load_cases = []
    for lc in _as_list(native.get("load_cases")):
        if not isinstance(lc, dict):
            continue
        results = [r for r in _as_list(lc.get("results")) if isinstance(r, dict)]
        if not results and isinstance(lc.get("metrics"), dict):
            for metric, mv in lc["metrics"].items():
                if isinstance(mv, dict):
                    results.append({
                        "result_type": mv.get("result_type") or metric,
                        "metric": metric,
                        "max": mv.get("value", mv.get("max")),
                        "min": mv.get("min"),
                        "average": mv.get("average"),
                        "unit": mv.get("unit"),
                    })
        load_cases.append({"id": str(lc.get("id") or load_case_id), "results": results})
    if not load_cases and _as_list(native.get("results")):
        load_cases.append({"id": load_case_id, "results": [r for r in _as_list(native.get("results")) if isinstance(r, dict)]})
    regions = []
    for i, r in enumerate(_as_list(native.get("regions") or native.get("field_regions")), start=1):
        if not isinstance(r, dict):
            continue
        center = r.get("center") or r.get("location") or {}
        value = r.get("value") or r.get("magnitude") or {}
        regions.append({
            "id": str(r.get("id") or f"assembly_region_{i:03d}"),
            "result_type": str(r.get("result_type") or r.get("field") or "unknown"),
            "load_case_id": str(r.get("load_case_id") or (load_cases[0]["id"] if load_cases else load_case_id)),
            "center": {
                "x": float(center.get("x", 0.0)),
                "y": float(center.get("y", 0.0)),
                "z": float(center.get("z", 0.0)),
            },
            "bbox": r.get("bbox"),
            "value": {
                "peak": value.get("peak", value.get("value", value.get("max"))),
                "min": value.get("min"),
                "max": value.get("max", value.get("value", value.get("peak"))),
                "unit": value.get("unit"),
            },
            "node_count": r.get("node_count"),
            "part_hint": r.get("part_id") or r.get("part_hint"),
            "interface_hint": r.get("interface_id") or r.get("interface_hint"),
            "connection_hint": r.get("connection_id") or r.get("connection_hint"),
            "proxy_derived": bool(r.get("proxy_derived", r.get("connection_id") or r.get("connection_hint"))),
        })
    computed = {
        "format": COMPUTED_METRICS_FORMAT,
        "schema_version": CAE_CONTRACT_VERSION,
        "contract_version": CAE_CONTRACT_VERSION,
        "aieng_format_version": FORMAT_VERSION,
        "solver": solver,
        "load_cases": load_cases,
        "warnings": list(native.get("warnings") or []),
    }
    fields = {
        "format": FIELD_REGIONS_FORMAT,
        "schema_version": CAE_CONTRACT_VERSION,
        "contract_version": CAE_CONTRACT_VERSION,
        "aieng_format_version": FORMAT_VERSION,
        "solver": solver,
        "regions": regions,
        "warnings": list(native.get("warnings") or []),
    }
    return computed, fields


def execute_assembly_solver_v0(
    *,
    model: dict[str, Any] | None,
    deck_present: bool,
    generic_result: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    """Optional assembly execution wrapper.

    v0 does not launch CalculiX directly.  It records skipped/unavailable status
    unless a generic pre-normalized assembly result is present.
    """
    model = model if isinstance(model, dict) else {}
    if generic_result is not None:
        cm, fr = normalize_assembly_solver_result(generic_result, load_case_id=str(model.get("load_case_id") or "assembly_load_case_1"))
        status = "normalized_external_result"
        diag = {
            "format": "aieng.assembly_solver_execution",
            "format_version": FORMAT_VERSION,
            "contract_version": "0.1",
            "status": status,
            "solver_executed": False,
            "adapter": (cm.get("solver") or {}).get("adapter"),
            "solver": cm.get("solver"),
            "input_deck_path": ASSEMBLY_SOLVER_DECK_PATH if deck_present else None,
            "warnings": ["Generic assembly result normalized; no solver was executed by this wrapper."],
            "errors": [],
            "output_artifacts": [ASSEMBLY_COMPUTED_METRICS_PATH, ASSEMBLY_FIELD_REGIONS_PATH],
            "metadata": {"production_ready": False, "simplified_proxy_connections": True},
        }
        return cm, fr, diag
    reason = "assembly solver deck is absent" if not deck_present else "assembly solver runner is unavailable in v0"
    diag = {
        "format": "aieng.assembly_solver_execution",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "status": "skipped" if not deck_present else "unavailable",
        "solver_executed": False,
        "adapter": None,
        "solver": None,
        "input_deck_path": ASSEMBLY_SOLVER_DECK_PATH if deck_present else None,
        "warnings": [reason],
        "errors": [],
        "output_artifacts": [],
        "metadata": {
            "production_ready": False,
            "simplified_proxy_connections": True,
            "contact_physics_modeled": False,
            "bolt_preload_modeled": False,
        },
    }
    return None, None, diag


def map_assembly_results(
    *,
    computed_metrics: dict[str, Any] | None,
    field_regions: dict[str, Any] | None,
    model: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map neutral assembly field regions to parts/interfaces/connections."""
    computed_metrics = computed_metrics if isinstance(computed_metrics, dict) else {}
    field_regions = field_regions if isinstance(field_regions, dict) else {}
    model = model if isinstance(model, dict) else {}
    parts = [p for p in _as_list(model.get("parts")) if isinstance(p, dict)]
    interfaces = [i for i in _as_list(model.get("interfaces")) if isinstance(i, dict)]
    connections = [c for c in _as_list(model.get("connections")) if isinstance(c, dict)]
    iface_by_id = {i.get("interface_id"): i for i in interfaces}
    conns_by_iface: dict[str, list[dict[str, Any]]] = {}
    for c in connections:
        for iid in (c.get("interface_a"), c.get("interface_b")):
            if iid:
                conns_by_iface.setdefault(str(iid), []).append(c)
    part_bboxes: dict[str, list[float]] = {}
    for part in parts:
        boxes = [
            i.get("world_bbox") for i in interfaces
            if i.get("part_id") == part.get("part_id") and isinstance(i.get("world_bbox"), list)
        ]
        bb = _bbox_union(boxes) if boxes else None
        if bb:
            part_bboxes[str(part.get("part_id"))] = bb

    units: dict[str, str] = {}
    overall = []
    load_cases: list[str] = []
    for lc in _as_list(computed_metrics.get("load_cases")):
        if not isinstance(lc, dict):
            continue
        lc_id = str(lc.get("id") or "assembly_load_case_1")
        load_cases.append(lc_id)
        for r in _as_list(lc.get("results")):
            if isinstance(r, dict):
                if r.get("unit"):
                    units.setdefault(str(r.get("result_type") or "unknown"), str(r.get("unit")))
                overall.append({"load_case_id": lc_id, **r})

    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for region in _as_list(field_regions.get("regions")):
        if not isinstance(region, dict):
            continue
        center = region.get("center") or {}
        p = [float(center.get("x", 0.0)), float(center.get("y", 0.0)), float(center.get("z", 0.0))]
        value = region.get("value") or {}
        lc_id = str(region.get("load_case_id") or (load_cases[0] if load_cases else model.get("load_case_id") or "assembly_load_case_1"))
        base = {
            "region_id": region.get("id"),
            "load_case_id": lc_id,
            "result_type": str(region.get("result_type") or "unknown"),
            "value": value.get("peak", value.get("max")),
            "unit": value.get("unit"),
            "location": {"x": p[0], "y": p[1], "z": p[2]},
            "node_count": region.get("node_count"),
            "proxy_derived": bool(region.get("proxy_derived")),
        }

        candidate_ifaces = [i for i in interfaces if _bbox_contains(i.get("world_bbox"), p, pad=1e-6)]
        part_hits = [pid for pid, bb in part_bboxes.items() if _bbox_contains(bb, p, pad=1e-6)]
        method = "unmapped"
        confidence = "low"
        iface = None
        part_id = None
        if region.get("interface_hint") and region.get("interface_hint") in iface_by_id:
            iface = iface_by_id[region["interface_hint"]]
            part_id = iface.get("part_id")
            method, confidence = "interface_hint", "high"
        elif len(candidate_ifaces) == 1:
            iface = candidate_ifaces[0]
            part_id = iface.get("part_id")
            method, confidence = "interface_bbox_contains", "high"
        elif len(part_hits) == 1:
            part_id = part_hits[0]
            method, confidence = "part_bbox_contains", "high"
        elif candidate_ifaces:
            iface = candidate_ifaces[0]
            part_id = iface.get("part_id")
            method, confidence = "ambiguous_interface_bbox", "low"
        elif part_bboxes:
            nearest, best = None, math.inf
            for pid, bb in part_bboxes.items():
                d = _dist(_bbox_center(bb), p)
                if d < best:
                    nearest, best = pid, d
            part_id = nearest
            method, confidence = "nearest_part_centroid", "medium" if nearest else "low"

        if part_id is None and not iface:
            unmapped.append({**base, "reason": "no assembly part/interface geometry near region"})
            continue
        conn_ids: list[str] = []
        if iface:
            conn_ids = [str(c.get("connection_id")) for c in conns_by_iface.get(str(iface.get("interface_id")), [])]
        elif region.get("connection_hint"):
            conn_ids = [str(region.get("connection_hint"))]
        source_ir_node = next((p.get("source_ir_node") for p in parts if p.get("part_id") == part_id), None)
        mapped.append({
            **base,
            "part_id": part_id,
            "interface_id": iface.get("interface_id") if iface else region.get("interface_hint"),
            "connection_id": conn_ids[0] if len(conn_ids) == 1 else None,
            "connection_ids": conn_ids,
            "source_ir_node": source_ir_node,
            "topology_entities": ((iface or {}).get("resolved_topology_refs") or {}),
            "mapping_method": method,
            "confidence": confidence,
            "note": "proxy-derived connection result; not real contact stress" if (conn_ids or region.get("proxy_derived")) else None,
        })

    hotspot_parts = sorted({m["part_id"] for m in mapped if m.get("part_id")})
    hotspot_connections = sorted({c for m in mapped for c in _as_list(m.get("connection_ids")) if c})
    result_map = {
        "format": "aieng.assembly_result_map",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "generated_at_utc": _now(),
        "solver": field_regions.get("solver") or computed_metrics.get("solver") or {},
        "load_cases": sorted(set(load_cases)) or [str(model.get("load_case_id") or "assembly_load_case_1")],
        "units": units,
        "overall": overall,
        "mapped_results": mapped,
        "unmapped_regions": unmapped,
        "summary": {
            "mapped_part_count": len(hotspot_parts),
            "mapped_connection_count": len(hotspot_connections),
            "mapped_region_count": len(mapped),
            "unmapped_region_count": len(unmapped),
            "hotspot_parts": hotspot_parts,
            "hotspot_connections": hotspot_connections,
        },
        "limitations": list(_LIMITATIONS),
        "provenance": {
            "created_by": "aieng.assembly_result_mapping_v0",
            "source_artifacts": [ASSEMBLY_COMPUTED_METRICS_PATH, ASSEMBLY_FIELD_REGIONS_PATH, ASSEMBLY_CAE_MODEL_PATH],
            "solver_neutral": True,
            "contact_physics_modeled": False,
            "bolt_preload_modeled": False,
            "production_ready": False,
        },
        "credibility": classify_credibility(
            "proxy_assembly",
            contact_physics_modeled=False,
            bolt_preload_modeled=False,
            production_ready=False,
        ),
    }
    diagnostics = {
        "format": "aieng.assembly_result_mapping",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "status": "mapped" if mapped else ("skipped" if not _as_list(field_regions.get("regions")) else "unmapped"),
        "summary": result_map["summary"],
        "warnings": [] if mapped else ["No assembly field regions mapped."],
        "limitations": list(_LIMITATIONS),
    }
    return result_map, diagnostics


def _update_manifest(
    manifest: dict[str, Any],
    *,
    model_diag: dict[str, Any],
    deck_diag: dict[str, Any],
    exec_diag: dict[str, Any],
    mapping_diag: dict[str, Any],
) -> dict[str, Any]:
    manifest = manifest if isinstance(manifest, dict) else {}
    asm = manifest.setdefault("assembly", {})
    if not isinstance(asm, dict):
        asm = {}
        manifest["assembly"] = asm
    asm.update({
        "present": True,
        "assembly_cae_model_status": model_diag.get("status"),
        "solver_deck_status": deck_diag.get("status"),
        "solver_execution_status": exec_diag.get("status"),
        "assembly_result_mapping_status": mapping_diag.get("status"),
        "solver_executed": bool(exec_diag.get("solver_executed")),
        "is_proxy_model": True,
        "production_ready": False,
        "proxy_connection_limitations": list(_LIMITATIONS),
        "artifacts": [
            ASSEMBLY_CAE_MODEL_PATH,
            ASSEMBLY_CAE_MODEL_DIAGNOSTICS_PATH,
            ASSEMBLY_SOLVER_DECK_DIAGNOSTICS_PATH,
            ASSEMBLY_SOLVER_EXECUTION_DIAGNOSTICS_PATH,
            ASSEMBLY_RESULT_MAPPING_DIAGNOSTICS_PATH,
        ],
    })
    if deck_diag.get("deck_path"):
        asm["artifacts"].append(deck_diag["deck_path"])
    if mapping_diag.get("status") in {"mapped", "unmapped"}:
        asm["artifacts"].append(ASSEMBLY_RESULT_MAP_PATH)
    return manifest


def build_bolt_preload_report(model: dict[str, Any] | None, *, deck_status: str | None = None) -> dict[str, Any]:
    """Honest bolt-preload report for an assembly CAE model.

    Records EXPLICIT preload intent per bolted connection and whether it is
    actually modeled. In v0 the simplified proxy deck cannot apply pretension
    (no solid bolt geometry / ``*PRE-TENSION SECTION``), so every intent is
    reported ``unsupported`` and ``bolt_preload_modeled`` is false.

    Honesty invariants (#199):
    - preload is never inferred from a bolt designation / BOM entry — only an
      explicit ``preload.axial_force_n`` counts as intent;
    - ``bolt_preload_modeled`` is true ONLY when a connection's preload is
      actually represented in a generated deck (``modeled`` true), never from
      intent alone;
    - no fatigue / loosening / torque-to-preload claim is implied.
    """
    model = model if isinstance(model, dict) else {}
    connections: list[dict[str, Any]] = []
    with_intent = 0
    modeled_count = 0
    for conn in _as_list(model.get("connections")):
        if not isinstance(conn, dict) or conn.get("type") != "bolted_proxy":
            continue
        pre = conn.get("bolt_preload") if isinstance(conn.get("bolt_preload"), dict) else _bolt_preload_intent(conn)
        intent = bool(pre.get("intent_present"))
        modeled = bool(pre.get("modeled"))
        with_intent += int(intent)
        modeled_count += int(modeled)
        if modeled:
            status, reasons = "modeled", []
        elif intent:
            status = "unsupported"
            reasons = [
                "v0 assembly proxy deck models bolted joints as tie/connector proxies; "
                "pretension requires solid bolt geometry and a *PRE-TENSION SECTION, "
                "not available in the proxy model",
            ]
        else:
            status = "no_intent"
            reasons = [
                "no explicit preload specified; bolt preload is not inferred from a "
                "bolt designation or BOM/standard-part entry",
            ]
        connections.append({
            "connection_id": conn.get("connection_id"),
            "type": conn.get("type"),
            "fastener_id": pre.get("fastener_id"),
            "interface_a": conn.get("interface_a"),
            "interface_b": conn.get("interface_b"),
            "preload_intent_present": intent,
            "axial_force_n": pre.get("axial_force_n"),
            "method": pre.get("method"),
            "modeled": modeled,
            "status": status,
            "reasons": reasons,
        })

    bolt_preload_modeled = modeled_count > 0
    return {
        "format": "aieng.assembly_bolt_preload",
        "format_version": FORMAT_VERSION,
        "contract_version": "0.1",
        "schema_version": "0.1",
        "bolt_preload_modeled": bolt_preload_modeled,
        "deck_representation": "modeled" if bolt_preload_modeled else "unsupported",
        "deck_status": deck_status,
        "summary": {
            "bolted_connections": len(connections),
            "with_preload_intent": with_intent,
            "modeled": modeled_count,
        },
        "connections": connections,
        "honesty": {
            "bolt_preload_modeled": bolt_preload_modeled,
            "preload_inferred_from_designation": False,
            "fatigue_modeled": False,
            "loosening_modeled": False,
            "torque_to_preload_certified": False,
            "note": "Preload intent is recorded only when explicitly specified; the v0 "
                    "assembly proxy deck cannot apply pretension, so no preload is modeled "
                    "and no production or fatigue claim is implied.",
        },
    }


def process_assembly_cae_package(package_path: str | Path) -> dict[str, Any]:
    """Best-effort assembly CAE v0 processing for a package.

    Missing prerequisites produce skipped/needs_user_input diagnostics, not hard
    failures.  Packages without ``assembly/assembly_ir.json`` are untouched.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"assembly_present": False, "reason": "package not found"}
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            if ASSEMBLY_IR_PATH not in names:
                return {"assembly_present": False}
            assembly = _read_json(zf, names, ASSEMBLY_IR_PATH)
            part_registry = _read_json(zf, names, PART_REGISTRY_PATH)
            connection_graph = _read_json(zf, names, CONNECTION_GRAPH_PATH)
            interface_resolution = _read_json(zf, names, INTERFACE_RESOLUTION_PATH)
            connection_geometry = _read_json(zf, names, ASSEMBLY_CONNECTION_GEOMETRY_PATH)
            setup_draft = _read_json(zf, names, ASSEMBLY_CAE_DRAFT_PATH)
            manifest = _read_json(zf, names, CONVERSION_MANIFEST_PATH)
            generic_result = None
            for candidate in ASSEMBLY_GENERIC_SOLVER_RESULT_PATHS:
                generic_result = _read_json(zf, names, candidate)
                if generic_result is not None:
                    break
    except Exception as exc:  # noqa: BLE001
        return {"assembly_present": False, "error": f"{type(exc).__name__}: {exc}"}

    model, model_diag = build_assembly_cae_model(
        assembly=assembly,
        part_registry=part_registry,
        connection_graph=connection_graph,
        interface_resolution=interface_resolution,
        connection_geometry=connection_geometry,
        setup_draft=setup_draft,
    )
    deck, deck_diag = generate_assembly_solver_deck(model, available_members=names)
    preload_report = build_bolt_preload_report(model, deck_status=deck_diag.get("status"))
    computed, fields, exec_diag = execute_assembly_solver_v0(
        model=model,
        deck_present=deck is not None,
        generic_result=generic_result,
    )
    if computed is not None and fields is not None:
        result_map, mapping_diag = map_assembly_results(computed_metrics=computed, field_regions=fields, model=model)
    else:
        result_map, mapping_diag = map_assembly_results(computed_metrics=None, field_regions=None, model=model)
        mapping_diag["status"] = "skipped"
        mapping_diag["warnings"] = ["No normalized assembly results available."]

    members: dict[str, bytes] = {
        ASSEMBLY_CAE_MODEL_PATH: _dumps(model),
        ASSEMBLY_CAE_MODEL_DIAGNOSTICS_PATH: _dumps(model_diag),
        ASSEMBLY_SOLVER_DECK_DIAGNOSTICS_PATH: _dumps(deck_diag),
        ASSEMBLY_SOLVER_EXECUTION_DIAGNOSTICS_PATH: _dumps(exec_diag),
        ASSEMBLY_RESULT_MAPPING_DIAGNOSTICS_PATH: _dumps(mapping_diag),
        ASSEMBLY_BOLT_PRELOAD_DIAGNOSTICS_PATH: _dumps(preload_report),
    }
    if deck is not None:
        members[ASSEMBLY_SOLVER_DECK_PATH] = deck.encode("utf-8")
    if computed is not None:
        members[ASSEMBLY_COMPUTED_METRICS_PATH] = _dumps(computed)
    if fields is not None:
        members[ASSEMBLY_FIELD_REGIONS_PATH] = _dumps(fields)
    if mapping_diag.get("status") in {"mapped", "unmapped"}:
        members[ASSEMBLY_RESULT_MAP_PATH] = _dumps(result_map)
    members[CONVERSION_MANIFEST_PATH] = _dumps(
        _update_manifest(
            manifest if isinstance(manifest, dict) else {"format": "aieng.conversion_manifest"},
            model_diag=model_diag,
            deck_diag=deck_diag,
            exec_diag=exec_diag,
            mapping_diag=mapping_diag,
        )
    )
    _replace_members(package_path, members)
    topopt_result: dict[str, Any] = {}
    try:
        from aieng.converters.assembly_topopt import write_assembly_topopt_problem

        topopt_result = write_assembly_topopt_problem(package_path)
    except Exception as exc:  # noqa: BLE001 - assembly topopt setup is best-effort
        topopt_result = {"error": f"{type(exc).__name__}: {exc}"}
    if topopt_result.get("assembly_present"):
        members_artifacts = set(members.keys()) | set(topopt_result.get("artifacts") or [])
    else:
        members_artifacts = set(members.keys())
    return {
        "assembly_present": True,
        "assembly_cae_model_status": model_diag.get("status"),
        "solver_deck_status": deck_diag.get("status"),
        "solver_execution_status": exec_diag.get("status"),
        "assembly_result_mapping_status": mapping_diag.get("status"),
        "assembly_topopt_status": topopt_result.get("status"),
        "assembly_topopt_standard_problem_emitted": topopt_result.get("standard_problem_emitted"),
        "assembly_topopt_diagnostics": topopt_result.get("diagnostics"),
        "assembly_topopt_warnings": topopt_result.get("warnings"),
        "artifacts": sorted(members_artifacts),
    }
