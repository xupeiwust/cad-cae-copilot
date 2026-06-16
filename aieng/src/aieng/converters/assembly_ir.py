"""Assembly IR v0 — backend multi-part assembly representation + simplified connection contract.

Assembly IR describes parts, their placements, interfaces, and SIMPLIFIED engineering
connections (proxies) between parts, plus which parts are design spaces vs fixed/reference.

v0 scope is REPRESENTATION + VALIDATION ONLY:
  - validate_assembly_ir         -> diagnostics/assembly_validation.json
  - build_part_registry          -> assembly/part_registry.json
  - build_connection_graph       -> assembly/connection_graph.json
  - build_assembly_cae_setup_draft -> simulation/assembly_cae_setup_draft.json (solver-neutral DRAFT)
  - process_assembly_package     -> runs all of the above on a .aieng package (best-effort)

Honesty contract: connections are PROXIES, not full nonlinear contact. No bolt preload, no
assembly solver execution, no real contact physics. The CAE draft is solver-neutral and never
produces a solver-specific deck. Topology refs (face/edge/vertex ids) are allowed to be
unresolved in v0 and are reported honestly rather than silently assumed valid.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

# ── package artifact paths ────────────────────────────────────────────────────
ASSEMBLY_IR_PATH = "assembly/assembly_ir.json"
PART_REGISTRY_PATH = "assembly/part_registry.json"
CONNECTION_GRAPH_PATH = "assembly/connection_graph.json"
ASSEMBLY_VALIDATION_PATH = "diagnostics/assembly_validation.json"
ASSEMBLY_CAE_DRAFT_PATH = "simulation/assembly_cae_setup_draft.json"
CONVERSION_MANIFEST_PATH = "provenance/conversion_manifest.json"

# ── controlled vocabularies ───────────────────────────────────────────────────
PART_ROLES = {"design_part", "reference_part", "fixture", "load_source", "fastener", "external_context"}
# Roles editable-by-default (a part can override with an explicit `editable` flag).
EDITABLE_ROLES = {"design_part"}
CONNECTION_TYPES = {"rigid_tie", "bonded", "bolted_proxy", "welded_proxy",
                    "contact_proxy", "spring_proxy", "unknown"}
# Simplified models that MUST carry limitations (they approximate real physics).
PROXY_CONNECTION_TYPES = {"bolted_proxy", "welded_proxy", "contact_proxy", "spring_proxy"}
# Types that transfer load unless a connection is explicitly positioning-only.
LOAD_TRANSFER_TYPES = {"rigid_tie", "bonded", "bolted_proxy", "welded_proxy",
                       "contact_proxy", "spring_proxy"}
CONNECTION_BEHAVIORS = {"load_transfer", "positioning_only", "preserve_interface"}
INTERFACE_ROLES = {"mounting_face", "bolt_hole", "contact_face", "weld_face", "load_face", "support_face"}

# Solver-neutral CAE draft mapping for each connection type.
_CAE_DRAFT_MAP = {
    "rigid_tie": ("tie_constraint", True),
    "bonded": ("tie_constraint", True),
    "welded_proxy": ("bonded_tie", True),
    "bolted_proxy": ("connector_proxy", True),
    "spring_proxy": ("spring_connector", True),
    "contact_proxy": ("contact_unsupported", False),
    "unknown": ("unsupported", False),
}


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _is_number_triple(value: Any) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value))


def _matrix_shape_ok(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
        return False
    return all(isinstance(row, (list, tuple)) and len(row) == len(value) for row in value)


def _collect_interfaces(assembly: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index interfaces by id. Accepts a top-level ``interfaces`` list and/or per-part nesting."""
    out: dict[str, dict[str, Any]] = {}
    for iface in _as_list(assembly.get("interfaces")):
        if isinstance(iface, dict) and iface.get("id"):
            out[iface["id"]] = iface
    for part in _as_list(assembly.get("parts")):
        if not isinstance(part, dict):
            continue
        for iface in _as_list(part.get("interfaces")):
            if isinstance(iface, dict) and iface.get("id"):
                iface = {**iface}
                iface.setdefault("part_id", part.get("id"))
                out[iface["id"]] = iface
    return out


def _part_editable(part: dict[str, Any]) -> bool:
    explicit = part.get("editable")
    if isinstance(explicit, bool):
        return explicit
    return part.get("role") in EDITABLE_ROLES


def _connection_behaviors(conn: dict[str, Any]) -> list[str]:
    return [str(b) for b in _as_list(conn.get("behavior"))]


def _connection_load_transfer(conn: dict[str, Any]) -> bool:
    behaviors = _connection_behaviors(conn)
    if "load_transfer" in behaviors:
        return True
    if "positioning_only" in behaviors:
        return False
    return conn.get("type") in LOAD_TRANSFER_TYPES


def _topology_ref_tokens(iface: dict[str, Any]) -> list[str]:
    refs = iface.get("topology_refs") or {}
    tokens: list[str] = []
    if isinstance(refs, dict):
        for key in ("face_ids", "edge_ids", "vertex_ids"):
            for rid in _as_list(refs.get(key)):
                tokens.append(f"{iface.get('id', '?')}:{key[:-4]}:{rid}")
    return tokens


# ── Part B: validation ─────────────────────────────────────────────────────────

def validate_assembly_ir(assembly: Any) -> dict[str, Any]:
    """Validate an Assembly IR document. Returns a diagnostics dict (never raises).

    status is ``failed`` if any errors, ``warning`` if any warnings, else ``passed``.
    Topology refs are reported as ``unresolved_refs`` (v0 cannot resolve them) — not errors.
    """
    errors: list[str] = []
    warnings: list[str] = []
    unresolved_refs: list[str] = []
    unsupported_connection_types: list[str] = []
    limitations: list[str] = [
        "Assembly IR v0: connections are simplified PROXIES, not nonlinear contact.",
        "No assembly solver execution, no bolt preload, no contact physics are validated here.",
    ]

    if not isinstance(assembly, dict):
        return {
            "format": "aieng.assembly_validation", "format_version": FORMAT_VERSION,
            "schema_version": "0.1", "status": "failed",
            "errors": ["assembly_ir is not a JSON object"], "warnings": [],
            "unresolved_refs": [], "unsupported_connection_types": [],
            "limitations": limitations, "summary": {},
        }

    parts = [p for p in _as_list(assembly.get("parts")) if isinstance(p, dict)]
    connections = [c for c in _as_list(assembly.get("connections")) if isinstance(c, dict)]
    interfaces = _collect_interfaces(assembly)

    # 1. unique part ids + role / geometry / transform per part
    part_ids: set[str] = set()
    for idx, part in enumerate(parts):
        pid = part.get("id")
        if not pid:
            errors.append(f"part[{idx}] has no id")
            continue
        if pid in part_ids:
            errors.append(f"duplicate part id: {pid}")
        part_ids.add(pid)

        role = part.get("role")
        if role is None:
            warnings.append(f"part '{pid}' has no role (defaulting to external_context)")
        elif role not in PART_ROLES:
            warnings.append(f"part '{pid}' has unrecognized role '{role}'")

        # geometry_ref severity depends on role: design parts NEED geometry.
        if not part.get("geometry_ref") and not part.get("source_ir_node"):
            if role == "design_part":
                errors.append(f"design part '{pid}' has no geometry_ref / source_ir_node")
            else:
                warnings.append(f"part '{pid}' has no geometry_ref / source_ir_node")

        # 4. transform presence + shape
        transform = part.get("transform")
        if transform is None:
            warnings.append(f"part '{pid}' has no transform (assumed identity placement)")
        elif not isinstance(transform, dict):
            errors.append(f"part '{pid}' transform is not an object")
        else:
            if "translation" in transform and not _is_number_triple(transform["translation"]):
                errors.append(f"part '{pid}' transform.translation must be 3 numbers")
            if "rotation_euler_deg" in transform and not _is_number_triple(transform["rotation_euler_deg"]):
                errors.append(f"part '{pid}' transform.rotation_euler_deg must be 3 numbers")
            if "matrix" in transform and not _matrix_shape_ok(transform["matrix"]):
                errors.append(f"part '{pid}' transform.matrix must be 3x3 or 4x4")
            if not transform.get("unit") and not assembly.get("unit"):
                warnings.append(f"part '{pid}' transform has no unit (and assembly has no default unit)")

    # 3. interface references valid (part_id must exist)
    for iid, iface in interfaces.items():
        ipart = iface.get("part_id")
        if ipart not in part_ids:
            errors.append(f"interface '{iid}' references unknown part_id '{ipart}'")
        role = iface.get("semantic_role")
        if role is not None and role not in INTERFACE_ROLES:
            warnings.append(f"interface '{iid}' has unrecognized semantic_role '{role}'")
        # 7. topology refs are allowed unresolved but must be reported
        unresolved_refs.extend(_topology_ref_tokens(iface))

    # 2 / 6 / 8. connections
    for idx, conn in enumerate(connections):
        cid = conn.get("id") or f"connection[{idx}]"
        ctype = conn.get("type")
        if ctype not in CONNECTION_TYPES:
            unsupported_connection_types.append(str(ctype))
            warnings.append(f"connection '{cid}' has unrecognized type '{ctype}'")
        elif ctype == "unknown":
            warnings.append(f"connection '{cid}' type is 'unknown' (no behavior can be derived)")

        for side in ("part_a", "part_b"):
            ref = conn.get(side)
            if ref is None:
                errors.append(f"connection '{cid}' missing {side}")
            elif ref not in part_ids:
                errors.append(f"connection '{cid}' {side} references unknown part '{ref}'")

        for side, partside in (("interface_a", "part_a"), ("interface_b", "part_b")):
            ref = conn.get(side)
            if ref is None:
                continue
            if ref not in interfaces:
                errors.append(f"connection '{cid}' {side} references unknown interface '{ref}'")
            elif conn.get(partside) and interfaces[ref].get("part_id") != conn.get(partside):
                warnings.append(
                    f"connection '{cid}' {side}='{ref}' belongs to part "
                    f"'{interfaces[ref].get('part_id')}', not {partside}='{conn.get(partside)}'")

        # 8. proxy connections must declare limitations
        if ctype in PROXY_CONNECTION_TYPES and not _as_list(conn.get("limitations")):
            warnings.append(f"proxy connection '{cid}' ({ctype}) declares no limitations")

    # 5. design parts must exist (role or analysis_intent)
    intent = assembly.get("analysis_intent") or {}
    design_by_role = [p["id"] for p in parts if p.get("role") == "design_part" and p.get("id")]
    design_by_intent = [str(x) for x in _as_list(intent.get("design_parts"))]
    if not design_by_role and not design_by_intent:
        errors.append("no design parts declared (no part has role 'design_part' and "
                      "analysis_intent.design_parts is empty)")
    # analysis_intent references should point at real parts
    for key in ("design_parts", "frozen_parts", "allowed_optimization_parts"):
        for ref in _as_list(intent.get(key)):
            if ref not in part_ids:
                warnings.append(f"analysis_intent.{key} references unknown part '{ref}'")
    for ref in _as_list(intent.get("preserve_interfaces")):
        if ref not in interfaces:
            warnings.append(f"analysis_intent.preserve_interfaces references unknown interface '{ref}'")

    status = "failed" if errors else ("warning" if warnings else "passed")
    return {
        "format": "aieng.assembly_validation", "format_version": FORMAT_VERSION,
        "schema_version": "0.1", "status": status,
        "errors": errors, "warnings": warnings,
        "unresolved_refs": unresolved_refs,
        "unsupported_connection_types": sorted(set(unsupported_connection_types)),
        "limitations": limitations,
        "summary": {
            "part_count": len(parts),
            "connection_count": len(connections),
            "interface_count": len(interfaces),
            "design_part_count": len(set(design_by_role) | set(design_by_intent)),
            "proxy_connection_count": sum(1 for c in connections if c.get("type") in PROXY_CONNECTION_TYPES),
            "unresolved_ref_count": len(unresolved_refs),
        },
    }


# ── Part C: part registry + connection graph ─────────────────────────────────

def build_part_registry(assembly: Any) -> dict[str, Any]:
    """Normalized per-part registry. Editability is derived from role unless set explicitly."""
    assembly = assembly if isinstance(assembly, dict) else {}
    interfaces = _collect_interfaces(assembly)
    refs_by_part: dict[str, int] = {}
    for iface in interfaces.values():
        if any(_as_list((iface.get("topology_refs") or {}).get(k))
               for k in ("face_ids", "edge_ids", "vertex_ids")):
            refs_by_part[iface.get("part_id")] = refs_by_part.get(iface.get("part_id"), 0) + 1

    entries = []
    for part in _as_list(assembly.get("parts")):
        if not isinstance(part, dict):
            continue
        pid = part.get("id")
        geom = part.get("geometry_ref")
        entries.append({
            "part_id": pid,
            "name": part.get("name") or pid,
            "role": part.get("role") or "external_context",
            "geometry_ref": geom,
            "transform": part.get("transform"),
            "material": part.get("material"),
            "editable": _part_editable(part),
            "source_member": part.get("source_member") or geom,
            "source_ir_node": part.get("source_ir_node"),
            "topology_available": bool(geom or part.get("source_ir_node")),
            "topology_refs_present": refs_by_part.get(pid, 0) > 0,
        })
    return {
        "format": "aieng.assembly_part_registry", "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "parts": entries,
        "provenance": _provenance_block(assembly),
    }


def build_connection_graph(assembly: Any) -> dict[str, Any]:
    """Graph view: parts are nodes, connections are edges. Solver-neutral; proxies flagged."""
    assembly = assembly if isinstance(assembly, dict) else {}
    nodes = []
    for part in _as_list(assembly.get("parts")):
        if not isinstance(part, dict):
            continue
        nodes.append({
            "part_id": part.get("id"),
            "role": part.get("role") or "external_context",
            "editable": _part_editable(part),
        })

    edges = []
    for idx, conn in enumerate(_as_list(assembly.get("connections"))):
        if not isinstance(conn, dict):
            continue
        ctype = conn.get("type")
        edges.append({
            "id": conn.get("id") or f"connection_{idx:03d}",
            "type": ctype,
            "part_a": conn.get("part_a"),
            "part_b": conn.get("part_b"),
            "interface_a": conn.get("interface_a"),
            "interface_b": conn.get("interface_b"),
            "behavior": _connection_behaviors(conn),
            "confidence": conn.get("confidence"),
            "limitations": _as_list(conn.get("limitations")),
            "is_proxy": ctype in PROXY_CONNECTION_TYPES,
            "load_transfer": _connection_load_transfer(conn),
        })
    return {
        "format": "aieng.assembly_connection_graph", "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "nodes": nodes,
        "edges": edges,
        "provenance": _provenance_block(assembly),
    }


# ── Part D: assembly-aware CAE setup DRAFT (solver-neutral) ───────────────────

def build_assembly_cae_setup_draft(assembly: Any) -> dict[str, Any]:
    """Translate Assembly IR into a solver-neutral CAE DRAFT (never a solver deck).

    status is ``needs_user_input`` when required data is missing (e.g. a load-transferring
    connection with no interfaces, or no design parts), else ``draft``.
    """
    assembly = assembly if isinstance(assembly, dict) else {}
    interfaces = _collect_interfaces(assembly)
    parts = [p for p in _as_list(assembly.get("parts")) if isinstance(p, dict)]
    intent = assembly.get("analysis_intent") or {}

    needs_user_input: list[str] = []
    warnings: list[str] = []
    limitations: list[str] = [
        "Solver-neutral DRAFT only — no CalculiX/solver deck is produced.",
        "Connections are simplified proxies; tie/connector/spring drafts do NOT model real "
        "contact, friction, or bolt preload.",
    ]

    part_drafts = []
    materials: dict[str, Any] = {}
    for part in parts:
        pid = part.get("id")
        mat = part.get("material")
        if mat is not None:
            materials[pid] = mat
        else:
            warnings.append(f"part '{pid}' has no material (draft leaves it unassigned)")
        part_drafts.append({
            "part_id": pid, "role": part.get("role") or "external_context",
            "editable": _part_editable(part), "material": mat,
            "frozen": part.get("role") in {"reference_part", "fixture", "external_context"}
                      or pid in set(_as_list(intent.get("frozen_parts"))),
        })

    connection_drafts = []
    for idx, conn in enumerate(_as_list(assembly.get("connections"))):
        if not isinstance(conn, dict):
            continue
        cid = conn.get("id") or f"connection_{idx:03d}"
        ctype = conn.get("type")
        draft_type, supported = _CAE_DRAFT_MAP.get(ctype, ("unsupported", False))
        entry = {
            "connection_id": cid, "source_type": ctype, "draft_type": draft_type,
            "supported": supported, "behavior": _connection_behaviors(conn),
            "load_transfer": _connection_load_transfer(conn),
            "interface_a": conn.get("interface_a"), "interface_b": conn.get("interface_b"),
            "limitations": _as_list(conn.get("limitations")),
        }
        if not supported:
            entry["draft_only"] = True
            entry.setdefault("limitations", []).append(
                f"'{ctype}' has no solver-neutral draft in v0 — review manually before any analysis.")
            warnings.append(f"connection '{cid}' ({ctype}) is unsupported/draft-only")
        # A load-transferring connection without interfaces cannot be located.
        if entry["load_transfer"] and not (conn.get("interface_a") and conn.get("interface_b")):
            needs_user_input.append(
                f"connection '{cid}' transfers load but is missing interface_a/interface_b")
        connection_drafts.append(entry)

    # loads / supports from interface semantic roles
    loads, supports = [], []
    for iid, iface in interfaces.items():
        role = iface.get("semantic_role")
        ref = {"interface_id": iid, "part_id": iface.get("part_id"), "semantic_role": role,
               "topology_resolved": False}
        if role == "load_face":
            loads.append(ref)
        elif role in {"support_face", "mounting_face"}:
            supports.append(ref)

    preserve_interfaces = sorted(set(
        [str(x) for x in _as_list(intent.get("preserve_interfaces"))]
        + [c.get("interface_a") for c in _as_list(assembly.get("connections"))
           if isinstance(c, dict) and "preserve_interface" in _connection_behaviors(c) and c.get("interface_a")]
        + [c.get("interface_b") for c in _as_list(assembly.get("connections"))
           if isinstance(c, dict) and "preserve_interface" in _connection_behaviors(c) and c.get("interface_b")]
    ))

    design_parts = [p["id"] for p in parts if p.get("role") == "design_part" and p.get("id")] \
        or [str(x) for x in _as_list(intent.get("design_parts"))]
    if not design_parts:
        needs_user_input.append("no design parts declared — cannot scope an analysis draft")
    if not part_drafts:
        needs_user_input.append("assembly declares no parts")

    status = "needs_user_input" if needs_user_input else "draft"
    return {
        "format": "aieng.assembly_cae_setup_draft", "format_version": FORMAT_VERSION,
        "schema_version": "0.1", "status": status,
        "parts": part_drafts,
        "materials": materials,
        "connections": connection_drafts,
        "loads": loads,
        "supports": supports,
        "preserve_interfaces": preserve_interfaces,
        "design_parts": design_parts,
        "needs_user_input": needs_user_input,
        "warnings": warnings,
        "limitations": limitations,
        "provenance": _provenance_block(assembly),
    }


def _provenance_block(assembly: dict[str, Any]) -> dict[str, Any]:
    prov = assembly.get("provenance") if isinstance(assembly, dict) else None
    base = {
        "created_by": "aieng.assembly_ir",
        "schema": "assembly_ir.schema.json",
        "is_proxy_model": True,
        "contact_physics_modeled": False,
        "bolt_preload_modeled": False,
        "solver_executed": False,
    }
    if isinstance(prov, dict):
        base["source"] = prov
    return base


# ── Part E: package integration ───────────────────────────────────────────────

def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
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


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def process_assembly_package(package_path: str | Path) -> dict[str, Any]:
    """Best-effort: if a package carries assembly/assembly_ir.json, validate it and write
    the registry, connection graph, validation diagnostics, and CAE setup draft. A package
    WITHOUT assembly/assembly_ir.json is left untouched (returns ``{assembly_present: False}``).
    Never raises into the caller; never runs a solver; never touches single-part geometry.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"assembly_present": False, "reason": "package not found"}
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            if ASSEMBLY_IR_PATH not in names:
                return {"assembly_present": False}
            try:
                assembly = json.loads(zf.read(ASSEMBLY_IR_PATH))
            except Exception:
                assembly = None
            manifest = None
            if CONVERSION_MANIFEST_PATH in names:
                try:
                    manifest = json.loads(zf.read(CONVERSION_MANIFEST_PATH))
                except Exception:
                    manifest = None
    except Exception as exc:  # noqa: BLE001 - corrupt package; report, don't raise
        return {"assembly_present": False, "error": f"{type(exc).__name__}: {exc}"}

    validation = validate_assembly_ir(assembly)
    registry = build_part_registry(assembly)
    graph = build_connection_graph(assembly)
    draft = build_assembly_cae_setup_draft(assembly)

    members = {
        ASSEMBLY_VALIDATION_PATH: _dumps(validation),
        PART_REGISTRY_PATH: _dumps(registry),
        CONNECTION_GRAPH_PATH: _dumps(graph),
        ASSEMBLY_CAE_DRAFT_PATH: _dumps(draft),
    }
    if isinstance(manifest, dict):
        manifest["assembly"] = {
            "present": True,
            "part_count": validation["summary"].get("part_count", 0),
            "connection_count": validation["summary"].get("connection_count", 0),
            "validation_status": validation["status"],
            "is_proxy_model": True,
            "solver_executed": False,
        }
        members[CONVERSION_MANIFEST_PATH] = _dumps(manifest)

    _rewrite_package_members(package_path, members)
    return {
        "assembly_present": True,
        "validation_status": validation["status"],
        "part_count": validation["summary"].get("part_count", 0),
        "connection_count": validation["summary"].get("connection_count", 0),
        "cae_draft_status": draft["status"],
        "artifacts": sorted(members.keys()),
    }


# ── Part F: authoring (write parts / connections into a package's assembly IR) ──
#
# These let an agent build the assembly IR incrementally from the named parts of
# a single .aieng package — define each part, then the mates between them — rather
# than only consuming an IR produced elsewhere. Authoring stays inside the v0
# honesty contract: connections are proxies, no contact/preload/solver is implied.

GEOMETRY_TOPOLOGY_PATH = "geometry/topology_map.json"

# Honest default limitation for each proxy connection type (the schema REQUIRES
# proxy connections to carry limitations; we never let one be recorded without).
_DEFAULT_PROXY_LIMITATION = {
    "bolted_proxy": "Bolted proxy: no bolt preload, no thread engagement, no contact separation modeled.",
    "welded_proxy": "Welded proxy: idealized as a bonded tie; no weld metallurgy, HAZ, or residual stress.",
    "contact_proxy": "Contact proxy: no real contact mechanics (no separation, friction, or pressure distribution).",
    "spring_proxy": "Spring proxy: a lumped linear stiffness, not a physical compliant member.",
}


def _read_member(package_path: Path, member: str) -> Any | None:
    """Best-effort read of one JSON member from a .aieng package."""
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            if member in zf.namelist():
                return json.loads(zf.read(member))
    except Exception:
        return None
    return None


def load_assembly_ir(package_path: str | Path) -> dict[str, Any]:
    """Return the package's assembly IR, or a fresh skeleton if absent/corrupt."""
    data = _read_member(Path(package_path), ASSEMBLY_IR_PATH)
    if isinstance(data, dict) and data.get("format") == "aieng.assembly_ir":
        data.setdefault("parts", [])
        data.setdefault("interfaces", [])
        data.setdefault("connections", [])
        return data
    return {
        "format": "aieng.assembly_ir",
        "schema_version": FORMAT_VERSION,
        "unit": "mm",
        "parts": [],
        "interfaces": [],
        "connections": [],
    }


def _named_parts_in_package(package_path: Path) -> set[str]:
    """Named solids in the package's CAD topology (for geometry_ref verification)."""
    topo = _read_member(package_path, GEOMETRY_TOPOLOGY_PATH)
    names: set[str] = set()
    if isinstance(topo, dict):
        for e in topo.get("entities", []):
            if isinstance(e, dict) and e.get("type") == "solid" and e.get("name"):
                names.add(str(e["name"]))
    return names


def _assembly_summary(assembly: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    parts = assembly.get("parts", [])
    conns = assembly.get("connections", [])
    return {
        "part_count": len(parts),
        "connection_count": len(conns),
        "parts": [p.get("id") for p in parts],
        "connections": [c.get("id") for c in conns],
        "validation_status": validation.get("status"),
    }


def _save_and_process(package_path: Path, assembly: dict[str, Any], process: bool) -> dict[str, Any]:
    _rewrite_package_members(package_path, {ASSEMBLY_IR_PATH: _dumps(assembly)})
    if process:
        return process_assembly_package(package_path)
    return {"assembly_present": True, "processed": False}


def define_assembly_part(
    package_path: str | Path,
    *,
    part_id: str | None = None,
    name: str | None = None,
    role: str = "design_part",
    geometry_ref: str | None = None,
    transform: dict[str, Any] | None = None,
    material: Any = None,
    editable: bool | None = None,
    process: bool = True,
) -> dict[str, Any]:
    """Add or update one part in the package's assembly IR (initialising the IR if
    absent). ``geometry_ref`` links the assembly part to a named solid in the
    package's CAD model; it is verified against the topology when available and
    reported honestly (``geometry_ref_known`` is ``True`` / ``False`` / ``None``
    for verified / not-found / unverifiable) — never fabricated.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "error", "code": "package_not_found", "message": f"package not found: {package_path}"}
    role = str(role or "design_part")
    if role not in PART_ROLES:
        return {"status": "error", "code": "bad_role",
                "message": f"role must be one of {sorted(PART_ROLES)}", "got": role}
    pid = str(part_id or geometry_ref or name or "").strip()
    if not pid:
        return {"status": "error", "code": "missing_id",
                "message": "Provide part_id, geometry_ref, or name to identify the part."}

    assembly = load_assembly_ir(package_path)
    named = _named_parts_in_package(package_path)
    ref = (geometry_ref or name or pid)
    if named:
        geometry_ref_known: bool | None = ref in named
    else:
        geometry_ref_known = None

    part: dict[str, Any] = {"id": pid, "role": role}
    if name:
        part["name"] = name
    if ref:
        part["geometry_ref"] = ref
    if transform is not None:
        part["transform"] = transform
    if material is not None:
        part["material"] = material
    if editable is not None:
        part["editable"] = bool(editable)

    parts = assembly.setdefault("parts", [])
    idx = next((i for i, p in enumerate(parts) if p.get("id") == pid), None)
    action = "updated" if idx is not None else "added"
    if idx is not None:
        parts[idx] = {**parts[idx], **part}
    else:
        parts.append(part)

    processed = _save_and_process(package_path, assembly, process)
    validation = validate_assembly_ir(assembly)
    if geometry_ref_known is True:
        ref_note = f"geometry_ref '{ref}' matches a named part in the model."
    elif geometry_ref_known is False:
        ref_note = (f"geometry_ref '{ref}' does NOT match any named part {sorted(named)} — the part "
                    "is recorded but unlinked. Fix the label or build that part first.")
    else:
        ref_note = "No CAD topology in the package to verify geometry_ref against (unverified, not a failure)."
    return {
        "status": "ok",
        "action": action,
        "part": part,
        "geometry_ref_known": geometry_ref_known,
        "geometry_ref_note": ref_note,
        "assembly_summary": _assembly_summary(assembly, validation),
        "processed": processed,
        "honesty": ("Assembly IR is a representation + validation contract. It records parts and "
                    "proxy connections; it implies no contact physics, no bolt preload, and no solver run."),
    }


def define_assembly_mate(
    package_path: str | Path,
    *,
    connection_type: str,
    part_a: str,
    part_b: str,
    connection_id: str | None = None,
    interface_a: str | None = None,
    interface_b: str | None = None,
    behavior: Any = None,
    parameters: dict[str, Any] | None = None,
    confidence: Any = "low",
    limitations: list[str] | None = None,
    process: bool = True,
) -> dict[str, Any]:
    """Add or update one connection (mate) between two **already-defined** parts.
    Refuses dangling connections (both parts must exist — call ``define_assembly_part``
    first) and never records a proxy connection without ``limitations`` (auto-fills an
    honest default for the proxy type when none is supplied).
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "error", "code": "package_not_found", "message": f"package not found: {package_path}"}
    ctype = str(connection_type or "").strip()
    if ctype not in CONNECTION_TYPES:
        return {"status": "error", "code": "bad_type",
                "message": f"connection_type must be one of {sorted(CONNECTION_TYPES)}", "got": ctype}
    pa, pb = str(part_a or "").strip(), str(part_b or "").strip()
    if not pa or not pb:
        return {"status": "error", "code": "missing_parts", "message": "part_a and part_b are required."}
    if pa == pb:
        return {"status": "error", "code": "self_connection", "message": "part_a and part_b must differ."}

    assembly = load_assembly_ir(package_path)
    part_ids = {p.get("id") for p in assembly.get("parts", []) if p.get("id")}
    missing = [p for p in (pa, pb) if p not in part_ids]
    if missing:
        return {"status": "error", "code": "unknown_parts",
                "message": f"part(s) {missing} are not defined in the assembly — call cad.define_part first.",
                "available_parts": sorted(part_ids)}

    lims = list(limitations or [])
    if ctype in PROXY_CONNECTION_TYPES and not lims:
        lims = [_DEFAULT_PROXY_LIMITATION.get(ctype, "Simplified proxy: real physics not fully modeled.")]

    cid = str(connection_id or f"conn_{pa}__{pb}_{ctype}").strip()
    conn: dict[str, Any] = {"id": cid, "type": ctype, "part_a": pa, "part_b": pb}
    if interface_a:
        conn["interface_a"] = interface_a
    if interface_b:
        conn["interface_b"] = interface_b
    if behavior is not None:
        conn["behavior"] = behavior
    if parameters:
        conn["parameters"] = parameters
    if confidence is not None:
        conn["confidence"] = confidence
    if lims:
        conn["limitations"] = lims

    conns = assembly.setdefault("connections", [])
    idx = next((i for i, c in enumerate(conns) if c.get("id") == cid), None)
    action = "updated" if idx is not None else "added"
    if idx is not None:
        conns[idx] = conn
    else:
        conns.append(conn)

    processed = _save_and_process(package_path, assembly, process)
    validation = validate_assembly_ir(assembly)
    return {
        "status": "ok",
        "action": action,
        "connection": conn,
        "is_proxy": ctype in PROXY_CONNECTION_TYPES,
        "assembly_summary": _assembly_summary(assembly, validation),
        "processed": processed,
        "honesty": ("Connection is a v0 proxy: positioning + simplified load transfer only. No "
                    "contact mechanics, no bolt preload, no solver execution is implied."),
    }
