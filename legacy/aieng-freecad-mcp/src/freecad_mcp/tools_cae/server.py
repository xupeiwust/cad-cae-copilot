"""Register CAE tools with the unified FastMCP server."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from freecad_mcp.aieng_bridge.context import load_aieng_context
from freecad_mcp.aieng_bridge.guards import GuardResult, check_operation_allowed
from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    persist_standard_result_to_aieng,
)
from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.toolset import FreecadFemCaeToolset, SurrogateStaticCaeToolset
from freecad_mcp.contracts import ToolExecutionError
from freecad_mcp.tool_contracts import ClaimPolicy, EvidenceBlock, StandardToolResult, TraceBlock
from freecad_mcp.tools_cae.models import (
    CAE_MCP_SCHEMA_VERSION,
    CaeBaseResponse,
    CaeCreateAnalysisRequest,
    CaeCreateAnalysisResponse,
    CaeErrorResponse,
    CaeExtractResultsRequest,
    CaeExtractResultsResponse,
    CaeGenerateMeshRequest,
    CaeGenerateMeshResponse,
    CaeGenerateReportDataRequest,
    CaeGenerateReportDataResponse,
    CaeInspectGeometryRequest,
    CaeInspectGeometryResponse,
    CaeRunBucklingAnalysisRequest,
    CaeRunBucklingAnalysisResponse,
    CaeRunModalAnalysisRequest,
    CaeRunModalAnalysisResponse,
    CaeRunStaticAnalysisRequest,
    CaeRunStaticAnalysisResponse,
    CaeRunThermalAnalysisRequest,
    CaeRunThermalAnalysisResponse,
)


def _producer_kind_from_solver_mode(solver_mode: str | None) -> str:
    if solver_mode is None:
        return "unknown"
    if solver_mode.startswith("surrogate"):
        return "surrogate"
    if solver_mode == "freecad_fem":
        return "freecad_fem"
    if solver_mode == "calculix":
        return "calculix"
    return "unknown"


def _validation_error_response(tool_name: str, exc: ValidationError) -> CaeErrorResponse:
    from freecad_mcp.contracts.failure_mode import FailureDetail, FailureMode
    return CaeErrorResponse(
        status="rejected",
        operation=tool_name,
        error_code="validation_error",
        tool_name=tool_name,
        message="Request validation failed.",
        detail=str(exc),
        claim_policy=ClaimPolicy(),
        failure_mode=FailureDetail(mode=FailureMode.MISSING_INPUT, message=f"Validation error: {exc}"),
        errors=[f"Validation error: {exc}"],
    )


def _backend_error_response(tool_name: str, exc: ToolExecutionError) -> CaeErrorResponse:
    from freecad_mcp.contracts.failure_mode import classify_exception
    failure = classify_exception(exc)
    return CaeErrorResponse(
        status="failed",
        operation=tool_name,
        error_code="backend_error",
        tool_name=tool_name,
        message=str(exc),
        claim_policy=ClaimPolicy(),
        failure_mode=failure,
        errors=[failure.message],
    )


def _internal_error_response(tool_name: str, exc: Exception) -> CaeErrorResponse:
    from freecad_mcp.contracts.failure_mode import classify_exception
    failure = classify_exception(exc)
    return CaeErrorResponse(
        status="failed",
        operation=tool_name,
        error_code="internal_error",
        tool_name=tool_name,
        message=failure.message,
        claim_policy=ClaimPolicy(),
        failure_mode=failure,
        errors=[failure.message],
    )


def _guard_rejected_response(tool_name: str, guard: GuardResult) -> CaeErrorResponse:
    from freecad_mcp.contracts.failure_mode import FailureDetail, FailureMode
    return CaeErrorResponse(
        status="rejected",
        operation=tool_name,
        error_code="validation_error",
        tool_name=tool_name,
        message="Operation rejected by .aieng guard checks.",
        detail="; ".join(guard.reasons) if guard.reasons else None,
        claim_policy=ClaimPolicy(),
        failure_mode=FailureDetail(mode=FailureMode.GUARD_REJECTED, message="; ".join(guard.reasons) if guard.reasons else "Guard rejected"),
        warnings=guard.warnings,
        unsupported=guard.unsupported,
        errors=guard.reasons,
    )


def _maybe_persist(
    package_path: str | None,
    persist_to_aieng: bool,
    response: CaeBaseResponse,
) -> dict[str, Any] | None:
    """Persist a CAE response to .aieng if requested. Returns persistence metadata."""
    if not persist_to_aieng:
        return None
    if not package_path:
        return None
    try:
        result = StandardToolResult(
            status=response.status,
            operation=response.operation,
            inputs=response.inputs,
            outputs=response.outputs,
            artifacts_written=response.artifacts_written,
            evidence=response.evidence,
            claim_policy=response.claim_policy,
            trace=response.trace,
            warnings=response.warnings,
            unsupported=response.unsupported,
            errors=response.errors,
        )
        return persist_standard_result_to_aieng(package_path, result)
    except PersistenceError as exc:
        return {"error": str(exc), "error_code": "PERSISTENCE_FAILED", "persisted": False}


def _apply_persistence(
    response: CaeBaseResponse,
    persist_meta: dict[str, Any] | None,
) -> CaeBaseResponse:
    if persist_meta is not None:
        response.persistence = persist_meta
    return response


def register_cae_tools(mcp: Any, facade: CAEFacade) -> None:
    """Register CAE analysis tools on the FastMCP instance."""

    @mcp.tool()
    async def aieng_inspect_context(
        package_path: str | None = None,
    ) -> dict[str, Any]:
        """Inspect an optional .aieng package and report what resources were found.

        This tool is read-only and never modifies files.
        """
        context = load_aieng_context(package_path)
        return {
            "mode": context.mode,
            "package_path": context.package_path,
            "available": context.available,
            "resources_found": {
                "manifest": context.manifest is not None,
                "task_spec": context.task_spec is not None,
                "external_tool_requirements": context.external_tool_requirements is not None,
                "feature_graph": context.feature_graph is not None,
                "constraints": context.constraints is not None,
                "simulation_setup": context.simulation_setup is not None,
                "claim_map": context.claim_map is not None,
                "evidence_index": context.evidence_index is not None,
                "tool_trace": context.tool_trace is not None,
                "completeness_report": context.completeness_report is not None,
            },
            "warnings": context.warnings,
            "unsupported": context.unsupported,
            "claim_policy": {
                "claims_advanced": False,
                "requires_explicit_update_claim": True,
            },
            "evidence_persistence_possible": context.available and context.mode == "aieng_enhanced",
        }

    @mcp.tool()
    async def cae_create_analysis(
        run_dir: str,
        task_spec: dict[str, Any],
        cad_spec: dict[str, Any],
        stage: str = "cae_setup",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a structured CAE analysis spec for the current task and CAD spec."""
        tool_name = "cae_create_analysis"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeCreateAnalysisRequest(
                run_dir=run_dir,
                task_spec=task_spec,
                cad_spec=cad_spec,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            analysis_spec = await asyncio.to_thread(
                facade.create_analysis,
                Path(request.run_dir),
                request.task_spec,
                request.cad_spec,
                stage=request.stage,
            )
            producer_kind = _producer_kind_from_solver_mode(analysis_spec.solver_mode)
            response: CaeBaseResponse = CaeCreateAnalysisResponse(
                status="success",
                operation=tool_name,
                analysis_spec=analysis_spec,
                evidence=EvidenceBlock(producer_kind=producer_kind),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_generate_mesh(
        run_dir: str,
        cad_spec: dict[str, Any],
        build_result: dict[str, Any],
        analysis_spec: dict[str, Any],
        stage: str = "cae_setup",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Prepare geometry, generate mesh, assign material, and apply boundary conditions."""
        tool_name = "cae_generate_mesh"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeGenerateMeshRequest(
                run_dir=run_dir,
                cad_spec=cad_spec,
                build_result=build_result,
                analysis_spec=analysis_spec,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            result = await asyncio.to_thread(
                facade.generate_mesh,
                Path(request.run_dir),
                request.cad_spec,
                request.build_result,
                request.analysis_spec,
                stage=request.stage,
            )
            producer_kind = _producer_kind_from_solver_mode(request.analysis_spec.solver_mode)
            response = CaeGenerateMeshResponse(
                status="success",
                operation=tool_name,
                prepared_geometry=result["prepared_geometry"],
                mesh_summary=result["mesh_summary"],
                material_assignment=result["material_assignment"],
                boundary_conditions=result["boundary_conditions"],
                evidence=EvidenceBlock(producer_kind=producer_kind),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_run_static_analysis(
        run_dir: str,
        task_spec: dict[str, Any],
        cad_spec: dict[str, Any],
        analysis_spec: dict[str, Any],
        mass_properties: dict[str, Any],
        stage: str = "solve",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the configured static analysis through the CAE facade."""
        tool_name = "cae_run_static_analysis"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeRunStaticAnalysisRequest(
                run_dir=run_dir,
                task_spec=task_spec,
                cad_spec=cad_spec,
                analysis_spec=analysis_spec,
                mass_properties=mass_properties,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            solver_output = await asyncio.to_thread(
                facade.run_static_analysis,
                Path(request.run_dir),
                request.task_spec,
                request.cad_spec,
                request.analysis_spec,
                request.mass_properties,
                stage=request.stage,
            )
            producer_kind = _producer_kind_from_solver_mode(request.analysis_spec.solver_mode)
            response = CaeRunStaticAnalysisResponse(
                status="success",
                operation=tool_name,
                solver_output=solver_output,
                evidence=EvidenceBlock(producer_kind=producer_kind),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_extract_results(
        run_dir: str,
        task_spec: dict[str, Any],
        analysis_spec: dict[str, Any],
        solver_output: dict[str, Any],
        stage: str = "result_check",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Convert solver output into a structured CAE result summary."""
        tool_name = "cae_extract_results"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeExtractResultsRequest(
                run_dir=run_dir,
                task_spec=task_spec,
                analysis_spec=analysis_spec,
                solver_output=solver_output,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            result_summary = await asyncio.to_thread(
                facade.extract_results,
                Path(request.run_dir),
                request.task_spec,
                request.analysis_spec,
                request.solver_output,
                stage=request.stage,
            )
            response = CaeExtractResultsResponse(
                status="success",
                operation=tool_name,
                result_summary=result_summary,
                evidence=EvidenceBlock(producer_kind=result_summary.producer_kind or "unknown"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_generate_report_data(
        run_dir: str,
        task_spec: dict[str, Any],
        cad_spec: dict[str, Any],
        analysis_spec: dict[str, Any],
        mass_properties: dict[str, Any],
        result_summary: dict[str, Any],
        stage: str = "report",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Build the structured CAE report payload for the current run."""
        tool_name = "cae_generate_report_data"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeGenerateReportDataRequest(
                run_dir=run_dir,
                task_spec=task_spec,
                cad_spec=cad_spec,
                analysis_spec=analysis_spec,
                mass_properties=mass_properties,
                result_summary=result_summary,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            report_data = await asyncio.to_thread(
                facade.build_report_data,
                Path(request.run_dir),
                request.task_spec,
                request.cad_spec,
                request.analysis_spec,
                request.mass_properties,
                request.result_summary,
                stage=request.stage,
            )
            producer_kind = _producer_kind_from_solver_mode(request.analysis_spec.solver_mode)
            response = CaeGenerateReportDataResponse(
                status="success",
                operation=tool_name,
                report_data=report_data,
                evidence=EvidenceBlock(producer_kind=producer_kind),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_inspect_geometry(
        document_path: str,
        object_name: str,
        doc_name: str | None = None,
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Inspect a solid's faces and get geometric suggestions for FEM setup.

        Returns face catalog (ID, surface type, normal, area, bbox) plus
        suggested fixed/load references based purely on geometric heuristics.
        """
        tool_name = "cae_inspect_geometry"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeInspectGeometryRequest(
                document_path=document_path,
                object_name=object_name,
                doc_name=doc_name,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            if not isinstance(facade.toolset, FreecadFemCaeToolset):
                response = CaeErrorResponse(
                    status="unsupported",
                    operation=tool_name,
                    error_code="backend_error",
                    tool_name=tool_name,
                    message="inspect_geometry requires the FreeCAD FEM backend.",
                    claim_policy=ClaimPolicy(),
                    unsupported=["inspect_geometry is not available with the surrogate backend."],
                )
            else:
                result = await asyncio.to_thread(
                    facade.toolset.inspect_geometry,
                    request.document_path,
                    request.object_name,
                    request.doc_name,
                )
                response = CaeInspectGeometryResponse(
                    status="success",
                    operation=tool_name,
                    document_path=result.document_path,
                    object_name=result.object_name,
                    global_bbox=result.global_bbox,
                    faces=[f.model_dump(mode="json") for f in result.faces],
                    suggested_fixed=result.suggested_fixed,
                    suggested_load=result.suggested_load,
                    notes=result.notes,
                    evidence=EvidenceBlock(producer_kind="freecad_fem"),
                    claim_policy=ClaimPolicy(),
                    trace=TraceBlock(),
                )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_run_thermal_analysis(
        run_dir: str,
        thermal_spec: dict[str, Any],
        cad_spec: dict[str, Any] | None = None,
        stage: str = "solve",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a steady-state thermal analysis and return temperature and heat-flux results.

        Uses the surrogate backend (1D conduction formula) when no FreeCAD connection is
        available, or the full FreeCAD FEM + CalculiX thermomechanical solver when connected.

        Status: Implemented scaffold (surrogate); Experimental (FreeCAD FEM thermal)
        """
        tool_name = "cae_run_thermal_analysis"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeRunThermalAnalysisRequest(
                run_dir=run_dir,
                thermal_spec=thermal_spec,
                cad_spec=cad_spec,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            result = await asyncio.to_thread(
                facade.run_thermal_analysis,
                Path(request.run_dir),
                request.thermal_spec,
                request.cad_spec,
                stage=request.stage,
            )
            warnings: list[str] = []
            if result.producer_kind == "freecad_fem":
                warnings.append(
                    "FreeCAD FEM thermal analysis is experimental and not yet proven "
                    "by integration tests with a real FreeCAD + CalculiX runtime."
                )
            response = CaeRunThermalAnalysisResponse(
                status="success",
                operation=tool_name,
                result=result,
                evidence=EvidenceBlock(producer_kind=result.producer_kind or "unknown"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                warnings=warnings,
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_run_modal_analysis(
        run_dir: str,
        modal_spec: dict[str, Any],
        cad_spec: dict[str, Any] | None = None,
        stage: str = "solve",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a modal (natural frequency) analysis and return natural frequencies.

        Uses Euler-Bernoulli cantilever beam surrogate without FreeCAD, or CalculiX
        *FREQUENCY step via FreeCAD FEM when connected.

        Status: Implemented scaffold (surrogate); Experimental (FreeCAD FEM modal)
        """
        tool_name = "cae_run_modal_analysis"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeRunModalAnalysisRequest(
                run_dir=run_dir,
                modal_spec=modal_spec,
                cad_spec=cad_spec,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            result = await asyncio.to_thread(
                facade.run_modal_analysis,
                Path(request.run_dir),
                request.modal_spec,
                request.cad_spec,
                stage=request.stage,
            )
            warnings: list[str] = []
            if result.producer_kind == "freecad_fem":
                warnings.append(
                    "FreeCAD FEM modal analysis is experimental and not yet proven "
                    "by integration tests with a real FreeCAD + CalculiX runtime."
                )
            response = CaeRunModalAnalysisResponse(
                status="success",
                operation=tool_name,
                result=result,
                evidence=EvidenceBlock(producer_kind=result.producer_kind or "unknown"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                warnings=warnings,
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")

    @mcp.tool()
    async def cae_run_buckling_analysis(
        run_dir: str,
        buckling_spec: dict[str, Any],
        cad_spec: dict[str, Any] | None = None,
        stage: str = "solve",
        package_path: str | None = None,
        persist_to_aieng: bool = False,
        target_feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a linear buckling analysis and return critical load factors.

        Uses Euler column buckling formula for the surrogate, or CalculiX *BUCKLE step
        via FreeCAD FEM when connected.

        Status: Implemented scaffold (surrogate); Experimental (FreeCAD FEM buckling)
        """
        tool_name = "cae_run_buckling_analysis"
        context = load_aieng_context(package_path)
        guard = check_operation_allowed(context, tool_name, target_feature_id)
        if not guard.allowed:
            response = _guard_rejected_response(tool_name, guard)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        if persist_to_aieng and not package_path:
            response = CaeErrorResponse(
                status="rejected",
                operation=tool_name,
                error_code="validation_error",
                tool_name=tool_name,
                message="package_path is required when persist_to_aieng=true.",
                claim_policy=ClaimPolicy(),
                errors=["persist_to_aieng=true requires a valid package_path."],
            )
            return response.model_dump(mode="json")

        try:
            request = CaeRunBucklingAnalysisRequest(
                run_dir=run_dir,
                buckling_spec=buckling_spec,
                cad_spec=cad_spec,
                stage=stage,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                target_feature_id=target_feature_id,
            )
        except ValidationError as exc:
            response = _validation_error_response(tool_name, exc)
            _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
            return response.model_dump(mode="json")

        try:
            result = await asyncio.to_thread(
                facade.run_buckling_analysis,
                Path(request.run_dir),
                request.buckling_spec,
                request.cad_spec,
                stage=request.stage,
            )
            warnings: list[str] = []
            if result.producer_kind == "freecad_fem":
                warnings.append(
                    "FreeCAD FEM buckling analysis is experimental and not yet proven "
                    "by integration tests with a real FreeCAD + CalculiX runtime."
                )
            response = CaeRunBucklingAnalysisResponse(
                status="success",
                operation=tool_name,
                result=result,
                evidence=EvidenceBlock(producer_kind=result.producer_kind or "unknown"),
                claim_policy=ClaimPolicy(),
                trace=TraceBlock(),
                warnings=warnings,
            )
        except ToolExecutionError as exc:
            response = _backend_error_response(tool_name, exc)
        except Exception as exc:
            response = _internal_error_response(tool_name, exc)

        _apply_persistence(response, _maybe_persist(package_path, persist_to_aieng, response))
        return response.model_dump(mode="json")
