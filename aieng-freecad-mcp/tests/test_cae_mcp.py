"""Tests for the CAE MCP tool layer (surrogate backend, no FreeCAD required)."""

import json
from pathlib import Path
from typing import Any

import pytest

from freecad_mcp.cae_core.schemas import (
    AcceptanceCriteria,
    AnalysisSpec,
    BoundaryCondition,
    CadSpec,
    EnvelopeConstraints,
    LoadCondition,
    LoadSpec,
    MassProperties,
    MaterialSpec,
    MeshSpec,
    ResultSummary,
    TaskSpec,
)
from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.toolset import SurrogateStaticCaeToolset
from freecad_mcp.contracts import CADBuildResult, ToolExecutionError
from freecad_mcp.tools_cae.models import CAE_MCP_SCHEMA_VERSION
from freecad_mcp.tools_cae.server import register_cae_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _task_spec() -> TaskSpec:
    return TaskSpec(
        source_document="task.md",
        description="Bracket task",
        material=MaterialSpec(
            name="Aluminum 6061-T6",
            elastic_modulus_mpa=68900.0,
            poisson_ratio=0.33,
            density_kg_m3=2700.0,
            yield_strength_mpa=276.0,
        ),
        envelope=EnvelopeConstraints(
            max_width_mm=120.0,
            max_height_mm=80.0,
            max_depth_mm=60.0,
        ),
        thickness_mm=8.0,
        mounting={
            "fixed_feature": "mounting_holes",
            "location": "vertical leg",
            "hole_count": 2,
            "hole_diameter_mm": 10.0,
            "hole_spacing_mm": 60.0,
        },
        load_case=LoadSpec(
            location="load hole",
            target_feature="load_hole",
            force_magnitude_n=1500.0,
            force_direction="-Z",
            load_hole_diameter_mm=12.0,
        ),
        acceptance_criteria=AcceptanceCriteria(
            max_von_mises_stress_mpa=150.0,
            max_displacement_mm=1.0,
        ),
    )


def _cad_spec() -> CadSpec:
    return CadSpec.model_validate(
        {
            "document_name": "bracket_basic",
            "build_strategy": "freecad_mcp_partdesign_sequence",
            "parameters": {
                "width_mm": 120.0,
                "vertical_leg_mm": 80.0,
                "horizontal_leg_mm": 60.0,
                "thickness_mm": 8.0,
                "mounting_hole_count": 2,
                "mounting_hole_diameter_mm": 10.0,
                "mounting_hole_spacing_mm": 60.0,
                "load_hole_diameter_mm": 12.0,
                "inner_fillet_radius_mm": 6.0,
            },
        }
    )


def _analysis_spec() -> AnalysisSpec:
    task = _task_spec()
    return AnalysisSpec(
        solver_mode="surrogate_static",
        material=task.material,
        boundary_conditions=[
            BoundaryCondition(
                name="mounting_fixity",
                target="mounting_holes",
                constraint_type="fixed",
            )
        ],
        loads=[
            LoadCondition(
                name="service_force",
                target="load_hole",
                load_type="force",
                magnitude_n=1500.0,
                direction="-Z",
            )
        ],
        mesh=MeshSpec(target_size_mm=4.0, element_type="surrogate", refinement_regions=[]),
        assumptions=["test"],
    )


def _build_result() -> CADBuildResult:
    return CADBuildResult(
        document_path="runs/test/cad/model.FCStd",
        document_is_placeholder=False,
        primary_object_name="PartBody",
        metadata={"backend": "mock"},
    )


class SpyFacade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_analysis(self, run_dir, task_spec, cad_spec, stage="cae_setup"):
        self.calls.append(("create_analysis", stage))
        return _analysis_spec()

    def generate_mesh(self, run_dir, cad_spec, build_result, analysis_spec, stage="cae_setup"):
        self.calls.append(("generate_mesh", stage))
        return {
            "prepared_geometry": {"backend": "spy"},
            "mesh_summary": {"mesh_node_count": 10},
            "material_assignment": {"material_name": "Aluminum 6061-T6"},
            "boundary_conditions": {"boundary_condition_count": 1, "load_count": 1},
        }

    def run_static_analysis(
        self, run_dir, task_spec, cad_spec, analysis_spec, mass_properties, stage="solve"
    ):
        self.calls.append(("run_static_analysis", stage))
        return {
            "backend": "spy",
            "generated_with_real_solver": False,
            "max_von_mises_stress_mpa": 10.0,
            "max_displacement_mm": 0.1,
        }

    def extract_results(self, run_dir, task_spec, analysis_spec, solver_output, stage="result_check"):
        self.calls.append(("extract_results", stage))
        return ResultSummary(
            success=True,
            solver_mode="surrogate_static",
            generated_with_real_solver=False,
            max_von_mises_stress_mpa=10.0,
            max_displacement_mm=0.1,
            factor_of_safety=2.0,
            meets_stress_limit=True,
            meets_displacement_limit=True,
            notes=["spy"],
        )

    def build_report_data(
        self, run_dir, task_spec, cad_spec, analysis_spec, mass_properties, result_summary, stage="report"
    ):
        self.calls.append(("build_report_data", stage))
        return {
            "task": {"source_document": task_spec.source_document},
            "cad": {"document_name": cad_spec.document_name},
            "analysis": {"solver_mode": analysis_spec.solver_mode},
            "mass_properties": {"mass_kg": mass_properties.mass_kg},
            "results": {"success": result_summary.success},
        }


class FailingFacade(SpyFacade):
    def run_static_analysis(
        self, run_dir, task_spec, cad_spec, analysis_spec, mass_properties, stage="solve"
    ):
        raise ToolExecutionError("solver unavailable")


# ---------------------------------------------------------------------------
# Tests: surrogate backend
# ---------------------------------------------------------------------------

class TestSurrogateBackend:
    def test_create_analysis_known_family(self) -> None:
        toolset = SurrogateStaticCaeToolset()
        task = _task_spec()
        cad = _cad_spec()
        analysis = toolset.cae_create_analysis(task, cad)
        assert analysis.solver_mode == "surrogate_static"
        assert analysis.solver_mode == "surrogate_static"
        assert len(analysis.loads) == 1

    def test_run_static_analysis_known_family(self) -> None:
        toolset = SurrogateStaticCaeToolset()
        task = _task_spec()
        cad = _cad_spec()
        analysis = toolset.cae_create_analysis(task, cad)
        mass = MassProperties(volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0])
        result = toolset.cae_run_static_analysis(task, cad, analysis, mass)
        assert result["backend"] == "surrogate_static"
        assert result["generated_with_real_solver"] is False
        assert result["max_von_mises_stress_mpa"] > 0

    def test_run_static_analysis_unknown_family_with_fallback(self) -> None:
        toolset = SurrogateStaticCaeToolset()
        task = _task_spec()
        cad = CadSpec(
            document_name="custom",
            build_strategy="custom",
            parameters={"width_mm": 50.0, "thickness_mm": 5.0, "span_mm": 100.0},
        )
        analysis = toolset.cae_create_analysis(task, cad)
        mass = MassProperties(volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0])
        result = toolset.cae_run_static_analysis(task, cad, analysis, mass)
        assert result["backend"] == "surrogate_static"

    def test_run_static_analysis_unknown_family_no_geometry_params(self) -> None:
        toolset = SurrogateStaticCaeToolset()
        task = _task_spec()
        cad = CadSpec(
            document_name="weird",
            build_strategy="custom",
            parameters={},  # missing all geometry params
        )
        analysis = toolset.cae_create_analysis(task, cad)
        mass = MassProperties(volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0])
        with pytest.raises(ToolExecutionError):
            toolset.cae_run_static_analysis(task, cad, analysis, mass)

    def test_extract_results_pass(self) -> None:
        toolset = SurrogateStaticCaeToolset()
        task = _task_spec()
        analysis = _analysis_spec()
        solver_output = {
            "max_von_mises_stress_mpa": 50.0,
            "max_displacement_mm": 0.5,
            "generated_with_real_solver": False,
        }
        summary = toolset.cae_extract_results(task, analysis, solver_output)
        assert summary.success is True
        assert summary.meets_stress_limit is True
        assert summary.meets_displacement_limit is True


# ---------------------------------------------------------------------------
# Tests: facade tracing
# ---------------------------------------------------------------------------

class TestCAEFacade:
    def test_facade_end_to_end_surrogate(self, tmp_path: Path) -> None:
        toolset = SurrogateStaticCaeToolset()
        facade = CAEFacade(toolset)
        task = _task_spec()
        cad = _cad_spec()
        build = _build_result()

        analysis = facade.create_analysis(tmp_path, task, cad)
        mesh_bundle = facade.generate_mesh(tmp_path, cad, build, analysis)
        mass = MassProperties(volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0])
        solver_out = facade.run_static_analysis(tmp_path, task, cad, analysis, mass)
        summary = facade.extract_results(tmp_path, task, analysis, solver_out)
        report = facade.build_report_data(tmp_path, task, cad, analysis, mass, summary)

        assert analysis.solver_mode == "surrogate_static"
        assert "mesh_summary" in mesh_bundle
        assert solver_out["backend"] == "surrogate_static"
        assert summary.success is True
        assert "results" in report

        trace_file = tmp_path / "cae" / "tool_trace.jsonl"
        assert trace_file.exists()
        lines = trace_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 5


# ---------------------------------------------------------------------------
# Tests: MCP tool registration (mock facade)
# ---------------------------------------------------------------------------

class TestCAEMCPTools:
    @pytest.mark.asyncio
    async def test_cae_create_analysis_tool(self) -> None:
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        # FastMCP stores tools in mcp._tool_manager._tools
        tools = list(mcp._tool_manager._tools.values())
        tool_names = {t.name for t in tools}
        assert tool_names == {
            "aieng_inspect_context",
            "cae_create_analysis",
            "cae_generate_mesh",
            "cae_run_static_analysis",
            "cae_extract_results",
            "cae_generate_report_data",
            "cae_inspect_geometry",
            "cae_run_thermal_analysis",
            "cae_run_modal_analysis",
            "cae_run_buckling_analysis",
        }

    @pytest.mark.asyncio
    async def test_cae_run_static_analysis_backend_error(self) -> None:
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP(name="test")
        facade = FailingFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
        )

        assert response["error"] is True
        assert response["error_code"] == "backend_error"
        assert response["tool_name"] == "cae_run_static_analysis"
        assert response["schema_version"] == CAE_MCP_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Tests: StandardToolResult defaults and claim policy
# ---------------------------------------------------------------------------

class TestStandardToolResult:
    def test_claims_advanced_defaults_to_false(self) -> None:
        from freecad_mcp.tool_contracts import StandardToolResult

        result = StandardToolResult(status="success", operation="test_op")
        assert result.claim_policy.claims_advanced is False

    def test_requires_explicit_update_claim_defaults_to_true(self) -> None:
        from freecad_mcp.tool_contracts import StandardToolResult

        result = StandardToolResult(status="success", operation="test_op")
        assert result.claim_policy.requires_explicit_update_claim is True

    def test_surrogate_result_defaults(self) -> None:
        from freecad_mcp.tool_contracts import StandardToolResult, EvidenceBlock

        result = StandardToolResult(
            status="success",
            operation="cae_run_static_analysis",
            evidence=EvidenceBlock(producer_kind="surrogate"),
        )
        assert result.evidence.producer_kind == "surrogate"
        assert result.trace.producer == "freecad_mcp"
        assert result.trace.exit_status is None
        assert result.artifacts_written == []
        assert result.warnings == []
        assert result.unsupported == []
        assert result.errors == []

    def test_failed_operation_can_still_emit_trace_compatible_result(self) -> None:
        from freecad_mcp.tool_contracts import StandardToolResult

        result = StandardToolResult(
            status="failed",
            operation="cae_run_solver",
            errors=["solver exited with code 1"],
            trace={"tool_trace_id": "trace-123", "producer": "freecad_mcp", "exit_status": 1},
        )
        assert result.status == "failed"
        assert result.trace.exit_status == 1
        assert result.claim_policy.claims_advanced is False


# ---------------------------------------------------------------------------
# Tests: surrogate thermal / modal / buckling discipline
# ---------------------------------------------------------------------------

class TestSurrogateAdvancedAnalyses:
    def test_surrogate_thermal_does_not_imply_solver_execution(self) -> None:
        from freecad_mcp.cae_core.schemas import ThermalAnalysisSpec, ThermalBC, MaterialSpec, MeshSpec
        from freecad_mcp.cae_core.toolset import SurrogateStaticCaeToolset

        toolset = SurrogateStaticCaeToolset()
        thermal_spec = ThermalAnalysisSpec(
            solver_mode="surrogate_thermal",
            material=MaterialSpec(
                name="Aluminum",
                elastic_modulus_mpa=68900.0,
                poisson_ratio=0.33,
                density_kg_m3=2700.0,
                yield_strength_mpa=276.0,
            ),
            thermal_boundary_conditions=[
                ThermalBC(name="base", target="Face1", bc_type="fixed_temperature", temperature_c=20.0)
            ],
            mesh=MeshSpec(target_size_mm=2.0, element_type="surrogate"),
            assumptions=["1D steady-state conduction surrogate."],
        )
        result = toolset.cae_run_thermal_analysis(thermal_spec, cad_spec=None)
        assert result.producer_kind == "surrogate"
        assert result.solver_executed is False
        assert result.mesh_generated is False
        assert result.engineering_validation is False
        assert result.claims_advanced is False
        assert result.generated_with_real_solver is False

    def test_surrogate_modal_does_not_imply_solver_execution(self) -> None:
        from freecad_mcp.cae_core.schemas import ModalAnalysisSpec, BoundaryCondition, MaterialSpec, MeshSpec
        from freecad_mcp.cae_core.toolset import SurrogateStaticCaeToolset

        toolset = SurrogateStaticCaeToolset()
        modal_spec = ModalAnalysisSpec(
            solver_mode="surrogate_modal",
            material=MaterialSpec(
                name="Aluminum",
                elastic_modulus_mpa=68900.0,
                poisson_ratio=0.33,
                density_kg_m3=2700.0,
                yield_strength_mpa=276.0,
            ),
            boundary_conditions=[BoundaryCondition(name="fixed", target="mounting_holes", constraint_type="fixed")],
            mesh=MeshSpec(target_size_mm=2.0, element_type="surrogate"),
            assumptions=["Euler-Bernoulli cantilever surrogate."],
        )
        cad = _cad_spec()
        result = toolset.cae_run_modal_analysis(modal_spec, cad_spec=cad)
        assert result.producer_kind == "surrogate"
        assert result.solver_executed is False
        assert result.mesh_generated is False
        assert result.engineering_validation is False
        assert result.claims_advanced is False

    def test_surrogate_buckling_does_not_imply_solver_execution(self) -> None:
        from freecad_mcp.cae_core.schemas import BucklingAnalysisSpec, BoundaryCondition, LoadCondition, MaterialSpec, MeshSpec
        from freecad_mcp.cae_core.toolset import SurrogateStaticCaeToolset

        toolset = SurrogateStaticCaeToolset()
        buckling_spec = BucklingAnalysisSpec(
            solver_mode="surrogate_buckling",
            material=MaterialSpec(
                name="Aluminum",
                elastic_modulus_mpa=68900.0,
                poisson_ratio=0.33,
                density_kg_m3=2700.0,
                yield_strength_mpa=276.0,
            ),
            boundary_conditions=[BoundaryCondition(name="fixed", target="mounting_holes", constraint_type="fixed")],
            loads=[LoadCondition(name="force", target="load_hole", load_type="force", magnitude_n=1500.0, direction="-Z")],
            mesh=MeshSpec(target_size_mm=2.0, element_type="surrogate"),
            assumptions=["Euler column buckling surrogate."],
        )
        cad = _cad_spec()
        result = toolset.cae_run_buckling_analysis(buckling_spec, cad_spec=cad)
        assert result.producer_kind == "surrogate"
        assert result.solver_executed is False
        assert result.mesh_generated is False
        assert result.engineering_validation is False
        assert result.claims_advanced is False


# ---------------------------------------------------------------------------
# Tests: CAE response models carry standard result fields
# ---------------------------------------------------------------------------

class TestCAEResponseStandardFields:
    def test_create_analysis_response_has_claim_policy(self) -> None:
        from freecad_mcp.tools_cae.models import CaeCreateAnalysisResponse
        from freecad_mcp.cae_core.schemas import AnalysisSpec, BoundaryCondition, LoadCondition, MaterialSpec, MeshSpec

        analysis = AnalysisSpec(
            solver_mode="surrogate_static",
            material=MaterialSpec(name="Al", elastic_modulus_mpa=1.0, poisson_ratio=0.3, density_kg_m3=1.0, yield_strength_mpa=1.0),
            boundary_conditions=[],
            loads=[],
            mesh=MeshSpec(target_size_mm=1.0, element_type="tet4"),
            assumptions=[],
        )
        response = CaeCreateAnalysisResponse(analysis_spec=analysis)
        assert response.claim_policy.claims_advanced is False
        assert response.status == "success"
        assert response.operation == ""

    def test_error_response_has_standard_fields(self) -> None:
        from freecad_mcp.tools_cae.models import CaeErrorResponse

        response = CaeErrorResponse(
            error_code="backend_error",
            tool_name="cae_run_static_analysis",
            message="solver unavailable",
        )
        assert response.status == "failed"
        assert response.claim_policy.claims_advanced is False
        assert response.claim_policy.requires_explicit_update_claim is True
        assert response.evidence.producer_kind is None
        assert response.errors == []

    @pytest.mark.asyncio
    async def test_tool_success_response_does_not_advance_claims(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_create_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
        )

        assert response["status"] == "success"
        assert response["claim_policy"]["claims_advanced"] is False
        assert response["claim_policy"]["requires_explicit_update_claim"] is True
        assert response["evidence"]["producer_kind"] == "surrogate"
        assert response["trace"]["producer"] == "freecad_mcp"
        assert response["schema_version"] == CAE_MCP_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_tool_backend_error_response_is_structured(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        mcp = FastMCP(name="test")
        facade = FailingFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
        )

        assert response["status"] == "failed"
        assert response["error"] is True
        assert response["error_code"] == "backend_error"
        assert response["claim_policy"]["claims_advanced"] is False
        assert response["operation"] == "cae_run_static_analysis"
        assert response["errors"] == ["solver unavailable"]


# ---------------------------------------------------------------------------
# Tests: aieng bridge stubs do not write to disk
# ---------------------------------------------------------------------------

class TestAiengBridgeStubs:
    def test_build_evidence_entry_does_not_write(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge import build_evidence_entry
        from freecad_mcp.tool_contracts import StandardToolResult, EvidenceBlock, ClaimPolicy, TraceBlock

        result = StandardToolResult(
            status="success",
            operation="cae_run_static_analysis",
            evidence=EvidenceBlock(producer_kind="surrogate"),
            claim_policy=ClaimPolicy(),
            trace=TraceBlock(tool_trace_id="trace-1"),
        )
        entry = build_evidence_entry(result, evidence_id="ev-1")
        assert entry["evidence_id"] == "ev-1"
        assert entry["claims_advanced"] is False
        assert entry["producer_kind"] == "surrogate"
        # Ensure no files were written
        assert not list(tmp_path.iterdir())

    def test_build_trace_entry_does_not_write(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge import build_trace_entry
        from freecad_mcp.tool_contracts import StandardToolResult, EvidenceBlock, ClaimPolicy, TraceBlock

        result = StandardToolResult(
            status="success",
            operation="cae_run_static_analysis",
            evidence=EvidenceBlock(producer_kind="surrogate"),
            claim_policy=ClaimPolicy(),
            trace=TraceBlock(tool_trace_id="trace-1", exit_status=0),
        )
        entry = build_trace_entry(result, trace_id="trace-1")
        assert entry["trace_id"] == "trace-1"
        assert entry["exit_status"] == 0
        assert entry["producer"] == "freecad_mcp"
        # Ensure no files were written
        assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# Tests: .aieng context loading
# ---------------------------------------------------------------------------

class TestAiengContext:
    def test_load_none_returns_standalone(self) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context

        ctx = load_aieng_context(None)
        assert ctx.mode == "standalone"
        assert ctx.available is False
        assert any("standalone" in w for w in ctx.warnings)

    def test_load_nonexistent_path_returns_standalone(self) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context

        ctx = load_aieng_context("/does/not/exist")
        assert ctx.mode == "standalone"
        assert ctx.available is False
        assert any("does not exist" in w for w in ctx.warnings)

    def test_load_minimal_directory(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context

        manifest = {"name": "test-package", "version": "0.1.0"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        claim_map = {"claims": []}
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))

        ctx = load_aieng_context(str(tmp_path))
        assert ctx.mode == "aieng_enhanced"
        assert ctx.available is True
        assert ctx.manifest == manifest
        assert ctx.claim_map == claim_map
        assert ctx.task_spec is None
        assert not any("manifest.json not found" in w for w in ctx.warnings)

    def test_missing_optional_resources_are_warnings(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context

        # Only manifest, nothing else
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        ctx = load_aieng_context(str(tmp_path))
        assert ctx.available is True
        assert ctx.task_spec is None
        assert ctx.feature_graph is None
        # Should not crash

    def test_malformed_zipped_aieng_is_handled(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context

        zip_path = tmp_path / "package.aieng"
        zip_path.write_text("fake zip")
        ctx = load_aieng_context(str(zip_path))
        assert ctx.mode == "standalone"
        assert ctx.available is False
        assert any("Malformed" in w for w in ctx.warnings)


# ---------------------------------------------------------------------------
# Tests: operation guards
# ---------------------------------------------------------------------------

class TestOperationGuards:
    def test_standalone_guard_allows_with_warning(self) -> None:
        from freecad_mcp.aieng_bridge.context import AiengPackageContext
        from freecad_mcp.aieng_bridge.guards import check_operation_allowed

        ctx = AiengPackageContext(mode="standalone", available=False)
        guard = check_operation_allowed(ctx, "cae_run_static_analysis")
        assert guard.allowed is True
        assert guard.mode == "standalone"
        assert any("standalone" in r for r in guard.reasons)

    def test_aieng_guard_rejects_unallowed_operation(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context
        from freecad_mcp.aieng_bridge.guards import check_operation_allowed

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "task").mkdir()
        task_spec = {"allowed_operations": ["cae_create_analysis"]}
        import yaml
        (tmp_path / "task" / "task_spec.yaml").write_text(yaml.safe_dump(task_spec))

        ctx = load_aieng_context(str(tmp_path))
        guard = check_operation_allowed(ctx, "cae_run_static_analysis")
        assert guard.allowed is False
        assert "not in task_spec.allowed_operations" in " ".join(guard.reasons)

    def test_aieng_guard_rejects_semantic_only_feature_on_modification(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context
        from freecad_mcp.aieng_bridge.guards import check_operation_allowed

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Hole001": {"editability": {"executable": False}, "semantic_only": True}
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        ctx = load_aieng_context(str(tmp_path))
        # Modification operations are rejected for semantic-only features
        guard = check_operation_allowed(ctx, "cad_set_parameter", target_feature_id="Hole001", is_modification=True)
        assert guard.allowed is False
        assert "semantic-only" in " ".join(guard.reasons).lower() or "not executable" in " ".join(guard.reasons).lower()

    def test_aieng_guard_allows_read_only_on_semantic_only_feature(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context
        from freecad_mcp.aieng_bridge.guards import check_operation_allowed

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        feature_graph = {
            "features": {
                "Hole001": {"editability": {"executable": False}, "semantic_only": True}
            }
        }
        (tmp_path / "graph" / "feature_graph.json").write_text(json.dumps(feature_graph))

        ctx = load_aieng_context(str(tmp_path))
        # Read-only operations are allowed with a warning
        guard = check_operation_allowed(ctx, "cae_run_static_analysis", target_feature_id="Hole001")
        assert guard.allowed is True
        assert any("semantic-only" in w.lower() for w in guard.warnings)

    def test_aieng_guard_rejects_protected_region(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context
        from freecad_mcp.aieng_bridge.guards import check_operation_allowed

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "graph").mkdir()
        constraints = {
            "protected_regions": [
                {"name": "mounting_zone", "features": ["Face1"]}
            ]
        }
        (tmp_path / "graph" / "constraints.json").write_text(json.dumps(constraints))

        ctx = load_aieng_context(str(tmp_path))
        guard = check_operation_allowed(ctx, "cae_run_static_analysis", target_feature_id="Face1")
        assert guard.allowed is False
        assert any("protected" in r.lower() for r in guard.reasons)
        assert guard.protected_region_conflicts

    def test_aieng_guard_allows_valid_operation(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.context import load_aieng_context
        from freecad_mcp.aieng_bridge.guards import check_operation_allowed

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "task").mkdir()
        import yaml
        (tmp_path / "task" / "task_spec.yaml").write_text(yaml.safe_dump({"allowed_operations": ["cae_run_static_analysis"]}))

        ctx = load_aieng_context(str(tmp_path))
        guard = check_operation_allowed(ctx, "cae_run_static_analysis")
        assert guard.allowed is True
        assert guard.mode == "aieng_enhanced"


# ---------------------------------------------------------------------------
# Tests: evidence and trace persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_append_evidence_creates_file(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.persistence import append_evidence_entry

        entry = {"evidence_id": "ev-001", "status": "success", "operation": "test"}
        eid = append_evidence_entry(str(tmp_path), entry)
        assert eid == "ev-001"
        evidence_path = tmp_path / "results" / "evidence_index.json"
        assert evidence_path.exists()
        data = json.loads(evidence_path.read_text())
        assert data["entries"][0]["evidence_id"] == "ev-001"

    def test_append_trace_creates_file(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.persistence import append_trace_entry

        entry = {"trace_id": "trace-001", "status": "success", "operation": "test"}
        tid = append_trace_entry(str(tmp_path), entry)
        assert tid == "trace-001"
        trace_path = tmp_path / "provenance" / "tool_trace.json"
        assert trace_path.exists()
        data = json.loads(trace_path.read_text())
        assert data["entries"][0]["trace_id"] == "trace-001"

    def test_persist_standard_result(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.persistence import persist_standard_result_to_aieng
        from freecad_mcp.tool_contracts import StandardToolResult

        result = StandardToolResult(
            status="success",
            operation="cae_run_static_analysis",
        )
        meta = persist_standard_result_to_aieng(str(tmp_path), result)
        assert meta["claims_advanced"] is False
        assert meta["operation"] == "cae_run_static_analysis"
        assert (tmp_path / "results" / "evidence_index.json").exists()
        assert (tmp_path / "provenance" / "tool_trace.json").exists()

    def test_persistence_does_not_modify_claim_map(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.persistence import persist_standard_result_to_aieng
        from freecad_mcp.tool_contracts import StandardToolResult

        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))

        result = StandardToolResult(status="success", operation="test")
        persist_standard_result_to_aieng(str(tmp_path), result)

        # claim_map must remain unchanged
        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map

    def test_evidence_appends_does_not_overwrite(self, tmp_path: Path) -> None:
        from freecad_mcp.aieng_bridge.persistence import append_evidence_entry

        append_evidence_entry(str(tmp_path), {"status": "success"})
        append_evidence_entry(str(tmp_path), {"status": "success"})
        data = json.loads((tmp_path / "results" / "evidence_index.json").read_text())
        assert len(data["entries"]) == 2


# ---------------------------------------------------------------------------
# Tests: CAE tool integration with optional .aieng
# ---------------------------------------------------------------------------

class TestCAEAiengIntegration:
    @pytest.mark.asyncio
    async def test_cae_run_static_analysis_without_package_path(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
        )
        assert response["status"] == "success"
        assert response["claim_policy"]["claims_advanced"] is False
        assert response.get("persistence") is None

    @pytest.mark.asyncio
    async def test_cae_run_static_analysis_with_persist_no_package_path(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
            persist_to_aieng=True,
        )
        assert response["status"] == "rejected"
        assert "package_path is required" in response.get("message", "")
        assert response["claim_policy"]["claims_advanced"] is False

    @pytest.mark.asyncio
    async def test_cae_run_static_analysis_with_persist_writes_evidence(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        # Set up minimal .aieng package
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )
        assert response["status"] == "success"
        assert response["claim_policy"]["claims_advanced"] is False
        assert response["persistence"] is not None
        assert response["persistence"]["claims_advanced"] is False
        assert (tmp_path / "results" / "evidence_index.json").exists()
        assert (tmp_path / "provenance" / "tool_trace.json").exists()

    @pytest.mark.asyncio
    async def test_cae_persist_failure_returns_error_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools
        import freecad_mcp.tools_cae.server as cae_server_mod
        from freecad_mcp.aieng_bridge.persistence import PersistenceError

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        def failing_persist(*args: Any, **kwargs: Any) -> Any:
            raise PersistenceError("disk full")

        monkeypatch.setattr(cae_server_mod, "persist_standard_result_to_aieng", failing_persist)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )
        assert response["status"] == "success"
        assert response["persistence"]["error_code"] == "PERSISTENCE_FAILED"
        assert response["persistence"]["persisted"] is False
        assert "disk full" in response["persistence"]["error"]

    @pytest.mark.asyncio
    async def test_guard_rejection_prevents_backend_execution(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "task").mkdir()
        import yaml
        (tmp_path / "task" / "task_spec.yaml").write_text(
            yaml.safe_dump({"allowed_operations": ["cae_create_analysis"]})
        )

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
            package_path=str(tmp_path),
            persist_to_aieng=True,
        )
        assert response["status"] == "rejected"
        assert "not in task_spec.allowed_operations" in str(response.get("detail", ""))
        # Backend should not have been called
        assert not any(c[0] == "run_static_analysis" for c in facade.calls)

    @pytest.mark.asyncio
    async def test_aieng_inspect_context_readonly(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "x"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps({"claims": []}))

        mcp = FastMCP(name="test")
        facade = SpyFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["aieng_inspect_context"].fn
        response = await tool(package_path=str(tmp_path))
        assert response["mode"] == "aieng_enhanced"
        assert response["available"] is True
        assert response["resources_found"]["manifest"] is True
        assert response["resources_found"]["claim_map"] is True
        assert response["claim_policy"]["claims_advanced"] is False
        # Must not write anything
        assert not (tmp_path / "results" / "evidence_index.json").exists()


# ---------------------------------------------------------------------------
# Tests: backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_cae_run_static_analysis_backend_error(self) -> None:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.tools_cae.server import register_cae_tools

        mcp = FastMCP(name="test")
        facade = FailingFacade()
        register_cae_tools(mcp, facade)

        tool = mcp._tool_manager._tools["cae_run_static_analysis"].fn
        response = await tool(
            run_dir="runs/test",
            task_spec=_task_spec().model_dump(mode="json"),
            cad_spec=_cad_spec().model_dump(mode="json"),
            analysis_spec=_analysis_spec().model_dump(mode="json"),
            mass_properties=MassProperties(
                volume_mm3=1000.0, mass_kg=0.1, center_of_gravity_mm=[0.0, 0.0, 0.0]
            ).model_dump(mode="json"),
        )

        assert response["error"] is True
        assert response["error_code"] == "backend_error"
        assert response["tool_name"] == "cae_run_static_analysis"
        assert response["schema_version"] == CAE_MCP_SCHEMA_VERSION
