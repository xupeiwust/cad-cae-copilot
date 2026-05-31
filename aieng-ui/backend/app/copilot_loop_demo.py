"""Deterministic demo fixture for the Copilot decision review workbench.

Creates a new project, writes a bracket-lightweighting `.aieng` package,
and pre-bakes two persisted Copilot loops (one rejected, one approved
with a mock CAD edit). Both loops have generated reports so the loop
history, compare panel, report diff, structured highlights, and
decision-review export are immediately exercisable in the UI without
running real Gmsh/CalculiX.

The pre-baked data is clearly labelled as demo/fixture data. It does not
represent real simulation results; it is a deterministic decision record
suitable for product demos and reviewer onboarding.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import Settings, now_iso, read_json
from .copilot_loop import (
    _build_loop_report,
    _loop_dir,
    _loop_path,
    _save_loop,
)
from .project_io import default_project, project_dir, save_project


DEMO_KIND = "bracket-lightweighting"


def _is_demo_project(metadata: dict[str, Any]) -> bool:
    """A project counts as a Copilot-loop demo if its metadata explicitly says so.

    Two separate keys are checked so older demo seeds (which set only
    ``demo: true``) still match. Anything without these flags — i.e. a real
    user project — is never deleted, modified, or considered a demo by us.
    """
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("demo_copilot_loop")) or metadata.get("demo_kind") == DEMO_KIND


def _find_demo_projects(settings: Settings) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not settings.projects_root.exists():
        return found
    for meta_path in settings.projects_root.glob("*/metadata.json"):
        try:
            metadata = read_json(meta_path, {})
        except Exception:
            continue
        if _is_demo_project(metadata):
            found.append(metadata)
    found.sort(key=lambda m: m.get("updated_at") or m.get("created_at") or "", reverse=True)
    return found


def _delete_project_dir(settings: Settings, project_id: str) -> None:
    """Recursively delete a project directory.

    Caller MUST verify the project is a demo project (`_is_demo_project`)
    before invoking this. The function additionally checks the resolved
    path is inside ``settings.projects_root`` so a malformed project_id
    cannot escape that root.
    """
    base = settings.projects_root.resolve()
    target = (settings.projects_root / project_id).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid project path") from exc
    if target.exists():
        shutil.rmtree(target, ignore_errors=False)


def reset_demo_projects(settings: Settings) -> dict[str, Any]:
    """Remove all Copilot-loop demo projects from the workspace.

    Only projects that this seeder marked as demo are deleted. Real user
    projects, even if loaded into the same workspace, are never touched.
    """
    removed: list[dict[str, Any]] = []
    for metadata in _find_demo_projects(settings):
        project_id = metadata.get("id")
        if not isinstance(project_id, str):
            continue
        try:
            _delete_project_dir(settings, project_id)
            removed.append({"project_id": project_id, "name": metadata.get("name")})
        except HTTPException:
            raise
        except Exception:
            # Best-effort cleanup; do not block other deletions.
            continue
    return {
        "schema_version": "0.1",
        "removed": removed,
        "notice": (
            "Reset removed only projects flagged as Copilot-loop demo "
            "fixtures. Real user projects were not modified."
        ),
    }


def _demo_package_contents() -> dict[str, str]:
    """Authoritative fixture package contents for the demo project.

    Returns a dict of package-internal path → text contents. All numbers
    are clearly fixture data and the manifest records that explicitly.
    """
    design_targets = {
        "schema_version": "0.1.1",
        "targets": [
            {
                "target_id": "mass_reduction_10pct",
                "target_type": "mass_reduction_target",
                "comparator": "reduce_by_at_least",
                "threshold": 10.0,
                "priority": "high",
            },
            {
                "target_id": "safety_factor_min",
                "target_type": "minimum_safety_factor",
                "comparator": ">=",
                "threshold": 1.5,
                "priority": "critical",
            },
        ],
    }
    parsed_features = {
        "features": [
            {
                "id": "back_wall",
                "kind": "wall",
                "parameters": {"thickness_mm": 20.0, "width_mm": 120.0},
                "mass_contribution_kg": 1.51,
            },
            {
                "id": "central_rib",
                "kind": "rib",
                "parameters": {"thickness_mm": 8.0, "length_mm": 100.0},
                "mass_contribution_kg": 0.38,
            },
            {
                "id": "mounting_flange",
                "kind": "flange",
                "parameters": {"thickness_mm": 12.0},
                "mass_contribution_kg": 0.42,
                "protected": True,
            },
        ],
    }
    feature_graph = {
        "features": [
            {
                "id": "back_wall",
                "type": "wall",
                "name": "Back wall",
                "cad_object_name": "BackWall",
                "parameters": [
                    {
                        "name": "thickness_mm",
                        "current_value": 20.0,
                        "min_value": 1.0,
                        "max_value": 40.0,
                        "editability": {"executable": True},
                        "cad_parameter_name": "Thickness",
                    }
                ],
            }
        ]
    }
    stress = {
        "schema_version": "0.1",
        "load_case_id": "load_case_001",
        "minimum_required_safety_factor": 1.5,
        "features": [
            {"feature_ref": "back_wall", "max_von_mises_stress_mpa": 22.0, "safety_factor": 15.91},
            {"feature_ref": "central_rib", "max_von_mises_stress_mpa": 195.0, "safety_factor": 1.79},
        ],
    }
    metrics = {
        "schema_version": "0.1",
        "metrics_source": {"tool": "fixture", "software": "mock_postprocessor"},
        "load_cases": [
            {
                "id": "load_case_001",
                "metrics": {
                    "max_von_mises_stress": {"value": 195.0, "unit": "MPa"},
                    "minimum_safety_factor": {"value": 1.79},
                    "total_mass": {"value": 2.30, "unit": "kg"},
                },
            }
        ],
    }
    manifest = {
        "model_id": "copilot-loop-demo",
        "demo": True,
        "description": (
            "Deterministic demo fixture: bracket lightweighting decision review. "
            "Computed values are mock/fixture data and do not represent real "
            "simulation results. A qualified engineer must review the underlying "
            "evidence before any acceptance decision."
        ),
        "resources": {"geometry": {"source": "geometry/source.step"}},
    }
    return {
        "manifest.json": json.dumps(manifest),
        "geometry/source.step": "ISO-10303-21;\nEND-ISO-10303-21;\n",
        "task/design_targets.yaml": _yaml_dump(design_targets),
        "simulation/cae_imports/parsed_features.json": json.dumps(parsed_features),
        "graph/feature_graph.json": json.dumps(feature_graph),
        "results/stress_by_feature.json": json.dumps(stress),
        "results/computed_metrics.json": json.dumps(metrics),
    }


def _yaml_dump(data: Any) -> str:
    """Minimal YAML emitter for nested dicts/lists of primitives.

    Avoids adding PyYAML as a runtime dep; the .aieng readers in this repo
    accept JSON-style YAML, which is what this emitter produces.
    """
    return json.dumps(data, indent=2)


def _write_demo_package(package_path: Path) -> None:
    package_path.parent.mkdir(parents=True, exist_ok=True)
    contents = _demo_package_contents()
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for member, text in contents.items():
            zf.writestr(member, text)


def _build_step(
    *,
    id: str,
    title: str,
    kind: str,
    requires_approval: bool,
    status: str,
    summary: str,
    limitation: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "kind": kind,
        "requiresApproval": requires_approval,
        "status": status,
        "summary": summary,
        "limitation": limitation,
        "warnings": warnings or [],
        "errors": errors or [],
        "artifacts": artifacts or [],
        "toolCalls": tool_calls or [],
        "data": data or {},
        "updated_at": now_iso(),
    }


def _demo_proposal() -> dict[str, Any]:
    return {
        "proposal_id": "prop_back_wall_thin_20_to_10",
        "feature_ref": "back_wall",
        "action_type": "thin",
        "parameter_change": {"name": "thickness_mm", "from": 20.0, "to": 10.0},
        "rationale": (
            "Back wall safety factor is 15.91 — far above the required 1.5. "
            "Thinning halves the wall contribution to mass while keeping the "
            "predicted bending-floor safety factor well above target."
        ),
        "targets_addressed": ["mass_reduction_10pct"],
    }


def _demo_verdict() -> dict[str, Any]:
    return {
        "proposal_id": "prop_back_wall_thin_20_to_10",
        "verdict": "pass",
        "checks": [
            {"check_id": "param_bounds", "status": "pass", "message": "10.0 is within [1.0, 40.0]"},
            {"check_id": "regression_floor", "status": "pass", "message": "Predicted SF_after≈3.98 ≥ 1.5"},
            {"check_id": "manufacturability_min_thickness", "status": "pass", "message": "10.0 ≥ 2.0 mm floor"},
        ],
        "blockers": [],
        "warnings_from_checks": [],
    }


def _build_baseline_evidence() -> dict[str, Any]:
    return {
        "member_count": 7,
        "has_design_targets": True,
        "has_computed_metrics": True,
        "has_result_summary": False,
        "has_preprocessing_summary": False,
        "revalidation_status": None,
        "result_summary": None,
        "preprocessing_summary": None,
    }


def _build_baseline_metrics() -> dict[str, Any]:
    return {
        "metrics": {
            "max_von_mises_stress": {"value": 195.0, "unit": "MPa"},
            "minimum_safety_factor": {"value": 1.79},
            "total_mass": {"value": 2.30, "unit": "kg"},
        },
        "design_target_comparisons": None,
        "source": "results/computed_metrics.json (demo fixture)",
    }


def _build_after_metrics_approved() -> dict[str, Any]:
    return {
        "metrics": {
            "max_von_mises_stress": {"value": 198.0, "unit": "MPa"},
            "minimum_safety_factor": {"value": 1.74},
            "total_mass": {"value": 1.55, "unit": "kg"},
        },
        "design_target_comparisons": {
            "items": [
                {
                    "target_id": "mass_reduction_10pct",
                    "target_type": "mass_reduction_target",
                    "expected": "≤ 2.07 kg",
                    "actual": "1.55 kg",
                    "comparator": "reduce_by_at_least",
                    "status": "pass",
                    "notes": "Computed on demo fixture metrics; not certified.",
                },
                {
                    "target_id": "safety_factor_min",
                    "target_type": "minimum_safety_factor",
                    "expected": ">= 1.5",
                    "actual": 1.74,
                    "comparator": ">=",
                    "status": "pass",
                    "notes": "Computed on demo fixture metrics; not certified.",
                },
            ],
        },
        "source": "demo fixture (post-edit recomputation)",
    }


def _build_metric_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    keys = sorted(set(before.get("metrics", {})) | set(after.get("metrics", {})))
    for key in keys:
        b = (before.get("metrics") or {}).get(key) or {}
        a = (after.get("metrics") or {}).get(key) or {}
        bv = b.get("value")
        av = a.get("value")
        delta = (av - bv) if isinstance(bv, (int, float)) and isinstance(av, (int, float)) else None
        direction = "unknown"
        if delta is not None:
            if key in {"max_von_mises_stress"}:
                direction = "improved" if delta < 0 else "regressed" if delta > 0 else "unchanged"
            elif key in {"minimum_safety_factor"}:
                direction = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
            elif "mass" in key:
                direction = "improved" if delta < 0 else "regressed" if delta > 0 else "unchanged"
        rows.append({
            "metric": key,
            "before": bv,
            "after": av,
            "delta": delta,
            "unit": a.get("unit") or b.get("unit"),
            "direction": direction,
        })
    return {"metrics": rows}


def _bake_rejected_loop(project_id: str, package_path: Path, loop_id: str) -> dict[str, Any]:
    proposal = _demo_proposal()
    verdict = _demo_verdict()
    baseline = _build_baseline_metrics()
    steps = [
        _build_step(
            id="inspect_evidence",
            title="Inspect package evidence",
            kind="read_only",
            requires_approval=False,
            status="completed",
            summary="Inspected 7 demo package member(s).",
            limitation="Read-only inspection does not validate engineering correctness.",
            data=_build_baseline_evidence(),
        ),
        _build_step(
            id="recommend_modification",
            title="Recommend CAD modification",
            kind="read_only",
            requires_approval=False,
            status="completed",
            summary=f"Selected proposal {proposal['proposal_id']}: back_wall thin.",
            limitation="Recommendations are hypotheses, not solver evidence.",
            data={"selected_proposal": proposal, "proposal_count": 1},
        ),
        _build_step(
            id="verify_proposal",
            title="Verify proposal",
            kind="review",
            requires_approval=False,
            status="completed",
            summary="Verification verdict: pass.",
            limitation="Verification is heuristic and does not replace re-simulation.",
            data={"proposal": proposal, "verdict": verdict},
        ),
        _build_step(
            id="apply_cad_edit",
            title="Approve/apply CAD parameter edit",
            kind="mutation",
            requires_approval=True,
            status="skipped",
            summary="User rejected approval; operation was not executed.",
            limitation="Only declared parameter edits are supported.",
            warnings=["reason=user_rejected"],
            tool_calls=[{"toolName": "cad.edit_parameter", "status": "rejected", "runId": "demo-run-reject"}],
            data={"reason": "user_rejected"},
        ),
        _build_step(
            id="mark_stale",
            title="Mark stale downstream artifacts",
            kind="postprocess",
            requires_approval=False,
            status="skipped",
            summary="No CAD edit was applied; no new stale evidence was introduced.",
        ),
        _build_step(
            id="prepare_solver",
            title="Prepare mesh / solver run",
            kind="read_only",
            requires_approval=False,
            status="skipped",
            summary="No edit was applied; preparing the solver was not necessary on the unchanged baseline.",
        ),
        _build_step(
            id="run_mesh_solver",
            title="Run mesh / solver",
            kind="expensive",
            requires_approval=True,
            status="skipped",
            summary="Mesh/solver execution was not started because the CAD edit was rejected.",
            warnings=["Gmsh/CalculiX availability is not faked in the demo."],
        ),
        _build_step(
            id="extract_results",
            title="Extract solver results",
            kind="postprocess",
            requires_approval=False,
            status="skipped",
            summary="No new solver run to extract results from.",
        ),
        _build_step(
            id="refresh_summary",
            title="Refresh CAE summary",
            kind="postprocess",
            requires_approval=False,
            status="skipped",
            summary="No solver activity to summarise on the unchanged baseline.",
        ),
        _build_step(
            id="compare_targets",
            title="Compare design targets",
            kind="review",
            requires_approval=False,
            status="partial",
            summary="No before/after delta available; the baseline is unchanged.",
            warnings=["No before/after metric delta could be computed from available evidence."],
        ),
        _build_step(
            id="generate_report",
            title="Generate loop report",
            kind="review",
            requires_approval=False,
            status="completed",
            summary="Generated closed-loop Copilot report.",
        ),
    ]
    loop = {
        "schema_version": "0.1",
        "loop_id": loop_id,
        "project_id": project_id,
        "package_path": str(package_path),
        "status": "completed",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "strictness": "default",
        "selected_proposal_id": proposal["proposal_id"],
        "current_step_id": None,
        "steps": steps,
        "context": {
            "baseline": baseline,
            "evidence": _build_baseline_evidence(),
            "recommendation_response": {
                "recommendations": {"proposals": [proposal]},
                "verification": {"verdicts": [verdict]},
            },
            "selected_proposal": proposal,
            "apply_rejected": True,
            "claim_boundary": {"claims_advanced": False},
        },
    }
    return loop


def _bake_approved_loop(project_id: str, package_path: Path, loop_id: str) -> dict[str, Any]:
    proposal = _demo_proposal()
    verdict = _demo_verdict()
    baseline = _build_baseline_metrics()
    after = _build_after_metrics_approved()
    comparison = _build_metric_comparison(baseline, after)
    stale_artifacts = [
        "results/computed_metrics.json",
        "results/stress_by_feature.json",
        "results/result_summary.json",
    ]
    steps = [
        _build_step(
            id="inspect_evidence",
            title="Inspect package evidence",
            kind="read_only",
            requires_approval=False,
            status="completed",
            summary="Inspected 7 demo package member(s).",
            data=_build_baseline_evidence(),
        ),
        _build_step(
            id="recommend_modification",
            title="Recommend CAD modification",
            kind="read_only",
            requires_approval=False,
            status="completed",
            summary=f"Selected proposal {proposal['proposal_id']}: back_wall thin.",
            data={"selected_proposal": proposal, "proposal_count": 1},
        ),
        _build_step(
            id="verify_proposal",
            title="Verify proposal",
            kind="review",
            requires_approval=False,
            status="completed",
            summary="Verification verdict: pass.",
            data={"proposal": proposal, "verdict": verdict},
        ),
        _build_step(
            id="apply_cad_edit",
            title="Approve/apply CAD parameter edit",
            kind="mutation",
            requires_approval=True,
            status="completed",
            summary="Mock CAD edit applied (demo fixture; not a real CAD execution).",
            warnings=["Approved operation completed. Downstream evidence may now be stale until re-simulation."],
            tool_calls=[{"toolName": "cad.edit_parameter", "status": "success", "runId": "demo-run-approve"}],
            artifacts=[{"path": "geometry/source.step", "label": "modified (mock)"}],
            data={
                "output": {
                    "status": "success",
                    "summary": "demo edit",
                    "warnings": [],
                    "errors": [],
                }
            },
        ),
        _build_step(
            id="mark_stale",
            title="Mark stale downstream artifacts",
            kind="postprocess",
            requires_approval=False,
            status="completed",
            summary="Downstream geometry-dependent evidence is marked stale.",
            artifacts=[{"path": p, "label": "stale"} for p in stale_artifacts],
            data={"stale_artifacts": stale_artifacts},
        ),
        _build_step(
            id="prepare_solver",
            title="Prepare mesh / solver run",
            kind="read_only",
            requires_approval=False,
            status="partial",
            summary="Solver preflight indicates inputs are not ready in the demo environment.",
            warnings=["Gmsh/CalculiX availability is not faked in the demo."],
        ),
        _build_step(
            id="run_mesh_solver",
            title="Run mesh / solver",
            kind="expensive",
            requires_approval=True,
            status="skipped",
            summary="Mesh/solver execution was not started because preflight is not ready.",
            warnings=["Demo fixture: solver unavailable. Success is never faked."],
        ),
        _build_step(
            id="extract_results",
            title="Extract solver results",
            kind="postprocess",
            requires_approval=False,
            status="skipped",
            summary="No new solver run to extract results from.",
        ),
        _build_step(
            id="refresh_summary",
            title="Refresh CAE summary",
            kind="postprocess",
            requires_approval=False,
            status="partial",
            summary="Refreshed CAE summary against pre-baked demo metrics. Not a re-simulation.",
        ),
        _build_step(
            id="compare_targets",
            title="Compare design targets",
            kind="review",
            requires_approval=False,
            status="completed",
            summary="Compared available metrics and design target status on demo fixture data.",
            data={"before": baseline, "after": after, "comparison": comparison},
        ),
        _build_step(
            id="generate_report",
            title="Generate loop report",
            kind="review",
            requires_approval=False,
            status="completed",
            summary="Generated closed-loop Copilot report.",
        ),
    ]
    loop = {
        "schema_version": "0.1",
        "loop_id": loop_id,
        "project_id": project_id,
        "package_path": str(package_path),
        "status": "completed",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "strictness": "default",
        "selected_proposal_id": proposal["proposal_id"],
        "current_step_id": None,
        "steps": steps,
        "context": {
            "baseline": baseline,
            "evidence": _build_baseline_evidence(),
            "recommendation_response": {
                "recommendations": {"proposals": [proposal]},
                "verification": {"verdicts": [verdict]},
            },
            "selected_proposal": proposal,
            "apply_rejected": False,
            "stale_artifacts": stale_artifacts,
            "after": after,
            "metric_comparison": comparison,
            "claim_boundary": {"claims_advanced": False},
        },
    }
    return loop


def _bake_report_into_package_and_local(
    settings: Settings,
    project_id: str,
    package_path: Path,
    loop: dict[str, Any],
) -> None:
    """Generate the loop report and persist it in both locations."""
    report = _build_loop_report(loop)
    report_member = f"reports/copilot_loop/{loop['loop_id']}.md"
    local = project_dir(settings, project_id) / "copilot_loops" / f"{loop['loop_id']}.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(report["markdown"], encoding="utf-8")
    # Inline-write into the package zip (the regular write_artifact_to_package
    # helper rewrites the entire zip; use the same approach by adding the
    # member if it does not exist).
    _add_member_to_zip(package_path, report_member, report["markdown"])
    report["artifact_path"] = report_member
    loop.setdefault("context", {})["report"] = report


def _add_member_to_zip(package_path: Path, member: str, text: str) -> None:
    # Read the existing members, then rewrite the zip with the new/updated
    # member alongside the existing ones.
    existing: dict[str, bytes] = {}
    with zipfile.ZipFile(package_path, "r") as zf:
        for name in zf.namelist():
            if name == member:
                continue
            existing[name] = zf.read(name)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, blob in existing.items():
            zf.writestr(name, blob)
        zf.writestr(member, text)


def seed_demo_project(settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
    """Seed (or reuse) the bracket-lightweighting Copilot demo project.

    Behavior:
    - If a demo project of kind ``bracket-lightweighting`` already exists,
      its existing project id is returned without recreating anything,
      unless ``reset=true`` is passed in the payload.
    - With ``reset=true``, all existing demo projects (only those flagged
      as demo) are removed first, then a fresh one is created.
    - Real user projects are never modified, regardless of the reset flag.

    The returned payload includes ``reused`` so the UI can show a more
    informative landing card on subsequent clicks.
    """
    payload = payload or {}
    reset = bool(payload.get("reset", False))

    if reset:
        reset_demo_projects(settings)
        reused = False
        existing: dict[str, Any] | None = None
    else:
        existing_projects = _find_demo_projects(settings)
        existing = existing_projects[0] if existing_projects else None
        reused = existing is not None

    if reused and existing is not None:
        project_id = existing.get("id")
        if not isinstance(project_id, str):
            existing = None  # corrupt metadata — fall through to fresh create
            reused = False

    if not reused or existing is None:
        name = str(payload.get("name") or "Demo · Bracket lightweighting").strip() or "Demo project"
        project = save_project(settings, default_project(name))
        project_id = project["id"]
        package_filename = "demo-bracket.aieng"
        package_path = project_dir(settings, project_id) / package_filename
        _write_demo_package(package_path)
        project["aieng_file"] = package_filename
        project["demo"] = True
        project["demo_copilot_loop"] = True
        project["demo_kind"] = DEMO_KIND
        project["demo_notice"] = (
            "Demo fixture data. Computed values are mock/fixture inputs, "
            "not real simulation results."
        )
        save_project(settings, project)

        rejected_loop = _bake_rejected_loop(project_id, package_path, loop_id="demo-rejected1")
        approved_loop = _bake_approved_loop(project_id, package_path, loop_id="demo-approved1")
        _loop_dir(settings, project_id).mkdir(parents=True, exist_ok=True)
        _bake_report_into_package_and_local(settings, project_id, package_path, rejected_loop)
        _bake_report_into_package_and_local(settings, project_id, package_path, approved_loop)
        _save_loop(settings, project_id, rejected_loop)
        _save_loop(settings, project_id, approved_loop)

        if not _loop_path(settings, project_id, rejected_loop["loop_id"]).exists():
            raise HTTPException(status_code=500, detail="failed to persist rejected demo loop")
        if not _loop_path(settings, project_id, approved_loop["loop_id"]).exists():
            raise HTTPException(status_code=500, detail="failed to persist approved demo loop")
    else:
        # Reuse path — recover the existing demo project's known shape.
        project_id = str(existing.get("id"))
        name = str(existing.get("name") or "Demo · Bracket lightweighting")
        package_filename = str(existing.get("aieng_file") or "demo-bracket.aieng")

    return {
        "schema_version": "0.2",
        "project_id": project_id,
        "project_name": name,
        "package_path": package_filename,
        "demo_kind": DEMO_KIND,
        "reused": reused,
        "loops": [
            {
                "loop_id": "demo-rejected1",
                "decision": "rejected",
                "description": "Rejected back-wall thinning; baseline unchanged.",
            },
            {
                "loop_id": "demo-approved1",
                "decision": "approved",
                "description": "Approved back-wall thinning; downstream evidence marked stale.",
            },
        ],
        "next_action": "Compare the rejected and approved loops to see the decision review chain.",
        "notice": (
            "Demo fixture data. Computed values are mock/fixture inputs, not real "
            "simulation results. A qualified engineer must review the underlying "
            "evidence before any acceptance decision."
        ),
    }


def run_demo_smoke_check(settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
    """Run a deterministic health-check chain against the local demo fixture.

    This verifies that the v0.5 demo flow (seed → list → compare → export)
    works end-to-end on the user's machine without requiring Gmsh,
    CalculiX, or a real solver.

    The check only operates on demo-flagged projects and never mutates real
    user projects. Ordinary chain failures produce ``ok=false`` with structured
    failed checks; they do not raise 500.
    """
    from . import copilot_loop

    payload = payload or {}
    reset = bool(payload.get("reset", False))
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    project_id: str | None = None
    reused = False

    def _check(
        check_id: str,
        label: str,
        passed: bool,
        summary: str,
        details: list[str] | None = None,
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "label": label,
                "status": "passed" if passed else "failed",
                "summary": summary,
                "details": details or [],
            }
        )

    # 1. Seed or reuse demo project
    try:
        seed_result = seed_demo_project(settings, {"reset": reset})
        project_id = seed_result.get("project_id")
        reused = bool(seed_result.get("reused"))
        _check("seed", "Seed or reuse demo project", True, f"Project {project_id} {'reused' if reused else 'created'}.")
    except Exception as exc:  # noqa: BLE001
        _check("seed", "Seed or reuse demo project", False, f"Demo seed failed: {type(exc).__name__}: {exc}")
        return {
            "ok": False,
            "project_id": None,
            "reused": False,
            "checks": checks,
            "export_path": None,
            "warnings": warnings,
            "claim_boundary": "",
        }

    assert isinstance(project_id, str)

    # 2. List loops
    try:
        listing = copilot_loop.list_loops(settings, project_id)
        loops = listing.get("loops") or []
        _check("list_loops", "List demo loops", bool(loops), f"Found {len(loops)} loop(s).")
    except Exception as exc:  # noqa: BLE001
        _check("list_loops", "List demo loops", False, f"List failed: {type(exc).__name__}: {exc}")
        loops = []

    # 3. Identify rejected and approved loops
    rejected_id: str | None = None
    approved_id: str | None = None
    try:
        for entry in loops:
            decision = entry.get("decision")
            lid = entry.get("loop_id")
            if decision == "rejected" and not rejected_id:
                rejected_id = lid
            elif decision == "approved" and not approved_id:
                approved_id = lid
        found_both = rejected_id is not None and approved_id is not None
        _check(
            "identify_decisions",
            "Identify rejected and approved loops",
            found_both,
            f"Rejected={rejected_id}, Approved={approved_id}." if found_both else "Could not find both decisions.",
        )
    except Exception as exc:  # noqa: BLE001
        _check("identify_decisions", "Identify rejected and approved loops", False, f"Error: {type(exc).__name__}: {exc}")

    # 4. Compare reports
    compare_ok = False
    highlights: list[dict[str, Any]] = []
    if rejected_id and approved_id:
        try:
            diff = copilot_loop.compare_reports(settings, project_id, rejected_id, approved_id)
            highlights = diff.get("highlights") or []
            hl_by_id = {h.get("id"): h for h in highlights if isinstance(h, dict)}
            decision_hl = hl_by_id.get("approval_decision")
            decision_changed = (
                decision_hl is not None
                and decision_hl.get("status") == "changed"
            )
            _check(
                "compare_reports",
                "Compare loop reports",
                True,
                f"Diff generated; {len(highlights)} highlight(s)." if highlights else "Diff generated; no highlights.",
            )
            _check(
                "highlight_approval_decision",
                "Highlights include approval decision changed",
                decision_changed,
                "Approval decision marked as changed." if decision_changed else "Missing or incorrect approval_decision highlight.",
            )
            compare_ok = True
        except Exception as exc:  # noqa: BLE001
            _check("compare_reports", "Compare loop reports", False, f"Compare failed: {type(exc).__name__}: {exc}")
            _check("highlight_approval_decision", "Highlights include approval decision changed", False, "Compare step failed.")
    else:
        _check("compare_reports", "Compare loop reports", False, "Missing loop IDs.")
        _check("highlight_approval_decision", "Highlights include approval decision changed", False, "Missing loop IDs.")

    # 5. Export review
    export_path: str | None = None
    export_text = ""
    if rejected_id and approved_id:
        try:
            export_result = copilot_loop.export_review(
                settings,
                project_id,
                {
                    "loop_ids": [rejected_id, approved_id],
                    "include_highlights": True,
                    "include_diff": True,
                    "include_reports": False,
                },
            )
            export_path = export_result.get("export_path")
            export_text = export_result.get("export_text") or ""
            warnings.extend(export_result.get("warnings") or [])
            _check(
                "export_review",
                "Export decision review",
                True,
                f"Export written to {export_path}." if export_path else "Export returned but no path.",
            )
        except Exception as exc:  # noqa: BLE001
            _check("export_review", "Export decision review", False, f"Export failed: {type(exc).__name__}: {exc}")
    else:
        _check("export_review", "Export decision review", False, "Missing loop IDs.")

    # 6. Verify export artifact exists
    artifact_exists = False
    if export_path and project_id:
        try:
            # Check package-internal path first
            package_path = copilot_loop._resolve_package(settings, project_id)
            if package_path.exists():
                with zipfile.ZipFile(package_path, "r") as zf:
                    artifact_exists = export_path in zf.namelist()
            # Fallback to local project dir
            if not artifact_exists:
                local_dir = project_dir(settings, project_id) / "copilot_loop_review"
                local_file = local_dir / Path(export_path).name
                artifact_exists = local_file.exists()
            _check(
                "export_artifact_exists",
                "Export artifact exists",
                artifact_exists,
                f"Artifact found at {export_path}." if artifact_exists else f"Artifact not found at {export_path}.",
            )
        except Exception as exc:  # noqa: BLE001
            _check("export_artifact_exists", "Export artifact exists", False, f"Check failed: {type(exc).__name__}: {exc}")
    else:
        _check("export_artifact_exists", "Export artifact exists", False, "No export path to check.")

    # 7. Claim boundary EN + ZH
    # Isolate the claim-boundary section so the diff/unified section does not
    # create false positives from embedded loop reports.
    _claim_boundary_section = ""
    if export_text:
        boundary_start = export_text.lower().find("## claim boundary")
        if boundary_start != -1:
            next_h2 = export_text.find("## ", boundary_start + 1)
            if next_h2 == -1:
                _claim_boundary_section = export_text[boundary_start:]
            else:
                _claim_boundary_section = export_text[boundary_start:next_h2]
    has_en_boundary = "does not certify" in _claim_boundary_section.lower()
    # The export review and loop reports share the same core claim-boundary phrase.
    has_zh_boundary = "does not certify" in _claim_boundary_section.lower()
    _check(
        "claim_boundary_en",
        "Export contains English claim boundary",
        has_en_boundary,
        "English claim boundary present." if has_en_boundary else "Missing English claim boundary.",
    )
    _check(
        "claim_boundary_zh",
        "Export contains Chinese claim boundary",
        has_zh_boundary,
        "Chinese claim boundary present." if has_zh_boundary else "Missing Chinese claim boundary.",
    )

    # 8. No prohibited certification language
    prohibited = (
        "design is certified",
        "claim accepted",
        "certified safe",
        "engineering claim approved",
    )
    found_prohibited: list[str] = []
    lower_text = export_text.lower()
    for phrase in prohibited:
        if phrase in lower_text:
            found_prohibited.append(phrase)
    _check(
        "no_certification_language",
        "No prohibited certification language",
        not found_prohibited,
        "Clean." if not found_prohibited else f"Found prohibited phrase(s): {', '.join(found_prohibited)}",
    )

    # 9. Optional: verify highlights include critical severity for approval_decision
    decision_hl = next((h for h in highlights if h.get("id") == "approval_decision"), None)
    severity_critical = decision_hl is not None and decision_hl.get("severity") == "critical"
    _check(
        "highlight_critical_severity",
        "Approval decision highlight severity is critical",
        severity_critical,
        "Severity is critical." if severity_critical else "Severity is not critical.",
    )

    all_passed = all(c["status"] == "passed" for c in checks)

    return {
        "ok": all_passed,
        "project_id": project_id,
        "reused": reused,
        "checks": checks,
        "export_path": export_path,
        "warnings": warnings,
        "claim_boundary": copilot_loop._CLAIM_BOUNDARY_EXPORT_NOTE if export_text else "",
    }
