"""Map (solver-neutral) CAE results back to Shape IR objects.

Consumes ONLY the neutral CAE contract artifacts — ``analysis/computed_metrics.json``
and ``analysis/field_regions.json`` (see ``cae_result_contract``) — plus
``geometry/topology_map.json`` and ``registry/object_registry.json``. It never
reads solver-native files (.frd/.dat/.inp) or knows any solver's naming; that is
the adapters'/normalizers' job. This is what makes the mapping solver-neutral:
CalculiX, Code_Aster, Elmer, FEniCSx or a remote solver all map identically once
their results are normalized.

Output: ``analysis/cae_result_map.json`` (ties results to topology entities,
object_registry objects, and source_ir_node where resolvable; unmapped regions
are reported honestly). This is observational and runs no solver/mesher.
"""
from __future__ import annotations

import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

from .cae_result_contract import CAE_CONTRACT_VERSION, load_neutral_cae_artifacts
from .credibility import classify_credibility

CAE_RESULT_MAP_PATH = "analysis/cae_result_map.json"
_TOPOLOGY_MEMBER = "geometry/topology_map.json"
_OBJECT_REGISTRY_MEMBER = "registry/object_registry.json"


def _bbox_contains(bbox: Any, p: tuple[float, float, float], pad: float = 1e-6) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 6:
        return False
    return all(bbox[i] - pad <= p[i] <= bbox[i + 3] + pad for i in range(3))


def _bbox_center(bbox: list[float]) -> tuple[float, float, float]:
    return ((bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2, (bbox[2] + bbox[5]) / 2)


def _resolve_entity(solids: list[dict[str, Any]], point: tuple[float, float, float]) -> tuple[dict[str, Any] | None, str]:
    contained = [s for s in solids if _bbox_contains(s.get("bounding_box"), point)]
    if contained:
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
    matches = [o for o in objects if entity_id in (o.get("topology_entities") or [])]
    if len(matches) == 1:
        return matches[0].get("node_id"), matches[0].get("linkage"), "resolved"
    if len(matches) > 1:
        return None, (matches[0].get("linkage") if matches else None), "ambiguous"
    return None, None, "none"


def map_cae_results(
    *,
    computed_metrics: dict[str, Any] | None,
    field_regions: dict[str, Any] | None,
    topology_map: dict[str, Any] | None,
    object_registry: dict[str, Any] | None,
) -> dict[str, Any]:
    """Correlate NEUTRAL CAE results with Shape IR nodes. Pure; neutral dicts in.

    ``computed_metrics`` is a neutral computed_metrics doc (load_cases[].results[]);
    ``field_regions`` is a neutral field_regions doc (regions[]).
    """
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    computed_metrics = computed_metrics or {}
    field_regions = field_regions or {}
    entities = (topology_map or {}).get("entities") or []
    solids = [e for e in entities if isinstance(e, dict) and e.get("type") == "solid"]
    objects = (object_registry or {}).get("objects") or []

    units: dict[str, str] = {}
    overall: list[dict[str, Any]] = []
    load_case_ids: list[str] = []
    for lc in computed_metrics.get("load_cases") or []:
        if not isinstance(lc, dict):
            continue
        lc_id = str(lc.get("id") or "load_case_1")
        if lc_id not in load_case_ids:
            load_case_ids.append(lc_id)
        for r in lc.get("results") or []:
            if not isinstance(r, dict):
                continue
            rtype = str(r.get("result_type") or "unknown")
            if r.get("unit"):
                units.setdefault(rtype, r["unit"])
            overall.append({
                "load_case_id": lc_id,
                "result_type": rtype,
                "metric": r.get("metric"),
                "max": r.get("max"),
                "min": r.get("min"),
                "average": r.get("average"),
                "unit": r.get("unit"),
            })

    default_lc = load_case_ids[0] if load_case_ids else "load_case_1"

    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    methods: set[str] = set()
    for region in field_regions.get("regions") or []:
        if not isinstance(region, dict):
            continue
        rtype = str(region.get("result_type") or "unknown")
        lc_id = str(region.get("load_case_id") or default_lc)
        if lc_id not in load_case_ids:
            load_case_ids.append(lc_id)
        center = region.get("center") or {}
        point = (float(center.get("x", 0.0)), float(center.get("y", 0.0)), float(center.get("z", 0.0)))
        value = region.get("value") or {}
        unit = value.get("unit")
        if unit:
            units.setdefault(rtype, unit)
        base = {
            "load_case_id": lc_id,
            "result_type": rtype,
            "region_id": region.get("id"),
            "value": value.get("peak", value.get("max")),
            "value_range": {"min": value.get("min"), "max": value.get("max")},
            "unit": unit,
            "location": {"x": point[0], "y": point[1], "z": point[2]},
            "node_count": region.get("node_count"),
        }
        solid, method = _resolve_entity(solids, point) if solids else (None, "none")
        if solid is None:
            unmapped.append({**base, "reason": "no topology solid near the result location"})
            continue
        methods.add(method)
        node_id, linkage, status = _node_for_entity(objects, str(solid.get("id")))
        affected = [str(solid.get("id"))] + [str(f) for f in (solid.get("face_ids") or [])]
        if status == "resolved":
            confidence = "high" if (method == "bbox_contains" and linkage in ("name_match", "source_ir_node")) else "medium"
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
            entry["note"] = f"region mapped to a topology body but not to a unique Shape IR node ({status})."
        mapped.append(entry)

    # ── provenance: solver/adapter, artifact versions, mapping methods, uncertainty ──
    cm_solver = computed_metrics.get("solver") if isinstance(computed_metrics.get("solver"), dict) else {}
    fr_solver = field_regions.get("solver") if isinstance(field_regions.get("solver"), dict) else {}
    solver = fr_solver or cm_solver or {}
    uncertain = (
        [{"region_id": m.get("region_id"), "reason": "node not unique (low confidence)"}
         for m in mapped if m["confidence"] == "low"]
        + [{"region_id": u.get("region_id"), "reason": u.get("reason")} for u in unmapped]
    )

    notes = ["Observational, solver-neutral CAE->Shape IR correlation; no solver/mesher executed."]
    if not (field_regions.get("regions")):
        notes.append("No field regions present — only scalar extrema were mapped.")
    if not objects:
        notes.append("No object registry — regions could not be tied to Shape IR nodes.")

    return {
        "format": "aieng.cae_result_map",
        "format_version": FORMAT_VERSION,
        "contract_version": CAE_CONTRACT_VERSION,
        "generated_at_utc": now,
        "solver": solver,
        "load_cases": load_case_ids or [default_lc],
        "units": units,
        "overall": overall,
        "mapped_results": mapped,
        "unmapped_regions": unmapped,
        "summary": {
            "mapped_count": len(mapped),
            "unmapped_count": len(unmapped),
            "resolved_to_node": sum(1 for m in mapped if m.get("source_ir_node")),
        },
        "provenance": {
            "solver_name": solver.get("name"),
            "solver_version": solver.get("version"),
            "adapter": solver.get("adapter"),
            "computed_metrics_schema": computed_metrics.get("schema_version"),
            "field_regions_schema": field_regions.get("schema_version"),
            "mapping_methods": sorted(methods),
            "unsupported_or_uncertain": uncertain,
        },
        "notes": notes,
        "credibility": classify_credibility("solver", solver_executed=True),
    }


def build_cae_result_map_for_package(package_path: str | Path) -> dict[str, Any]:
    """Build the result map from a package's NEUTRAL CAE artifacts (normalizing
    legacy CalculiX ``results/*`` on the fly when ``analysis/*`` is absent)."""
    package_path = Path(package_path)
    if not package_path.exists():
        return {"format": "aieng.cae_result_map", "format_version": FORMAT_VERSION,
                "error": f"package not found: {package_path}", "mapped_results": [], "unmapped_regions": []}
    neutral = load_neutral_cae_artifacts(package_path)
    with zipfile.ZipFile(package_path, "r") as zf:
        names = set(zf.namelist())
        topology_map = json.loads(zf.read(_TOPOLOGY_MEMBER).decode("utf-8")) if _TOPOLOGY_MEMBER in names else {}
        object_registry = json.loads(zf.read(_OBJECT_REGISTRY_MEMBER).decode("utf-8")) if _OBJECT_REGISTRY_MEMBER in names else {}
    result = map_cae_results(
        computed_metrics=neutral["computed_metrics"],
        field_regions=neutral["field_regions"],
        topology_map=topology_map,
        object_registry=object_registry,
    )
    result["provenance"]["artifact_source"] = neutral["source"]
    return result


def write_cae_result_map(package_path: str | Path) -> dict[str, Any]:
    """Persist neutral analysis/* (normalizing legacy CalculiX results/* if needed),
    then build + write analysis/cae_result_map.json."""
    package_path = Path(package_path)
    if package_path.exists():
        try:
            from .cae_result_contract import write_normalized_cae_artifacts
            write_normalized_cae_artifacts(package_path)  # persist neutral analysis/* from results/*
        except Exception:  # noqa: BLE001 - mapping still works via in-memory normalization
            pass
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
