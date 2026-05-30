"""Map CAE (CalculiX) results back to Shape IR objects.

Bridges solver results to the model's authoring intent: it takes
``results/computed_metrics.json`` (scalar extrema per load case) and
``results/field_regions.json`` (spatial clusters of high stress/displacement) and
maps each region through ``geometry/topology_map.json`` and
``registry/object_registry.json`` to a ``source_ir_node`` where resolvable.

Output: ``analysis/cae_result_map.json``. This is observational and runs no
solver/mesher — it only correlates already-produced results with geometry.
Regions that cannot be tied to a node are reported honestly as ``unmapped``.

This map is the substrate for later topology optimization (loads/hotspots tied to
editable Shape IR nodes) — but optimization is NOT implemented here.
"""
from __future__ import annotations

import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

CAE_RESULT_MAP_PATH = "analysis/cae_result_map.json"

_COMPUTED_METRICS_MEMBER = "results/computed_metrics.json"
_FIELD_REGIONS_MEMBER = "results/field_regions.json"
_TOPOLOGY_MEMBER = "geometry/topology_map.json"
_OBJECT_REGISTRY_MEMBER = "registry/object_registry.json"

# FRD field code -> result type
_FIELD_RESULT_TYPE = {"S": "stress", "U": "displacement", "DISP": "displacement", "E": "strain"}
# computed_metrics metric name -> result type
_METRIC_RESULT_TYPE = {
    "max_von_mises_stress": "stress", "min_von_mises_stress": "stress",
    "max_displacement": "displacement", "max_deflection": "deflection",
    "max_principal_stress": "stress", "max_strain": "strain",
}


def _bbox_contains(bbox: list[float], p: tuple[float, float, float], pad: float = 1e-6) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 6:
        return False
    return all(bbox[i] - pad <= p[i] <= bbox[i + 3] + pad for i in range(3))


def _bbox_center(bbox: list[float]) -> tuple[float, float, float]:
    return ((bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2, (bbox[2] + bbox[5]) / 2)


def _resolve_entity(solids: list[dict[str, Any]], point: tuple[float, float, float]) -> tuple[dict[str, Any] | None, str]:
    """Find the topology solid a region location belongs to: prefer bbox
    containment, else nearest centre. Returns (solid, method)."""
    contained = [s for s in solids if _bbox_contains(s.get("bounding_box", []), point)]
    if len(contained) == 1:
        return contained[0], "bbox_contains"
    if contained:
        # multiple containers -> pick the smallest (tightest) bbox
        def _vol(s: dict[str, Any]) -> float:
            b = s.get("bounding_box") or [0, 0, 0, 0, 0, 0]
            return abs((b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2]))
        return min(contained, key=_vol), "bbox_contains"
    nearest, best = None, math.inf
    for s in solids:
        bb = s.get("bounding_box")
        if not (isinstance(bb, list) and len(bb) == 6):
            continue
        c = _bbox_center(bb)
        d = sum((c[i] - point[i]) ** 2 for i in range(3))
        if d < best:
            best, nearest = d, s
    return nearest, ("nearest_center" if nearest is not None else "none")


def _node_for_entity(objects: list[dict[str, Any]], entity_id: str) -> tuple[str | None, str | None, str]:
    """Map a topology entity id to a Shape IR node via the object registry.
    Returns (node_id, linkage, status) where status is resolved | ambiguous | none."""
    matches = [o for o in objects if entity_id in (o.get("topology_entities") or [])]
    if len(matches) == 1:
        return matches[0].get("node_id"), matches[0].get("linkage"), "resolved"
    if len(matches) > 1:
        # e.g. fused mesh: many nodes share one body -> can't single out a node
        return None, (matches[0].get("linkage") if matches else None), "ambiguous"
    return None, None, "none"


def map_cae_results(
    *,
    computed_metrics: dict[str, Any] | None,
    field_regions_docs: list[dict[str, Any]] | None,
    topology_map: dict[str, Any] | None,
    object_registry: dict[str, Any] | None,
) -> dict[str, Any]:
    """Correlate CAE results with Shape IR nodes. Pure; inputs are dicts."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    computed_metrics = computed_metrics or {}
    field_regions_docs = [d for d in (field_regions_docs or []) if isinstance(d, dict)]
    entities = (topology_map or {}).get("entities") or []
    solids = [e for e in entities if isinstance(e, dict) and e.get("type") == "solid"]
    objects = (object_registry or {}).get("objects") or []

    load_cases = computed_metrics.get("load_cases") or []
    units: dict[str, str] = {}

    # ── overall scalar extrema per load case (from computed_metrics) ──
    overall: list[dict[str, Any]] = []
    for lc in load_cases:
        if not isinstance(lc, dict):
            continue
        lc_id = str(lc.get("id") or "load_case_1")
        for name, mv in (lc.get("metrics") or {}).items():
            if not isinstance(mv, dict):
                continue
            rtype = _METRIC_RESULT_TYPE.get(name, name.replace("max_", "").replace("min_", ""))
            unit = mv.get("unit")
            if unit:
                units.setdefault(rtype, unit)
            overall.append({
                "load_case_id": lc_id,
                "result_type": rtype,
                "metric": name,
                "max": mv.get("value"),
                "min": None,       # computed_metrics records extrema only
                "average": None,   # not available without per-node aggregation
                "unit": unit,
            })

    default_lc = str(load_cases[0]["id"]) if load_cases and isinstance(load_cases[0], dict) and load_cases[0].get("id") else "load_case_1"

    # ── spatial regions -> topology entity -> Shape IR node ──
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for doc in field_regions_docs:
        field = str(doc.get("field") or "").upper()
        rtype = _FIELD_RESULT_TYPE.get(field, field.lower() or "unknown")
        lc_id = str(doc.get("load_case_id") or default_lc)
        for cluster in doc.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            loc = cluster.get("location") or {}
            point = (float(loc.get("x", 0.0)), float(loc.get("y", 0.0)), float(loc.get("z", 0.0)))
            mag = cluster.get("magnitude") or {}
            unit = mag.get("unit")
            if unit:
                units.setdefault(rtype, unit)
            base = {
                "load_case_id": lc_id,
                "result_type": rtype,
                "cluster_id": cluster.get("id"),
                "value": mag.get("value"),
                "unit": unit,
                "location": {"x": point[0], "y": point[1], "z": point[2]},
                "node_count": cluster.get("node_count"),
            }
            solid, method = _resolve_entity(solids, point) if solids else (None, "none")
            if solid is None:
                unmapped.append({**base, "reason": "no topology solid near the result location"})
                continue
            node_id, linkage, status = _node_for_entity(objects, str(solid.get("id")))
            affected = [str(solid.get("id"))] + [str(f) for f in (solid.get("face_ids") or [])]
            if status == "resolved":
                confidence = "high" if (method == "bbox_contains" and linkage in ("name_match", "source_ir_node")) else "medium"
            elif status == "ambiguous":
                confidence = "low"  # fused mesh / shared body — region known, node not unique
            else:
                confidence = "low"
            entry = {
                **base,
                "affected_topology_entities": affected,
                "source_ir_node": node_id,
                "node_linkage": linkage,
                "mapping_method": method,
                "confidence": confidence,
            }
            if node_id is None:
                entry["note"] = (
                    "region mapped to a topology body but not to a unique Shape IR node "
                    f"({status}; e.g. fused mesh)."
                )
            mapped.append(entry)

    notes = [
        "Observational CAE->Shape IR correlation; no solver/mesher executed.",
        "Spatial regions are matched to topology bodies by location; node linkage uses the object registry.",
    ]
    if not field_regions_docs:
        notes.append("No field_regions present — only scalar extrema were mapped (run cae.extract_field_regions).")
    if not objects:
        notes.append("No object registry — regions could not be tied to Shape IR nodes.")

    return {
        "format_version": FORMAT_VERSION,
        "generated_at_utc": now,
        "load_cases": [o["load_case_id"] for o in overall] or ([default_lc] if field_regions_docs else []),
        "units": units,
        "overall": overall,
        "mapped_results": mapped,
        "unmapped_regions": unmapped,
        "summary": {
            "mapped_count": len(mapped),
            "unmapped_count": len(unmapped),
            "resolved_to_node": sum(1 for m in mapped if m.get("source_ir_node")),
        },
        "notes": notes,
    }


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    try:
        return json.loads(zf.read(name).decode("utf-8"))
    except Exception:
        return None


def build_cae_result_map_for_package(package_path: str | Path) -> dict[str, Any]:
    """Read CAE + geometry artifacts from a package and build the result map."""
    package_path = Path(package_path)
    if not package_path.exists():
        return {"format_version": FORMAT_VERSION, "error": f"package not found: {package_path}",
                "mapped_results": [], "unmapped_regions": []}
    with zipfile.ZipFile(package_path, "r") as zf:
        names = set(zf.namelist())
        computed_metrics = _read_json(zf, _COMPUTED_METRICS_MEMBER, names)
        field_regions = _read_json(zf, _FIELD_REGIONS_MEMBER, names)
        topology_map = _read_json(zf, _TOPOLOGY_MEMBER, names)
        object_registry = _read_json(zf, _OBJECT_REGISTRY_MEMBER, names)
    docs = [field_regions] if isinstance(field_regions, dict) else []
    return map_cae_results(
        computed_metrics=computed_metrics,
        field_regions_docs=docs,
        topology_map=topology_map,
        object_registry=object_registry,
    )


def write_cae_result_map(package_path: str | Path) -> dict[str, Any]:
    """Build the CAE result map and write analysis/cae_result_map.json."""
    package_path = Path(package_path)
    result_map = build_cae_result_map_for_package(package_path)
    if not package_path.exists():
        return result_map
    data = (json.dumps(result_map, indent=2, sort_keys=True) + "\n").encode()
    tmp = package_path.with_suffix(".tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename != CAE_RESULT_MAP_PATH:
                    dst.writestr(item, src.read(item.filename))
            dst.writestr(CAE_RESULT_MAP_PATH, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return result_map
