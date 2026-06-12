"""Chain orchestration: topology writeback → sizing study (#107).

One deterministic step that:

1. Verifies a 2D/extrudable topology result + contour writeback exist.
2. Invokes ``parameterize_topology_writeback`` (#106) to produce
   ``analysis/design_study_problem.json`` + ``analysis/optimization_variables.json``.
3. Derives ``analysis/optimization_objectives.json``,
   ``analysis/optimization_constraints.json``,
   ``analysis/optimization_study.json`` and appends a chain-linkage entry to
   ``analysis/optimization_decision_log.json``.
4. Records provenance and an audit event.

Refuses 3D / voxel / missing inputs with honest messaging and no partial writes.
Baseline geometry is never modified.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.audit_event import build_audit_event, serialize_audit_events_jsonl
from aieng.optimization_artifacts import (
    DESIGN_STUDY_PROBLEM_PATH,
    OPTIMIZATION_ARTIFACT_PATHS,
    validate_optimization_artifact_set,
)

from .topology_parameterization import (
    AUDIT_EVENTS_PATH,
    OPTIMIZATION_VARIABLES_PATH,
    TOPOLOGY_OPTIMIZATION_PATH,
    parameterize_topology_writeback,
)

OPTIMIZATION_OBJECTIVES_PATH = OPTIMIZATION_ARTIFACT_PATHS["objectives"]
OPTIMIZATION_CONSTRAINTS_PATH = OPTIMIZATION_ARTIFACT_PATHS["constraints"]
OPTIMIZATION_STUDY_PATH = OPTIMIZATION_ARTIFACT_PATHS["study"]
OPTIMIZATION_DECISION_LOG_PATH = OPTIMIZATION_ARTIFACT_PATHS["decision_log"]


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(zf: zipfile.ZipFile, name: str) -> Any:
    try:
        return json.loads(zf.read(name))
    except Exception:  # noqa: BLE001
        return None


def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
    """Atomic zip rewrite: preserve existing members, overwrite/add new ones."""
    tmp = package_path.with_suffix(".toposizing.tmp.aieng")
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


def _objectives_from_problem(problem: dict[str, Any], study_id: str) -> dict[str, Any] | None:
    """Build an optimization_objectives document from the design-study problem."""
    problem_id = problem.get("id")
    raw_objectives: list[dict[str, Any]] = []
    if isinstance(problem.get("objectives"), list):
        raw_objectives = [obj for obj in problem["objectives"] if isinstance(obj, dict)]
    elif isinstance(problem.get("objective"), dict):
        raw_objectives = [problem["objective"]]
    if not raw_objectives:
        return None

    objectives: list[dict[str, Any]] = []
    for idx, obj in enumerate(raw_objectives):
        sense = obj.get("sense") or obj.get("direction") or "minimize"
        direction = sense if sense in ("minimize", "maximize", "target") else "minimize"
        objectives.append({
            "id": obj.get("id") or f"objective_{idx + 1}",
            "metric": obj.get("metric") or "volume",
            "direction": direction,
            "weight": obj.get("weight", 1.0),
            "target_value": obj.get("target_value") if "target_value" in obj else None,
            "unit": obj.get("unit"),
            "candidate_ids": [],
            "evidence_refs": [],
        })

    doc: dict[str, Any] = {
        "format": "aieng.optimization_objectives",
        "schema_version": "0.1",
        "study_id": study_id,
        "design_study_problem_ref": DESIGN_STUDY_PROBLEM_PATH,
        "objectives": objectives,
        "candidate_ids": [],
        "provenance": {
            "created_at": _now(),
            "created_by": "aieng.converters.topology_to_sizing",
            "source": "topology_to_sizing",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
    }
    if problem_id is not None:
        doc["design_study_problem_id"] = problem_id
    return doc


def _constraints_from_problem(problem: dict[str, Any], study_id: str) -> dict[str, Any]:
    """Build an optimization_constraints document from the design-study problem."""
    problem_id = problem.get("id")
    raw_constraints = [c for c in (problem.get("constraints") or []) if isinstance(c, dict)]
    constraints: list[dict[str, Any]] = []
    for idx, c in enumerate(raw_constraints):
        ctype = c.get("type") or "unknown"
        metric = ctype
        operator = "<="
        limit = c.get("limit")
        if ctype in ("max_stress", "max_displacement"):
            operator = "<="
            metric = ctype.replace("max_", "")
        elif ctype in ("min_wall", "min_fillet"):
            operator = ">="
        constraints.append({
            "id": c.get("id") or f"constraint_{idx + 1}",
            "metric": metric,
            "operator": operator,
            "limit": limit,
            "lower_limit": None,
            "upper_limit": limit if operator in ("<=", "<") else None,
            "unit": c.get("unit"),
            "hard": True,
            "penalty_weight": None,
            "unknown_policy": "needs_user_input",
            "candidate_ids": [],
            "evidence_refs": [],
        })

    doc: dict[str, Any] = {
        "format": "aieng.optimization_constraints",
        "schema_version": "0.1",
        "study_id": study_id,
        "design_study_problem_ref": DESIGN_STUDY_PROBLEM_PATH,
        "constraints": constraints,
        "candidate_ids": [],
        "provenance": {
            "created_at": _now(),
            "created_by": "aieng.converters.topology_to_sizing",
            "source": "topology_to_sizing",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
    }
    if problem_id is not None:
        doc["design_study_problem_id"] = problem_id
    return doc


def _study_document(
    problem: dict[str, Any],
    study_id: str,
    *,
    source_artifacts: list[str],
) -> dict[str, Any]:
    """Build the optimization_study envelope."""
    problem_id = problem.get("id")
    doc: dict[str, Any] = {
        "format": "aieng.optimization_study",
        "schema_version": "0.1",
        "study_id": study_id,
        "design_study_problem_ref": DESIGN_STUDY_PROBLEM_PATH,
        "algorithm": {"name": "manual", "phase": 1, "bounded_step": True, "seed": None},
        "sampling": {"requested_candidate_count": 5, "max_candidate_count": 20, "include_baseline": True, "seed": None},
        "budget": {"max_candidates": 20, "max_iterations": 1, "max_solver_runs": 0},
        "status": "defined",
        "artifact_refs": {
            "variables": OPTIMIZATION_VARIABLES_PATH,
            "objectives": OPTIMIZATION_OBJECTIVES_PATH,
            "constraints": OPTIMIZATION_CONSTRAINTS_PATH,
            "decision_log": OPTIMIZATION_DECISION_LOG_PATH,
            "iterations": "analysis/design_study_iterations.json",
            "ranking": "analysis/design_study_candidate_ranking.json",
            "acceptance": "analysis/design_study_acceptance.json",
        },
        "candidate_ids": [],
        "provenance": {
            "created_at": _now(),
            "created_by": "aieng.converters.topology_to_sizing",
            "source": "topology_to_sizing",
            "claim_advancement": "none",
        },
        "claim_policy": {
            "advisory_only": True,
            "baseline_unchanged": True,
            "human_approval_required_for_acceptance": True,
            "claim_advancement": "none",
        },
        "topology_to_sizing_chain": {
            "source_artifacts": source_artifacts,
            "design_space_node": problem.get("provenance", {}).get("design_space_node"),
            "production_ready": False,
        },
    }
    if problem_id is not None:
        doc["design_study_problem_id"] = problem_id
    return doc


def _decision_log_document(
    problem: dict[str, Any],
    study_id: str,
    *,
    existing: dict[str, Any] | None = None,
    source_artifacts: list[str],
    reason_codes: list[str],
    note: str,
) -> dict[str, Any]:
    """Build or append a topology→sizing decision-log entry."""
    problem_id = problem.get("id")
    if existing is None:
        existing = {
            "format": "aieng.optimization_decision_log",
            "schema_version": "0.1",
            "study_id": study_id,
            "design_study_problem_ref": DESIGN_STUDY_PROBLEM_PATH,
            "entries": [],
            "candidate_ids": [],
            "provenance": {
                "created_at": _now(),
                "created_by": "aieng.converters.topology_to_sizing",
                "source": "topology_to_sizing",
                "claim_advancement": "none",
            },
            "claim_policy": {
                "advisory_only": True,
                "baseline_unchanged": True,
                "human_approval_required_for_acceptance": True,
                "claim_advancement": "none",
            },
        }
        if problem_id is not None:
            existing["design_study_problem_id"] = problem_id

    decision_number = len(existing.get("entries") or []) + 1
    existing.setdefault("entries", []).append({
        "decision_id": f"decision_topo_to_sizing_{decision_number:04d}",
        "timestamp": _now(),
        "decision": "topology_to_sizing_linkage",
        "reason_codes": reason_codes,
        "requires_human_review": True,
        "candidate_ids": [],
        "metric_refs": [],
        "note": note,
    })
    return existing


def _append_audit_event(
    package_path: Path,
    status: str,
    artifacts_written: list[str],
    reason: str | None = None,
) -> None:
    """Append a single audit event to ``audit/events.jsonl``."""
    existing: list[dict[str, Any]] = []
    with zipfile.ZipFile(package_path, "r") as zf:
        if AUDIT_EVENTS_PATH in zf.namelist():
            text = zf.read(AUDIT_EVENTS_PATH).decode("utf-8")
            existing = [json.loads(line) for line in text.splitlines() if line.strip()]
    state_changes: dict[str, Any] = {"topology_to_sizing": True}
    if reason:
        state_changes["reason"] = reason
    event = build_audit_event(
        tool="aieng.converters.topology_to_sizing",
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


def topology_to_sizing(package_path: str | Path) -> dict[str, Any]:
    """Orchestrate topology writeback → sizing study with chain linkage.

    This is a single bounded step: it verifies the topology result and contour
    writeback, invokes the P4-1 parameterizer, and writes the full
    optimization-study envelope plus a decision-log entry.

    Returns a summary dict. The baseline geometry is never modified.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "error", "code": "package_not_found", "baseline_modified": False}

    # 1. Run P4-1 parameterization first. It performs all input validation and
    #    refuses 3D / voxel / unstable bodies honestly.
    param_result = parameterize_topology_writeback(package_path)
    if param_result.get("status") != "ok":
        return {
            **param_result,
            "baseline_modified": param_result.get("baseline_modified", False),
        }

    study_id = param_result["study_id"]
    source_artifacts = [TOPOLOGY_OPTIMIZATION_PATH, "geometry/shape_ir.json"]

    # 2. Read back the artifacts produced by parameterization.
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH)
            variables_doc = _read_json(zf, OPTIMIZATION_VARIABLES_PATH)
            existing_decision_log = _read_json(zf, OPTIMIZATION_DECISION_LOG_PATH)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "code": "read_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "baseline_modified": False,
        }

    if not isinstance(problem, dict) or not isinstance(variables_doc, dict):
        return {
            "status": "error",
            "code": "parameterization_missing",
            "message": "Parameterization artifacts missing after successful parameterize_topology_writeback.",
            "baseline_modified": False,
        }

    # 3. Build derived optimization artifacts.
    objectives_doc = _objectives_from_problem(problem, study_id)
    if objectives_doc is None:
        return {
            "status": "needs_user_input",
            "code": "no_objective",
            "message": "Design-study problem has no objective; cannot create sizing study.",
            "baseline_modified": False,
        }

    constraints_doc = _constraints_from_problem(problem, study_id)
    study_doc = _study_document(problem, study_id, source_artifacts=source_artifacts)
    decision_log_doc = _decision_log_document(
        problem,
        study_id,
        existing=existing_decision_log if isinstance(existing_decision_log, dict) else None,
        source_artifacts=source_artifacts,
        reason_codes=["initial_mvp", "small_number_of_design_variables"],
        note=(
            "Linked topology optimization result to a sizing study via contour writeback. "
            "Variables derived from the recovered extruded_region. "
            "production_ready=false; human approval required before acceptance."
        ),
    )

    # 4. Validate the complete artifact set before writing.
    validation_documents: dict[str, dict[str, Any]] = {
        "study": study_doc,
        "variables": variables_doc,
        "objectives": objectives_doc,
        "constraints": constraints_doc,
        "decision_log": decision_log_doc,
    }
    validation_issues = validate_optimization_artifact_set(
        validation_documents,
        design_study_problem=problem,
    )
    if validation_issues:
        return {
            "status": "error",
            "code": "artifact_validation_failed",
            "message": "; ".join(validation_issues),
            "baseline_modified": False,
        }

    # 5. Write all artifacts atomically.
    members = {
        OPTIMIZATION_OBJECTIVES_PATH: _dumps(objectives_doc),
        OPTIMIZATION_CONSTRAINTS_PATH: _dumps(constraints_doc),
        OPTIMIZATION_STUDY_PATH: _dumps(study_doc),
        OPTIMIZATION_DECISION_LOG_PATH: _dumps(decision_log_doc),
    }
    try:
        _rewrite_package_members(package_path, members)
        _append_audit_event(
            package_path,
            status="completed",
            artifacts_written=list(members.keys()),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "code": "write_failed",
            "message": f"{type(exc).__name__}: {exc}",
            "baseline_modified": False,
        }

    return {
        "status": "ok",
        "study_id": study_id,
        "variable_count": len(variables_doc.get("variables") or []),
        "artifacts": list(members.keys()) + param_result["artifacts"],
        "baseline_modified": False,
        "claim_advancement": "none",
    }
