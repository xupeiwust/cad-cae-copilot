"""Auto-parameterize a 2D contour topology writeback into sizing variables.

Phase 4 bridge: after ``opt.writeback_to_shape_ir`` (method=contour) emits an
``extruded_region`` body, this converter derives a small set of stable named
sizing parameters and writes:

  - ``analysis/design_study_problem.json`` (single-variable sizing study)
  - ``analysis/optimization_variables.json`` (resolved variable binding)

It is read-only with respect to the baseline geometry and refuses 3D / voxel
inputs with an honest ``needs_user_input`` / ``not_supported`` response.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.audit_event import build_audit_event, serialize_audit_events_jsonl
from aieng.converters.design_study import DESIGN_STUDY_PROBLEM_PATH
from aieng.converters.optimization_variables import resolve_optimization_variables

TOPOLOGY_OPTIMIZATION_PATH = "analysis/topology_optimization.json"
SHAPE_IR_PATH = "geometry/shape_ir.json"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"
AUDIT_EVENTS_PATH = "audit/events.jsonl"

THICKNESS_VAR_ID = "extrusion_thickness"
THICKNESS_PATH = "parts/0/params/EXTRUSION_THICKNESS"


class _RewriteError(Exception):
    """Package rewrite failed."""


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _read_json(zf: zipfile.ZipFile, name: str) -> Any:
    try:
        return json.loads(zf.read(name))
    except Exception:  # noqa: BLE001
        return None


def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
    """Atomic zip rewrite: preserve existing members, overwrite/add new ones."""
    tmp = package_path.with_suffix(".topoparam.tmp.aieng")
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
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise _RewriteError(f"package rewrite failed: {exc}") from exc


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clamp_bounds(value: float) -> tuple[float, float]:
    """Return sensible continuous bounds around a positive thickness value."""
    lo = max(0.1, value * 0.5)
    hi = value * 1.5
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


def _append_audit_event(
    package_path: Path,
    status: str,
    artifacts_written: list[str],
    reason: str | None = None,
) -> None:
    """Append a single audit event to ``audit/events.jsonl`` (creating if absent)."""
    existing: list[dict[str, Any]] = []
    with zipfile.ZipFile(package_path, "r") as zf:
        if AUDIT_EVENTS_PATH in zf.namelist():
            text = zf.read(AUDIT_EVENTS_PATH).decode("utf-8")
            existing = [
                json.loads(line)
                for line in text.splitlines()
                if line.strip()
            ]
    state_changes: dict[str, Any] = {"topology_parameterized": True}
    if reason:
        state_changes["reason"] = reason
    event = build_audit_event(
        tool="aieng.converters.topology_parameterization",
        event_type="optimization_artifact_written",
        status=status,
        artifacts_written=artifacts_written,
        evidence_created=[],
        state_changes=state_changes,
        geometry_revision=None,
        revalidation_status=None,
    )
    existing.append(event)
    _rewrite_package_members(package_path, {AUDIT_EVENTS_PATH: serialize_audit_events_jsonl(existing).encode()})


def parameterize_topology_writeback(package_path: str | Path) -> dict[str, Any]:
    """Derive sizing variables from a 2D contour topology writeback.

    Reads ``analysis/topology_optimization.json`` and ``geometry/shape_ir.json``,
    validates that the result is a 2D contour extrusion with a stable thickness
    parameter, and writes ``analysis/design_study_problem.json`` plus
    ``analysis/optimization_variables.json``.

    Returns a summary dict. The baseline geometry is never modified.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "error", "code": "package_not_found", "baseline_modified": False}

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            topo = _read_json(zf, TOPOLOGY_OPTIMIZATION_PATH)
            shape_ir = _read_json(zf, SHAPE_IR_PATH)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "code": "read_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "baseline_modified": False,
        }

    # ── Reject 3D / voxel / non-contour inputs ────────────────────────────────
    topo_dimension = (topo.get("dimension") if isinstance(topo, dict) else None) or ""
    if topo_dimension != "2d":
        return {
            "status": "needs_user_input",
            "code": "3d_or_non_2d_not_supported",
            "message": (
                "Only 2D contour topology results can be auto-parameterized; "
                f"found dimension={topo_dimension!r}."
            ),
            "baseline_modified": False,
        }

    if not isinstance(shape_ir, dict):
        return {
            "status": "needs_user_input",
            "code": "no_shape_ir",
            "message": "No readable geometry/shape_ir.json found in package.",
            "baseline_modified": False,
        }

    parts = [p for p in (shape_ir.get("parts") or []) if isinstance(p, dict)]
    if not parts:
        return {
            "status": "needs_user_input",
            "code": "no_recovered_body",
            "message": "Topology writeback did not produce a recoverable body part.",
            "baseline_modified": False,
        }

    node = parts[0]
    node_type = node.get("type")
    if node_type != "extruded_region":
        return {
            "status": "needs_user_input",
            "code": "no_stable_parameter",
            "message": (
                "Auto-parameterization only supports extruded_region contour bodies; "
                f"found node type {node_type!r}."
            ),
            "baseline_modified": False,
        }

    thickness = node.get("thickness")
    if not isinstance(thickness, (int, float)) or thickness <= 0:
        return {
            "status": "needs_user_input",
            "code": "no_stable_parameter",
            "message": (
                "Recovered extruded_region has no positive numeric thickness; "
                "cannot invent sizing variables."
            ),
            "baseline_modified": False,
        }

    # ── Build a minimal design-study problem for the recovered thickness ───────
    min_value, max_value = _clamp_bounds(float(thickness))
    design_space_node = (
        (topo.get("problem") or {}).get("design_space_node")
        or node.get("id")
        or "recovered_body"
    )
    study_id = f"topo_to_sizing_{design_space_node}"

    problem: dict[str, Any] = {
        "format": "aieng.design_study_problem",
        "schema_version": "0.1",
        "id": study_id,
        "name": f"Sizing study on {design_space_node}",
        "variables": [
            {
                "id": THICKNESS_VAR_ID,
                "path": THICKNESS_PATH,
                "type": "continuous",
                "current_value": float(thickness),
                "min_value": min_value,
                "max_value": max_value,
                "unit": "mm",
                "safe_to_modify": True,
                "protected": False,
                "semantic_role": "extrusion_thickness",
                "part_id": node.get("id"),
            }
        ],
        "objective": {"sense": "minimize", "metric": "volume"},
        "constraints": [],
        "settings": {"max_variables_per_candidate": 1, "require_reasoning": False},
        "provenance": {
            "from_topology_writeback": True,
            "source_artifacts": [TOPOLOGY_OPTIMIZATION_PATH, SHAPE_IR_PATH],
            "design_space_node": design_space_node,
            "production_ready": False,
            "parameterized_at": _now(),
            "claim_advancement": "none",
        },
    }

    variables_doc = resolve_optimization_variables(
        problem,
        study_id=study_id,
        parameter_index=[
            {
                "feature_id": node.get("id"),
                "feature_name": node.get("label") or node.get("id"),
                "scope": "local",
                "parameter_name": "extrusion_thickness",
                "cad_parameter_name": "EXTRUSION_THICKNESS",
                "current_value": float(thickness),
                "min_value": min_value,
                "max_value": max_value,
                "unit": "mm",
            }
        ],
    )
    variables_doc["schema_version"] = "0.2"
    variables_doc["provenance"]["created_at"] = _now()
    variables_doc["provenance"]["source"] = "aieng.converters.topology_parameterization"
    variables_doc["provenance"]["source_artifacts"] = [
        TOPOLOGY_OPTIMIZATION_PATH,
        SHAPE_IR_PATH,
    ]

    members = {
        DESIGN_STUDY_PROBLEM_PATH: _dumps(problem),
        OPTIMIZATION_VARIABLES_PATH: _dumps(variables_doc),
    }

    try:
        _rewrite_package_members(package_path, members)
        _append_audit_event(
            package_path,
            status="completed",
            artifacts_written=[DESIGN_STUDY_PROBLEM_PATH, OPTIMIZATION_VARIABLES_PATH],
        )
    except _RewriteError as exc:
        return {
            "status": "error",
            "code": "write_failed",
            "message": str(exc),
            "baseline_modified": False,
        }

    return {
        "status": "ok",
        "study_id": study_id,
        "variable_count": 1,
        "variables": [THICKNESS_VAR_ID],
        "artifacts": [DESIGN_STUDY_PROBLEM_PATH, OPTIMIZATION_VARIABLES_PATH],
        "baseline_modified": False,
        "claim_advancement": "none",
    }
