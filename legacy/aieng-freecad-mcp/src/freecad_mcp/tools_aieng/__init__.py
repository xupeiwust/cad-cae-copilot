""".aieng patch bridge MCP tools.

Provides:
- ``aieng_parse_patch`` — read-only validation and planning
- ``aieng_execute_patch`` — guarded execution with optional persistence
"""

from __future__ import annotations

from typing import Any

from freecad_mcp.aieng_bridge.patch import (
    PatchExecutionSummary,
    PatchPlan,
    execute_patch_plan,
    load_patch_proposal,
    parse_patch_proposal,
)
from freecad_mcp.aieng_bridge.claims import (
    ClaimUpdateRequest,
    update_claim_status,
)
from freecad_mcp.aieng_bridge.postprocessing import (
    PostprocessRequest,
    postprocess_results,
)
from freecad_mcp.aieng_bridge.references import (
    build_reference_map,
    load_reference_map,
    mark_references_needing_review,
    write_reference_map,
)
from freecad_mcp.freecad_runtime import detect_freecad_runtime
from freecad_mcp.aieng_bridge.audit import generate_audit_report
from freecad_mcp.aieng_bridge.planner import (
    CapabilityInspectionRequest,
    CapabilityPlanRequest,
    inspect_capabilities,
    plan_capabilities,
)
from freecad_mcp.aieng_bridge.workflow import (
    CadToCaeWorkflowRequest,
    run_cad_to_cae_workflow,
)
from freecad_mcp.aieng_bridge.design_targets import (
    read_design_targets,
    read_design_target_comparisons,
)
from freecad_mcp.aieng_bridge.recommendation import recommend_cad_modifications
from freecad_mcp.aieng_bridge.verification import (
    STRICTNESS_MODES as VERIFY_STRICTNESS_MODES,
    verify_cad_modifications,
)
from freecad_mcp.bridge.executor import FreecadExecutor
from freecad_mcp.cae_core.facade import CAEFacade


def register_aieng_tools(
    mcp: Any,
    executor: FreecadExecutor,
    facade: CAEFacade | None = None,
) -> None:
    """Register .aieng patch bridge tools with the FastMCP server."""

    @mcp.tool()
    async def aieng_parse_patch(
        package_path: str | None = None,
        patch_path: str | None = None,
        patch_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Parse an .aieng patch proposal without executing anything.

        Returns the validated plan, supported operations, unsupported
        operations, and any warnings.
        """
        try:
            raw = load_patch_proposal(package_path, patch_path, patch_json)
            plan = parse_patch_proposal(raw)
            return {
                "status": "success",
                "operation": "aieng_parse_patch",
                "patch_id": plan.patch_id,
                "supported_operations": [op.model_dump(mode="json") for op in plan.operations],
                "unsupported_operations": plan.unsupported_operations,
                "warnings": plan.warnings,
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_parse_patch",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_parse_patch",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_execute_patch(
        package_path: str | None = None,
        patch_path: str | None = None,
        patch_json: dict[str, Any] | None = None,
        persist_to_aieng: bool = False,
        dry_run: bool = False,
        export_modified_step: bool = False,
        export_modified_fcstd: bool = False,
        artifact_output_dir: str | None = None,
        input_fcstd: str | None = None,
    ) -> dict[str, Any]:
        """Execute an .aieng patch proposal with guard checks and optional persistence.

        Steps:
        1. Load and parse the patch proposal.
        2. For each supported operation, resolve parameters and run guards.
        3. Execute (or skip if dry_run) via existing CAD helpers.
        4. Optionally export modified CAD artifacts.
        5. Optionally persist evidence, trace, and run records to .aieng.

        Stops on the first failed/rejected step.
        """
        try:
            raw = load_patch_proposal(package_path, patch_path, patch_json)
            plan = parse_patch_proposal(raw)

            if not plan.operations and plan.unsupported_operations:
                return {
                    "status": "unsupported",
                    "operation": "aieng_execute_patch",
                    "patch_id": plan.patch_id,
                    "steps": [],
                    "unsupported_operations": plan.unsupported_operations,
                    "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
                    "warnings": plan.warnings,
                }

            summary = await execute_patch_plan(
                plan,
                executor,
                package_path=package_path,
                persist_to_aieng=persist_to_aieng,
                dry_run=dry_run,
                export_modified_step=export_modified_step,
                export_modified_fcstd=export_modified_fcstd,
                artifact_output_dir=artifact_output_dir,
                input_fcstd=input_fcstd,
            )
            return summary.model_dump(mode="json")
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_execute_patch",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_execute_patch",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_run_cad_to_cae_workflow(
        package_path: str | None = None,
        patch_path: str | None = None,
        patch_json: dict[str, Any] | None = None,
        persist_to_aieng: bool = False,
        dry_run: bool = False,
        export_modified_fcstd: bool = True,
        export_modified_step: bool = True,
        run_mesh: bool = True,
        export_solver_deck: bool = True,
        run_solver: bool = False,
        import_solver_evidence: bool = True,
        run_postprocess: bool = False,
        export_postprocess_csv: bool = True,
        export_postprocess_vtk: bool = False,
        analysis_type: str = "static_structural",
        stop_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Optional explicit CAD/CAE evidence orchestration helper.

        This tool is an optional orchestration convenience, not a default or
        automatic pipeline. CAD patch execution and CAE operations are
        independent first-class workflows. This tool composes them only when
        explicitly invoked.

        When called, it executes a guarded CAD patch, exports modified artifacts,
        and runs CAE preprocessing (mesh/deck/solver) with full evidence writeback.

        Solver execution is disabled by default. Set run_solver=True only
        when explicit solver evidence is required.

        Post-processing is optional. Set run_postprocess=True to extract
        result metrics and export CSV artifacts.

        This tool does not automatically advance claims.
        """
        if facade is None:
            return {
                "status": "unsupported",
                "operation": "aieng_run_cad_to_cae_workflow",
                "errors": ["CAE facade is not available."],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

        try:
            request = CadToCaeWorkflowRequest(
                package_path=package_path,
                patch_path=patch_path,
                patch_json=patch_json,
                persist_to_aieng=persist_to_aieng,
                dry_run=dry_run,
                export_modified_fcstd=export_modified_fcstd,
                export_modified_step=export_modified_step,
                run_mesh=run_mesh,
                export_solver_deck=export_solver_deck,
                run_solver=run_solver,
                import_solver_evidence=import_solver_evidence,
                run_postprocess=run_postprocess,
                export_postprocess_csv=export_postprocess_csv,
                export_postprocess_vtk=export_postprocess_vtk,
                analysis_type=analysis_type,  # type: ignore[arg-type]
                stop_on_failure=stop_on_failure,
            )
            summary = await run_cad_to_cae_workflow(request, executor, facade)
            return summary.model_dump(mode="json")
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_run_cad_to_cae_workflow",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_run_cad_to_cae_workflow",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    # Alias for clearer naming: optional explicit orchestration helper
    mcp._tool_manager._tools["aieng_orchestrate_cad_cae_sequence"] = mcp._tool_manager._tools["aieng_run_cad_to_cae_workflow"]

    @mcp.tool()
    async def aieng_postprocess_results(
        package_path: str | None = None,
        result_source: str | None = None,
        persist_to_aieng: bool = False,
        export_csv: bool = True,
        export_vtk: bool = False,
        output_dir: str | None = None,
        producer_kind: str = "surrogate",
        analysis_type: str = "static_structural",
    ) -> dict[str, Any]:
        """Post-process CAE results: extract metrics and export artifacts.

        Extracts deterministic result metrics from a CAE result summary and
        optionally exports CSV (and eventually VTK) artifacts.

        Post-processing evidence improves AI readability but does NOT validate
        engineering claims. Surrogate outputs are not solver evidence.
        """
        try:
            request = PostprocessRequest(
                package_path=package_path,
                result_source=result_source,
                persist_to_aieng=persist_to_aieng,
                export_csv=export_csv,
                export_vtk=export_vtk,
                output_dir=output_dir,
                producer_kind=producer_kind,  # type: ignore[arg-type]
                analysis_type=analysis_type,  # type: ignore[arg-type]
            )
            summary = await postprocess_results(request)
            return summary.model_dump(mode="json")
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_postprocess_results",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_postprocess_results",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_update_claim(
        package_path: str,
        claim_id: str,
        evidence_ids: list[str],
        decision_criteria: list[dict[str, Any]] | None = None,
        requested_status: str | None = None,
        mode: str = "evaluate",
        rationale: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Explicitly update a claim status based on evidence and criteria.

        This is the ONLY tool allowed to modify claim_map.json. All other
        tools remain claim-map immutable.

        Evaluate mode: deterministic criteria evaluation against evidence.
        Manual mode: explicit human-reviewed status with required rationale.

        Dry-run evaluates without writing.
        """
        try:
            request = ClaimUpdateRequest(
                package_path=package_path,
                claim_id=claim_id,
                evidence_ids=evidence_ids,
                decision_criteria=decision_criteria or [],
                requested_status=requested_status,  # type: ignore[arg-type]
                mode=mode,  # type: ignore[arg-type]
                rationale=rationale,
                dry_run=dry_run,
            )
            summary = update_claim_status(request)
            return summary.model_dump(mode="json")
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_update_claim",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_update_claim",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_get_reference_map(package_path: str) -> dict[str, Any]:
        """Read-only: get the current reference map for an .aieng package.

        Builds a reference map from available resources if none is persisted,
        but does not write to disk.
        """
        try:
            ref_map = load_reference_map(package_path)
            if ref_map is None:
                ref_map = build_reference_map(package_path)
            return {
                "status": "success",
                "operation": "aieng_get_reference_map",
                "reference_map": ref_map.model_dump(mode="json"),
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_get_reference_map",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_get_reference_map",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_build_reference_map(
        package_path: str,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Build and optionally persist a reference map.

        Writes objects/reference_map.json when persist=True.
        """
        try:
            ref_map = build_reference_map(package_path)
            written_path: str | None = None
            if persist:
                written_path = write_reference_map(package_path, ref_map)
            return {
                "status": "success",
                "operation": "aieng_build_reference_map",
                "reference_map": ref_map.model_dump(mode="json"),
                "written_path": written_path,
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_build_reference_map",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_build_reference_map",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_mark_references_needing_review(
        package_path: str,
        affected_feature_ids: list[str],
        reason: str = "Geometry modified; mapping stability not guaranteed.",
    ) -> dict[str, Any]:
        """Mark references as needing review after geometry changes.

        Updates objects/reference_map.json.
        """
        try:
            ref_map = mark_references_needing_review(package_path, affected_feature_ids, reason)
            return {
                "status": "success",
                "operation": "aieng_mark_references_needing_review",
                "affected_feature_ids": affected_feature_ids,
                "reference_map": ref_map.model_dump(mode="json"),
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_mark_references_needing_review",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_mark_references_needing_review",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_inspect_capabilities(
        desired_outcome: str = "",
        package_path: str | None = None,
        include_runtime_capabilities: bool = True,
        allow_cad_operations: bool = True,
        allow_cae_operations: bool = True,
        allow_claim_update: bool = True,
    ) -> dict[str, Any]:
        """Inspect available capabilities, context, and gaps for a desired outcome.

        This is a read-only inspection tool only. It does not execute operations,
        modify files, or advance claims. Workflow sequencing is decided by the caller.

        It is a planning-neutral capability inspection tool, NOT a workflow
        planner. It exposes possibly relevant tools, missing information,
        unsupported operations, side effects, and policy reminders. The agent
        or caller decides workflow ordering.

        No files are modified. No CAD or CAE operations are executed.
        Claims are never advanced.

        Args:
            desired_outcome: What the agent wants to achieve (e.g., "check max displacement").
            package_path: Optional path to an .aieng package for context.
            include_runtime_capabilities: Whether to detect FreeCAD/FEM/solver availability.
            allow_cad_operations: Whether to include CAD-related tools in results.
            allow_cae_operations: Whether to include CAE-related tools in results.
            allow_claim_update: Whether to include claim-related tools in results.

        Returns:
            CapabilityInspectionSummary with possibly_relevant_tools (unordered),
            missing_information, unsupported_operations, needs_review, and
            policy_reminders.
        """
        try:
            request = CapabilityInspectionRequest(
                desired_outcome=desired_outcome,
                package_path=package_path,
                include_runtime_capabilities=include_runtime_capabilities,
                allow_cad_operations=allow_cad_operations,
                allow_cae_operations=allow_cae_operations,
                allow_claim_update=allow_claim_update,
            )
            summary = inspect_capabilities(request)
            return {
                "status": summary.status,
                "operation": "aieng_inspect_capabilities",
                "inspection": summary.model_dump(mode="json"),
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_inspect_capabilities",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_plan_capabilities(
        desired_outcome: str = "",
        package_path: str | None = None,
        include_runtime_capabilities: bool = True,
        allow_cad_operations: bool = True,
        allow_cae_operations: bool = True,
        allow_claim_update: bool = True,
    ) -> dict[str, Any]:
        """Deprecated alias for aieng_inspect_capabilities.

        Prefer aieng_inspect_capabilities for new integrations. This tool is
        planning-neutral and does not prescribe workflow sequences.
        """
        return await aieng_inspect_capabilities(
            desired_outcome=desired_outcome,
            package_path=package_path,
            include_runtime_capabilities=include_runtime_capabilities,
            allow_cad_operations=allow_cad_operations,
            allow_cae_operations=allow_cae_operations,
            allow_claim_update=allow_claim_update,
        )

    @mcp.tool()
    async def aieng_generate_audit_report(
        package_path: str,
        output_markdown: bool = True,
        output_json: bool = True,
    ) -> dict[str, Any]:
        """Generate an audit report for an .aieng package.

        Summarizes evidence, traces, patch runs, reference map status,
        claim status, and claim discipline. Writes reports to
        ``reports/audit_report.json`` and optionally ``reports/audit_report.md``.

        This tool is read-only except for writing the audit report itself.
        It must not modify claim_map.json, evidence_index.json, or tool_trace.json.
        """
        try:
            result = generate_audit_report(
                package_path=package_path,
                output_markdown=output_markdown,
                output_json=output_json,
            )
            result["operation"] = "aieng_generate_audit_report"
            return result
        except ValueError as exc:
            return {
                "status": "rejected",
                "operation": "aieng_generate_audit_report",
                "errors": [str(exc)],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_generate_audit_report",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def freecad_runtime_capabilities() -> dict[str, Any]:
        """Detect FreeCAD, FEM, meshers, and solver runtime capabilities.

        Returns a structured capability report without modifying any files.
        """
        try:
            caps = detect_freecad_runtime()
            return {
                "status": "success",
                "operation": "freecad_runtime_capabilities",
                "capabilities": caps.model_dump(mode="json"),
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "freecad_runtime_capabilities",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_tool_registry_query(
        category: str | None = None,
        keyword: str | None = None,
        mutability: str | None = None,
    ) -> dict[str, Any]:
        """Query the unified tool transparency registry.

        Returns machine-readable metadata about all MCP tools:
        category, purpose, inputs, side effects, mutability,
        runtime requirements, dry-run support, and claim policy.

        This tool is read-only and never modifies files or claims.
        """
        from freecad_mcp.tool_registry import default_registry

        try:
            registry = default_registry()
            entries = registry.filter(category=category, keyword=keyword, mutability=mutability)
            return {
                "status": "success",
                "operation": "aieng_tool_registry_query",
                "count": len(entries),
                "filters": {
                    "category": category,
                    "keyword": keyword,
                    "mutability": mutability,
                },
                "entries": [e.model_dump(mode="json") for e in entries],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_tool_registry_query",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_read_design_targets(package_path: str) -> dict[str, Any]:
        """Read-only: inspect design targets from an .aieng package.

        Opens the .aieng ZIP package, reads task/design_targets.yaml, and
        returns the target definitions. Does not modify the package, does not
        mutate claim_map.json, and does not invoke any CAD/CAE operation.

        If task/design_targets.yaml is missing, returns has_design_targets=False
        with a warning instead of crashing.
        """
        try:
            result = read_design_targets(package_path)
            return {
                "status": "success" if result.get("ok") else "rejected",
                "operation": "aieng_read_design_targets",
                "package_path": result.get("package_path"),
                "has_design_targets": result.get("has_design_targets", False),
                "target_set_id": result.get("target_set_id"),
                "format_version": result.get("format_version"),
                "targets": result.get("targets", []),
                "claim_policy": result.get("claim_policy", {}),
                "warnings": result.get("warnings", []),
                "errors": [result["error"]] if "error" in result else [],
                "claim_policy_meta": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_read_design_targets",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy_meta": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_read_design_target_comparisons(package_path: str) -> dict[str, Any]:
        """Read-only: inspect design target comparisons from an .aieng package.

        Opens the .aieng ZIP package, reads results/result_summary.json, and
        returns the design_target_comparisons block if present. Does not
        generate comparisons automatically, does not write back, does not
        mutate claim_map.json, and does not invoke any CAD/CAE operation.

        If no comparisons exist, returns has_comparisons=False with a warning.
        """
        try:
            result = read_design_target_comparisons(package_path)
            return {
                "status": "success" if result.get("ok") else "rejected",
                "operation": "aieng_read_design_target_comparisons",
                "package_path": result.get("package_path"),
                "has_comparisons": result.get("has_comparisons", False),
                "design_target_comparisons": result.get("design_target_comparisons"),
                "summary": result.get("summary"),
                "warnings": result.get("warnings", []),
                "errors": [result["error"]] if "error" in result else [],
                "claim_policy_meta": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_read_design_target_comparisons",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy_meta": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }

    @mcp.tool()
    async def aieng_recommend_cad_modifications(package_path: str) -> dict[str, Any]:
        """Read-only: rank CAD modification proposals for a .aieng package.

        Delegates to the `aieng recommend-cad-modifications` CLI. Reads
        task/design_targets.yaml, results/computed_metrics.json,
        results/stress_by_feature.json, and
        simulation/cae_imports/parsed_features.json from the package,
        and returns a structured proposals block ranked by safety margin
        and mass contribution.

        Boundary: proposals are *hypotheses*. The package is not
        modified, no claims are advanced, and no CAD/CAE operations are
        executed. Verification by re-simulation (see
        `aieng_verify_cad_modifications`) is required before any
        proposal is accepted.
        """
        try:
            result = recommend_cad_modifications(package_path)
            payload = result.get("recommendations") or {}
            return {
                "status": "success" if result.get("ok") else "rejected",
                "operation": "aieng_recommend_cad_modifications",
                "package_path": result.get("package_path"),
                "schema_version": payload.get("schema_version"),
                "proposals": payload.get("proposals", []),
                "skipped_features": payload.get("skipped_features", []),
                "evidence": payload.get("evidence", {}),
                "modification_vocabulary": payload.get("modification_vocabulary", []),
                "llm_summary": payload.get("llm_summary"),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
                "exit_code": result.get("exit_code"),
                "claim_policy": result.get("claim_policy", {}),
                "claim_policy_meta": {
                    "claims_advanced": False,
                    "requires_explicit_update_claim": True,
                },
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_recommend_cad_modifications",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy_meta": {
                    "claims_advanced": False,
                    "requires_explicit_update_claim": True,
                },
            }

    @mcp.tool()
    async def aieng_verify_cad_modifications(
        package_path: str,
        strictness: str = "default",
        proposals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read-only: pre-execution verification gate on CAD proposals.

        Delegates to the `aieng verify-cad-modifications` CLI. Runs
        schema, manufacturability, and regression checks on each proposal
        and returns a per-proposal verdict (pass/warn/fail) plus an
        aggregate summary.

        Args:
            package_path: Path to a .aieng package.
            strictness: One of "lenient", "default", or "strict".
                "lenient" downgrades regression predicted-violations to
                warnings; "strict" promotes any warning to a failure.
            proposals: Optional. The JSON payload returned by
                `aieng_recommend_cad_modifications`. If omitted, the CLI
                regenerates proposals from the package.

        Boundary: verification is a pre-execution heuristic check. It
        does not perform geometry-kernel checks (those defer to a future
        Phase 37b in this repo), does not mutate the package, does not
        advance claims, and does not replace re-simulation as the
        authoritative correctness check.
        """
        try:
            result = verify_cad_modifications(
                package_path,
                strictness=strictness,
                proposals=proposals,
            )
            payload = result.get("verification") or {}
            summary = result.get("summary") or {}
            return {
                "status": "success" if result.get("ok") else "rejected",
                "operation": "aieng_verify_cad_modifications",
                "package_path": result.get("package_path"),
                "strictness": result.get("strictness", strictness),
                "schema_version": payload.get("schema_version"),
                "verdicts": payload.get("verdicts", []),
                "summary": summary,
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
                "exit_code": result.get("exit_code"),
                "claim_policy": result.get("claim_policy", {}),
                "claim_policy_meta": {
                    "claims_advanced": False,
                    "requires_explicit_update_claim": True,
                },
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "aieng_verify_cad_modifications",
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy_meta": {
                    "claims_advanced": False,
                    "requires_explicit_update_claim": True,
                },
            }

    @mcp.tool()
    async def preview_operation(
        operation_name: str,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Preview what an operation would do without executing it.

        Returns an OperationPreview containing:
        - would_write_artifacts: path templates for files that would be written
        - would_update_evidence / would_update_traces / would_touch_claims
        - guard_checks_required: which package/feature checks would run
        - unavailable_runtime_blocks: missing runtimes that would block execution
        - expected_duration_estimate and warnings

        This is a true dry-run: no files are written, no CAD operations run,
        no claims are advanced.
        """
        from freecad_mcp.tool_registry import default_registry
        from freecad_mcp.freecad_runtime import detect_freecad_runtime
        from freecad_mcp.contracts.operation_preview import OperationPreview

        try:
            registry = default_registry()
            entry = registry.get(operation_name)
            if entry is None:
                return {
                    "status": "rejected",
                    "operation": "preview_operation",
                    "preview": None,
                    "errors": [f"Unknown operation: {operation_name}"],
                    "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
                }

            inputs = inputs or {}

            # Determine artifact paths from inputs + registry side_effects
            would_write: list[str] = []
            for se in entry.side_effects:
                if "Writes" in se or "writes" in se:
                    # Heuristic: if input contains file_path/run_dir, include it
                    if "file_path" in inputs:
                        would_write.append(inputs["file_path"])
                    elif "run_dir" in inputs:
                        would_write.append(f"{inputs['run_dir']}/*")
                    elif "artifact_output_dir" in inputs:
                        would_write.append(f"{inputs['artifact_output_dir']}/*")
                    elif "output_dir" in inputs:
                        would_write.append(f"{inputs['output_dir']}/*")

            # Deduplicate while preserving order
            seen: set[str] = set()
            would_write = [p for p in would_write if not (p in seen or seen.add(p))]

            # Runtime gap detection
            runtime_blocks: list[str] = []
            if entry.runtime_requirements and "none" not in entry.runtime_requirements:
                caps = detect_freecad_runtime()
                cap_map = {
                    "freecad": caps.freecad_available,
                    "fem": caps.fem_available,
                    "mesher": caps.mesher_available,
                    "solver": caps.solver_available,
                }
                for req in entry.runtime_requirements:
                    if req != "none" and not cap_map.get(req, False):
                        runtime_blocks.append(req)

            # Guard checks
            guard_checks: list[str] = []
            if entry.mutates_cad or entry.mutates_package:
                guard_checks.append("package_context_load")
            if entry.mutates_cad:
                guard_checks.append("feature_graph_existence")
                guard_checks.append("parameter_editability")
            if entry.may_update_claim_map:
                guard_checks.append("claim_id_validity")
                guard_checks.append("evidence_ids_present")

            preview = OperationPreview(
                operation_name=operation_name,
                would_write_artifacts=would_write,
                would_update_evidence=entry.mutates_package and "evidence" in str(entry.side_effects).lower(),
                would_update_traces=entry.mutates_package and "trace" in str(entry.side_effects).lower(),
                would_touch_claims=entry.may_update_claim_map,
                guard_checks_required=guard_checks,
                unavailable_runtime_blocks=runtime_blocks,
                expected_duration_estimate="fast" if not runtime_blocks else "blocked",
                warnings=entry.notes if entry.dry_run_support != "full" else [],
            )

            return {
                "status": "success",
                "operation": "preview_operation",
                "preview": preview.model_dump(mode="json"),
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
        except Exception as exc:
            return {
                "status": "failed",
                "operation": "preview_operation",
                "preview": None,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
            }
