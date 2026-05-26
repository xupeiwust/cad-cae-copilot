"""Optional CAD/CAE evidence orchestration helper.

CAD patch execution and CAE operations are independent first-class workflows.
This module provides an optional explicit orchestration helper that composes
them only when explicitly invoked. It is not a default or automatic pipeline.

When called, it connects the existing CAD patch execution flow to the existing
CAE toolchain, producing a unified evidence trail without automatically
advancing claims.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.patch import (
    PatchExecutionSummary,
    execute_patch_plan,
    load_patch_proposal,
    parse_patch_proposal,
)
from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    persist_standard_result_to_aieng,
)
from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.schemas import (
    AcceptanceCriteria,
    BoundaryCondition,
    LoadCondition,
    LoadSpec,
    MassProperties,
    MaterialSpec,
    MeshSpec,
    MountingSpec,
    TaskSpec,
    CadSpec,
)
from freecad_mcp.contracts import CADBuildResult
from freecad_mcp.aieng_bridge.postprocessing import (
    PostprocessRequest,
    postprocess_results,
)
from freecad_mcp.tool_contracts import ClaimPolicy, EvidenceBlock, StandardToolResult, TraceBlock


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class CadToCaeWorkflowRequest(BaseModel):
    """Request to run the optional CAD/CAE evidence orchestration helper.

    This is an explicit optional composition, not a default pipeline.
    CAD patch execution and CAE operations remain independent workflows.
    """

    model_config = ConfigDict(extra="forbid")

    package_path: str | None = None
    patch_path: str | None = None
    patch_json: dict[str, Any] | None = None
    persist_to_aieng: bool = False
    dry_run: bool = False

    export_modified_fcstd: bool = True
    export_modified_step: bool = True

    run_mesh: bool = True
    export_solver_deck: bool = True
    run_solver: bool = False
    import_solver_evidence: bool = True

    run_postprocess: bool = False
    export_postprocess_csv: bool = True
    export_postprocess_vtk: bool = False

    analysis_type: Literal["static_structural"] = "static_structural"
    stop_on_failure: bool = True


class CaeWorkflowStep(BaseModel):
    """Result of one CAE step in the workflow."""

    model_config = ConfigDict(extra="forbid")

    step_name: str
    status: Literal["success", "failed", "skipped", "unsupported"]
    result: dict[str, Any] | None = None
    warnings: list[str] = []
    errors: list[str] = []
    producer_kind: str = "unknown"


class CadToCaeWorkflowSummary(BaseModel):
    """Summary of a complete CAD-to-CAE workflow execution."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "partial", "failed", "rejected"] = "success"
    mode: Literal["standalone", "aieng_enhanced"] = "standalone"
    patch_summary: PatchExecutionSummary | None = None
    cad_artifacts: list[dict[str, Any]] = []
    cae_steps: list[CaeWorkflowStep] = []
    evidence_ids: list[str] = []
    trace_ids: list[str] = []
    artifacts_written: list[str] = []
    claim_policy: ClaimPolicy = Field(default_factory=ClaimPolicy)
    warnings: list[str] = []
    errors: list[str] = []
    postprocess_summary: dict[str, Any] | None = None
    persistence: dict[str, Any] | None = None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _find_modified_step_artifact(artifacts_written: list[str]) -> str | None:
    for artifact in artifacts_written:
        if artifact.lower().endswith(".step"):
            return artifact
    return None


def _build_default_task_spec(thickness_mm: float = 10.0) -> TaskSpec:
    """Build a conservative static structural task spec for a flat plate."""
    return TaskSpec(
        source_document="modified_bracket",
        description="Static structural analysis of modified bracket base plate",
        material=MaterialSpec(
            name="Aluminum 6061-T6",
            elastic_modulus_mpa=68900.0,
            poisson_ratio=0.33,
            density_kg_m3=2700.0,
            yield_strength_mpa=276.0,
        ),
        thickness_mm=thickness_mm,
        mounting=MountingSpec(
            fixed_feature="mounting_holes",
            location="base",
            hole_count=4,
            hole_diameter_mm=6.0,
            hole_spacing_mm=80.0,
        ),
        load_case=LoadSpec(
            location="center",
            target_feature="load_face",
            force_magnitude_n=500.0,
            force_direction="-Z",
        ),
        acceptance_criteria=AcceptanceCriteria(
            max_von_mises_stress_mpa=200.0,
            max_displacement_mm=2.0,
        ),
    )


def _build_default_cad_spec(thickness_mm: float = 10.0) -> CadSpec:
    """Build a CAD spec matching the surrogate flat-plate heuristic."""
    return CadSpec(
        document_name="ParametricBracket",
        build_strategy="flat_plate",
        parameters={
            "width_mm": 60.0,
            "height_mm": thickness_mm,  # surrogate uses height_mm for flat plate
            "thickness_mm": thickness_mm,
            "mounting_hole_count": 4,
            "mounting_hole_diameter_mm": 6.0,
            "mounting_hole_spacing_mm": 80.0,
            "edge_margin_mm": 10.0,
        },
    )


def _build_default_mass_properties(thickness_mm: float = 10.0) -> MassProperties:
    """Estimate mass properties for a 100x60xthickness mm aluminum plate."""
    volume = 100.0 * 60.0 * thickness_mm  # mm^3
    mass = volume * 1e-9 * 2700.0  # kg
    return MassProperties(
        volume_mm3=volume,
        mass_kg=mass,
        center_of_gravity_mm=[0.0, 0.0, thickness_mm / 2.0],
    )


def _build_cae_metadata(
    workflow_id: str,
    patch_id: str | None,
    analysis_type: str,
    modified_artifact: str | None,
    cae_steps: list[CaeWorkflowStep],
) -> dict[str, Any]:
    """Build evidence metadata for the CAD-to-CAE workflow."""
    metadata: dict[str, Any] = {
        "workflow_id": workflow_id,
        "patch_id": patch_id,
        "analysis_type": analysis_type,
        "modified_artifact": modified_artifact,
        "claims_advanced": False,
        "engineering_validation": False,
    }

    solver_executed = any(
        s.step_name == "solver" and s.status == "success" for s in cae_steps
    )
    mesh_generated = any(
        s.step_name == "mesh" and s.status == "success" for s in cae_steps
    )
    deck_exported = any(
        s.step_name == "deck" and s.status == "success" for s in cae_steps
    )

    metadata["solver_executed"] = solver_executed
    metadata["mesh_generated"] = mesh_generated
    metadata["solver_deck_exported"] = deck_exported

    # Determine overall producer_kind
    producer_kinds = {s.producer_kind for s in cae_steps if s.producer_kind != "unknown"}
    if "freecad_fem" in producer_kinds:
        metadata["producer_kind"] = "freecad_fem"
    elif "surrogate" in producer_kinds:
        metadata["producer_kind"] = "surrogate"
        metadata["warning"] = (
            "Surrogate CAE result is not solver validation evidence."
        )
    else:
        metadata["producer_kind"] = "unknown"

    return metadata


# ------------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------------

async def run_cad_to_cae_workflow(
    request: CadToCaeWorkflowRequest,
    executor: FreecadExecutor,
    facade: CAEFacade,
) -> CadToCaeWorkflowSummary:
    """Run the complete CAD-to-CAE evidence workflow.

    Steps:
    1. Load and parse patch proposal.
    2. Execute patch with artifact export.
    3. Identify modified STEP artifact.
    4. Run CAE preprocessing (mesh/deck/solver) via facade.
    5. Aggregate evidence and optionally persist to .aieng.
    """
    context = load_aieng_context(request.package_path)
    mode: Literal["standalone", "aieng_enhanced"] = context.mode
    workflow_id = f"cad_to_cae_{request.analysis_type}"

    if request.persist_to_aieng and not request.package_path:
        return CadToCaeWorkflowSummary(
            status="rejected",
            mode=mode,
            claim_policy=ClaimPolicy(),
            errors=["persist_to_aieng=true requires a valid package_path."],
        )

    # --- Step 1: Patch execution ---
    raw_patch = load_patch_proposal(
        request.package_path, request.patch_path, request.patch_json
    )
    plan = parse_patch_proposal(raw_patch)

    if not plan.operations and plan.unsupported_operations:
        return CadToCaeWorkflowSummary(
            status="unsupported",
            mode=mode,
            claim_policy=ClaimPolicy(),
            warnings=plan.warnings,
            errors=["No supported operations in patch proposal."],
        )

    patch_summary = await execute_patch_plan(
        plan,
        executor,
        package_path=request.package_path,
        persist_to_aieng=request.persist_to_aieng,
        dry_run=request.dry_run,
        export_modified_step=request.export_modified_step,
        export_modified_fcstd=request.export_modified_fcstd,
    )

    cad_artifacts: list[dict[str, Any]] = []
    for artifact in patch_summary.artifacts_written:
        artifact_path = Path(artifact)
        suffix = artifact_path.suffix.lower()
        artifact_type = "unknown"
        if suffix == ".step":
            artifact_type = "modified_step"
        elif suffix == ".fcstd":
            artifact_type = "modified_fcstd"
        elif suffix == ".json":
            artifact_type = "run_record"
        cad_artifacts.append({
            "path": artifact,
            "artifact_type": artifact_type,
            "source_artifact_preserved": True,
        })

    summary = CadToCaeWorkflowSummary(
        status=patch_summary.status,
        mode=mode,
        patch_summary=patch_summary,
        cad_artifacts=cad_artifacts,
        claim_policy=ClaimPolicy(claims_advanced=False, requires_explicit_update_claim=True),
        warnings=list(patch_summary.warnings),
        errors=list(patch_summary.errors),
    )

    if patch_summary.status in ("rejected", "failed") and request.stop_on_failure:
        summary.errors.append("Patch execution failed; CAE steps skipped.")
        return summary

    # --- Step 2: CAE preprocessing ---
    modified_step = _find_modified_step_artifact(patch_summary.artifacts_written)
    if modified_step is None:
        summary.warnings.append("No modified STEP artifact found; CAE steps skipped.")
        return summary

    # Extract thickness from patch result for CAE inputs
    thickness_mm = 10.0
    if (
        patch_summary.steps
        and patch_summary.steps[0].result
        and "new_value" in patch_summary.steps[0].result
    ):
        try:
            thickness_mm = float(patch_summary.steps[0].result["new_value"])
        except (TypeError, ValueError):
            pass

    task_spec = _build_default_task_spec(thickness_mm)
    cad_spec = _build_default_cad_spec(thickness_mm)
    build_result = CADBuildResult(
        document_path=modified_step,
        document_is_placeholder=True,
        primary_object_name="BasePlate",
    )
    mass_properties = _build_default_mass_properties(thickness_mm)

    cae_steps: list[CaeWorkflowStep] = []

    # Create run_dir for CAE trace
    run_dir = Path(request.package_path) if request.package_path else Path(tempfile.mkdtemp())
    run_dir = run_dir / "cae_runs" / workflow_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if request.run_mesh:
        try:
            setup_bundle = await asyncio.to_thread(
                facade.setup, run_dir, task_spec, cad_spec, build_result
            )
            cae_steps.append(
                CaeWorkflowStep(
                    step_name="mesh",
                    status="success",
                    result={
                        "mesh_summary": setup_bundle.get("mesh_summary", {}),
                        "material": setup_bundle.get("material_assignment", {}),
                        "boundary_conditions": setup_bundle.get("boundary_conditions", {}),
                    },
                    producer_kind=_producer_kind_from_facade(facade),
                )
            )
            if request.export_solver_deck:
                cae_steps.append(
                    CaeWorkflowStep(
                        step_name="deck",
                        status="success",
                        result={"note": "Solver deck prepared alongside mesh generation."},
                        producer_kind=_producer_kind_from_facade(facade),
                    )
                )
        except Exception as exc:
            cae_steps.append(
                CaeWorkflowStep(
                    step_name="mesh",
                    status="failed",
                    errors=[f"{type(exc).__name__}: {exc}"],
                    producer_kind=_producer_kind_from_facade(facade),
                )
            )
            if request.stop_on_failure:
                summary.status = "partial"
                summary.errors.append(f"CAE mesh setup failed: {exc}")
                summary.cae_steps = cae_steps
                _maybe_persist(summary, request)
                return summary

    if request.run_solver:
        try:
            analysis_spec = await asyncio.to_thread(
                facade.create_analysis, run_dir, task_spec, cad_spec
            )
            solver_output = await asyncio.to_thread(
                facade.run_static_analysis,
                run_dir,
                task_spec,
                cad_spec,
                analysis_spec,
                mass_properties,
            )
            cae_steps.append(
                CaeWorkflowStep(
                    step_name="solver",
                    status="success",
                    result=solver_output,
                    producer_kind=_producer_kind_from_facade(facade),
                )
            )

            if request.import_solver_evidence:
                result_summary = await asyncio.to_thread(
                    facade.extract_results,
                    run_dir,
                    task_spec,
                    analysis_spec,
                    solver_output,
                )
                cae_steps.append(
                    CaeWorkflowStep(
                        step_name="results",
                        status="success",
                        result=result_summary.model_dump(mode="json"),
                        producer_kind=_producer_kind_from_facade(facade),
                    )
                )
        except Exception as exc:
            cae_steps.append(
                CaeWorkflowStep(
                    step_name="solver",
                    status="failed",
                    errors=[f"{type(exc).__name__}: {exc}"],
                    producer_kind=_producer_kind_from_facade(facade),
                )
            )
            if request.stop_on_failure:
                summary.status = "partial"
                summary.errors.append(f"CAE solver failed: {exc}")
                summary.cae_steps = cae_steps
                _maybe_persist(summary, request)
                return summary

    summary.cae_steps = cae_steps

    # Determine final status
    cae_failed = any(s.status == "failed" for s in cae_steps)
    if cae_failed and summary.status == "success":
        summary.status = "partial"

    # Collect all artifacts
    for step in cae_steps:
        if step.result and "artifacts" in step.result:
            for artifact in step.result["artifacts"]:
                if isinstance(artifact, str):
                    summary.artifacts_written.append(artifact)

    # --- Step 3: Optional post-processing ---
    if request.run_postprocess:
        await _run_postprocess_step(summary, request, run_dir, facade)

    # Persistence
    _maybe_persist(summary, request, workflow_id, modified_step)
    return summary


async def _run_postprocess_step(
    summary: CadToCaeWorkflowSummary,
    request: CadToCaeWorkflowRequest,
    run_dir: Path,
    facade: CAEFacade,
) -> None:
    """Run post-processing and attach results to the workflow summary."""
    # Build result_source from the last CAE result step if available
    result_source: str | None = None
    for step in reversed(summary.cae_steps):
        if step.step_name == "results" and step.result:
            # Write the result dict to a temp JSON file for post-processing to read
            result_file = run_dir / "cae_result_summary.json"
            try:
                result_file.write_text(json.dumps(step.result), encoding="utf-8")
                result_source = str(result_file)
            except (OSError, TypeError):
                pass
            break

    post_dir = run_dir / "postprocess"
    post_dir.mkdir(parents=True, exist_ok=True)

    pp_request = PostprocessRequest(
        package_path=request.package_path,
        result_source=result_source,
        persist_to_aieng=request.persist_to_aieng,
        export_csv=request.export_postprocess_csv,
        export_vtk=request.export_postprocess_vtk,
        output_dir=str(post_dir),
        producer_kind=_producer_kind_from_facade(facade),
        analysis_type=request.analysis_type,
    )

    try:
        pp_summary = await postprocess_results(pp_request)
        summary.postprocess_summary = pp_summary.model_dump(mode="json")
        for artifact in pp_summary.artifacts_written:
            summary.artifacts_written.append(artifact.path)
        for eid in pp_summary.evidence_ids:
            summary.evidence_ids.append(eid)
        for tid in pp_summary.trace_ids:
            summary.trace_ids.append(tid)
        if pp_summary.status in ("failed", "rejected") and request.stop_on_failure:
            if summary.status == "success":
                summary.status = "partial"
            summary.errors.extend(pp_summary.errors)
    except Exception as exc:
        summary.errors.append(f"Post-processing failed: {exc}")
        if request.stop_on_failure and summary.status == "success":
            summary.status = "partial"


def _producer_kind_from_facade(facade: CAEFacade) -> str:
    """Determine producer_kind from the facade's toolset."""
    name = facade.toolset.__class__.__name__
    if "Surrogate" in name:
        return "surrogate"
    if "Freecad" in name:
        return "freecad_fem"
    return "unknown"


def _maybe_persist(
    summary: CadToCaeWorkflowSummary,
    request: CadToCaeWorkflowRequest,
    workflow_id: str = "cad_to_cae",
    modified_step: str | None = None,
) -> None:
    """Optionally persist workflow evidence and trace to .aieng."""
    if not request.persist_to_aieng or not request.package_path:
        return

    package_path = request.package_path

    metadata = _build_cae_metadata(
        workflow_id,
        summary.patch_summary.patch_id if summary.patch_summary else None,
        request.analysis_type,
        modified_step,
        summary.cae_steps,
    )

    try:
        result = StandardToolResult(
            status=summary.status,
            operation="aieng_run_cad_to_cae_workflow",
            inputs={
                "workflow_id": workflow_id,
                "analysis_type": request.analysis_type,
                "run_solver": request.run_solver,
                "dry_run": request.dry_run,
            },
            outputs={
                "patch_status": summary.patch_summary.status if summary.patch_summary else None,
                "cae_steps": [s.model_dump(mode="json") for s in summary.cae_steps],
            },
            artifacts_written=summary.artifacts_written,
            evidence=EvidenceBlock(producer_kind=metadata.get("producer_kind", "unknown")),
            claim_policy=summary.claim_policy,
            trace=TraceBlock(),
            warnings=summary.warnings,
            errors=summary.errors,
        )
        meta = persist_standard_result_to_aieng(
            package_path, result, additional_metadata=metadata
        )
        summary.persistence = meta
        if "evidence_id" in meta:
            summary.evidence_ids.append(meta["evidence_id"])
        if "trace_id" in meta:
            summary.trace_ids.append(meta["trace_id"])
    except PersistenceError as exc:
        summary.errors.append(f"Workflow persistence failed: {exc}")
