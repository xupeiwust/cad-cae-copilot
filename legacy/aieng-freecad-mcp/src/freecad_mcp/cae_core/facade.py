"""Stable in-process entry point for all CAE operations."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from freecad_mcp.cae_core.schemas import (
    AnalysisSpec,
    BucklingAnalysisSpec,
    BucklingResultSummary,
    CadSpec,
    MassProperties,
    ModalAnalysisSpec,
    ModalResultSummary,
    ResultSummary,
    TaskSpec,
    ThermalAnalysisSpec,
    ThermalResultSummary,
    utc_now_iso,
)
from freecad_mcp.contracts import CADBuildResult, CAEToolset


class CAEFacade:
    """Stable in-process entry point for all CAE operations."""

    def __init__(self, toolset: CAEToolset) -> None:
        self.toolset = toolset

    def setup(
        self,
        run_dir: Path,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        build_result: CADBuildResult,
        stage: str = "cae_setup",
    ) -> dict[str, Any]:
        analysis_spec = self.create_analysis(run_dir, task_spec, cad_spec, stage=stage)
        setup_bundle = self.generate_mesh(run_dir, cad_spec, build_result, analysis_spec, stage=stage)
        return {"analysis_spec": analysis_spec, **setup_bundle}

    def create_analysis(
        self, run_dir: Path, task_spec: TaskSpec, cad_spec: CadSpec, stage: str = "cae_setup"
    ) -> AnalysisSpec:
        return self._invoke(
            run_dir,
            stage,
            "cae_create_analysis",
            lambda: self.toolset.cae_create_analysis(task_spec, cad_spec),
            {
                "document": task_spec.source_document,
                "solver_backend": self.toolset.__class__.__name__,
            },
            _analysis_summary,
        )

    def generate_mesh(
        self,
        run_dir: Path,
        cad_spec: CadSpec,
        build_result: CADBuildResult,
        analysis_spec: AnalysisSpec,
        stage: str = "cae_setup",
    ) -> dict[str, Any]:
        prepared_geometry = self._invoke(
            run_dir,
            stage,
            "cae_prepare_geometry",
            lambda: self.toolset.cae_prepare_geometry(run_dir, cad_spec, build_result, analysis_spec),
            {
                "document_path": build_result.document_path,
                "document": cad_spec.document_name,
            },
            _dict_summary,
        )
        mesh_summary = self._invoke(
            run_dir,
            stage,
            "cae_generate_mesh",
            lambda: self.toolset.cae_generate_mesh(run_dir, cad_spec, analysis_spec),
            {
                "document": cad_spec.document_name,
                "target_size_mm": analysis_spec.mesh.target_size_mm,
            },
            _dict_summary,
        )
        material_assignment = self._invoke(
            run_dir,
            stage,
            "cae_assign_material",
            lambda: self.toolset.cae_assign_material(analysis_spec),
            {"material_name": analysis_spec.material.name},
            _dict_summary,
        )
        boundary_conditions = self._invoke(
            run_dir,
            stage,
            "cae_apply_boundary_conditions",
            lambda: self.toolset.cae_apply_boundary_conditions(analysis_spec),
            {
                "boundary_condition_count": len(analysis_spec.boundary_conditions),
                "load_count": len(analysis_spec.loads),
            },
            _dict_summary,
        )
        return {
            "prepared_geometry": prepared_geometry,
            "mesh_summary": mesh_summary,
            "material_assignment": material_assignment,
            "boundary_conditions": boundary_conditions,
        }

    def solve(
        self,
        run_dir: Path,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
        stage: str = "solve",
    ) -> dict[str, Any]:
        return self.run_static_analysis(
            run_dir, task_spec, cad_spec, analysis_spec, mass_properties, stage=stage
        )

    def run_static_analysis(
        self,
        run_dir: Path,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
        stage: str = "solve",
    ) -> dict[str, Any]:
        return self._invoke(
            run_dir,
            stage,
            "cae_run_static_analysis",
            lambda: self.toolset.cae_run_static_analysis(
                task_spec, cad_spec, analysis_spec, mass_properties
            ),
            {
                "document": cad_spec.document_name,
                "solver_mode": analysis_spec.solver_mode,
                "mass_kg": mass_properties.mass_kg,
            },
            _dict_summary,
        )

    def extract_results(
        self,
        run_dir: Path,
        task_spec: TaskSpec,
        analysis_spec: AnalysisSpec,
        solver_output: dict[str, Any],
        stage: str = "result_check",
    ) -> ResultSummary:
        return self._invoke(
            run_dir,
            stage,
            "cae_extract_results",
            lambda: self.toolset.cae_extract_results(task_spec, analysis_spec, solver_output),
            {
                "solver_mode": analysis_spec.solver_mode,
                "generated_with_real_solver": solver_output.get("generated_with_real_solver"),
            },
            _result_summary_summary,
        )

    def build_report_data(
        self,
        run_dir: Path,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
        result_summary: ResultSummary,
        stage: str = "report",
    ) -> dict[str, Any]:
        return self._invoke(
            run_dir,
            stage,
            "cae_generate_report_data",
            lambda: self.toolset.cae_generate_report_data(
                task_spec, cad_spec, analysis_spec, mass_properties, result_summary
            ),
            {
                "document": cad_spec.document_name,
                "solver_mode": analysis_spec.solver_mode,
            },
            _dict_summary,
        )

    def run_thermal_analysis(
        self,
        run_dir: Path,
        thermal_spec: ThermalAnalysisSpec,
        cad_spec: CadSpec | None = None,
        stage: str = "solve",
    ) -> ThermalResultSummary:
        return self._invoke(
            run_dir,
            stage,
            "cae_run_thermal_analysis",
            lambda: self.toolset.cae_run_thermal_analysis(thermal_spec, cad_spec),
            {"solver_mode": thermal_spec.solver_mode, "analysis_type": thermal_spec.analysis_type},
            _thermal_result_summary,
        )

    def run_modal_analysis(
        self,
        run_dir: Path,
        modal_spec: ModalAnalysisSpec,
        cad_spec: CadSpec | None = None,
        stage: str = "solve",
    ) -> ModalResultSummary:
        return self._invoke(
            run_dir,
            stage,
            "cae_run_modal_analysis",
            lambda: self.toolset.cae_run_modal_analysis(modal_spec, cad_spec),
            {"solver_mode": modal_spec.solver_mode, "num_modes": modal_spec.num_modes},
            _modal_result_summary,
        )

    def run_buckling_analysis(
        self,
        run_dir: Path,
        buckling_spec: BucklingAnalysisSpec,
        cad_spec: CadSpec | None = None,
        stage: str = "solve",
    ) -> BucklingResultSummary:
        return self._invoke(
            run_dir,
            stage,
            "cae_run_buckling_analysis",
            lambda: self.toolset.cae_run_buckling_analysis(buckling_spec, cad_spec),
            {
                "solver_mode": buckling_spec.solver_mode,
                "num_buckling_modes": buckling_spec.num_buckling_modes,
            },
            _buckling_result_summary,
        )

    def _invoke(
        self,
        run_dir: Path,
        stage: str,
        tool_name: str,
        operation: Callable[[], Any],
        request_summary: dict[str, Any],
        response_summary_fn: Callable[[Any], dict[str, Any]],
    ) -> Any:
        started = time.perf_counter()
        try:
            result = operation()
            duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            self._append_trace(
                run_dir,
                {
                    "timestamp": utc_now_iso(),
                    "run_id": run_dir.name,
                    "stage": stage,
                    "tool_name": tool_name,
                    "backend": self.toolset.__class__.__name__,
                    "request_summary": request_summary,
                    "response_summary": response_summary_fn(result),
                    "duration_ms": duration_ms,
                    "success": True,
                    "error": None,
                },
            )
            return result
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            self._append_trace(
                run_dir,
                {
                    "timestamp": utc_now_iso(),
                    "run_id": run_dir.name,
                    "stage": stage,
                    "tool_name": tool_name,
                    "backend": self.toolset.__class__.__name__,
                    "request_summary": request_summary,
                    "response_summary": {},
                    "duration_ms": duration_ms,
                    "success": False,
                    "error": str(exc),
                },
            )
            raise

    def _append_trace(self, run_dir: Path, record: dict[str, Any]) -> None:
        trace_path = run_dir / "cae" / "tool_trace.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


def _analysis_summary(analysis_spec: AnalysisSpec) -> dict[str, Any]:
    return {
        "solver_mode": analysis_spec.solver_mode,
        "solver_mode": analysis_spec.solver_mode,
        "load_count": len(analysis_spec.loads),
        "boundary_condition_count": len(analysis_spec.boundary_conditions),
    }


def _result_summary_summary(result_summary: ResultSummary) -> dict[str, Any]:
    return {
        "success": result_summary.success,
        "solver_mode": result_summary.solver_mode,
        "max_von_mises_stress_mpa": result_summary.max_von_mises_stress_mpa,
        "max_displacement_mm": result_summary.max_displacement_mm,
    }


def _thermal_result_summary(result: ThermalResultSummary) -> dict[str, Any]:
    return {
        "success": result.success,
        "solver_mode": result.solver_mode,
        "max_temperature_c": result.max_temperature_c,
        "min_temperature_c": result.min_temperature_c,
    }


def _modal_result_summary(result: ModalResultSummary) -> dict[str, Any]:
    return {
        "success": result.success,
        "solver_mode": result.solver_mode,
        "num_frequencies": len(result.natural_frequencies_hz),
        "first_frequency_hz": result.natural_frequencies_hz[0] if result.natural_frequencies_hz else None,
    }


def _buckling_result_summary(result: BucklingResultSummary) -> dict[str, Any]:
    return {
        "success": result.success,
        "solver_mode": result.solver_mode,
        "critical_load_factor": result.critical_load_factor,
        "is_stable": result.is_stable,
    }


def _dict_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        for key in (
            "backend",
            "document",
            "analysis_name",
            "solver_name",
            "mesh_name",
            "material_name",
            "boundary_condition_count",
            "load_count",
            "mesh_node_count",
            "mesh_element_count",
            "generated_with_real_solver",
            "max_von_mises_stress_mpa",
            "max_displacement_mm",
        ):
            if key in value:
                summary[key] = value[key]
        if not summary:
            summary["keys"] = sorted(value.keys())
        return summary
    return {"type": type(value).__name__}
