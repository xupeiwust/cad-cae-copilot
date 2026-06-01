"""Shared contracts used by both CAD and CAE modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

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
)


class ToolExecutionError(RuntimeError):
    """Raised when an engineering tool call fails."""


class CADBuildResult(BaseModel):
    """Result of a CAD build operation passed into CAE workflows."""

    model_config = ConfigDict(extra="forbid")

    document_path: str
    document_is_placeholder: bool
    primary_object_name: str
    metadata: dict[str, Any] = {}


class CAEToolset(ABC):
    """Abstract interface for CAE backend implementations."""

    @abstractmethod
    def cae_create_analysis(self, task_spec: TaskSpec, cad_spec: CadSpec) -> AnalysisSpec:
        raise NotImplementedError

    @abstractmethod
    def cae_prepare_geometry(
        self,
        run_dir: Path,
        cad_spec: CadSpec,
        build_result: CADBuildResult,
        analysis_spec: AnalysisSpec,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cae_generate_mesh(
        self, run_dir: Path, cad_spec: CadSpec, analysis_spec: AnalysisSpec
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cae_assign_material(self, analysis_spec: AnalysisSpec) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cae_apply_boundary_conditions(self, analysis_spec: AnalysisSpec) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cae_run_static_analysis(
        self,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cae_extract_results(
        self, task_spec: TaskSpec, analysis_spec: AnalysisSpec, solver_output: dict[str, Any]
    ) -> ResultSummary:
        raise NotImplementedError

    @abstractmethod
    def cae_generate_report_data(
        self,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
        result_summary: ResultSummary,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cae_run_thermal_analysis(
        self,
        thermal_spec: ThermalAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> ThermalResultSummary:
        raise NotImplementedError

    @abstractmethod
    def cae_run_modal_analysis(
        self,
        modal_spec: ModalAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> ModalResultSummary:
        raise NotImplementedError

    @abstractmethod
    def cae_run_buckling_analysis(
        self,
        buckling_spec: BucklingAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> BucklingResultSummary:
        raise NotImplementedError
