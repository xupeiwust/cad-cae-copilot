"""CAE toolset implementations: surrogate and real FreeCAD FEM backends.

Design note: Neither backend depends on ``part_family``. Face selection is
based purely on explicit references or geometric heuristics (bbox, normals).
"""

from __future__ import annotations

import json
import math
import os
import shutil
import textwrap
import xmlrpc.client
from pathlib import Path
from typing import Any

from freecad_mcp.cae_core.schemas import (
    AnalysisSpec,
    BoundaryCondition,
    BracketParameters,
    BucklingAnalysisSpec,
    BucklingResultSummary,
    CadSpec,
    FlatPlateParameters,
    GeometryInspection,
    LoadCondition,
    MassProperties,
    MeshSpec,
    ModalAnalysisSpec,
    ModalResultSummary,
    ResultSummary,
    TaskSpec,
    ThermalAnalysisSpec,
    ThermalResultSummary,
)
from freecad_mcp.contracts import CADBuildResult, CAEToolset, ToolExecutionError

FORCE_DIRECTION_VECTORS: dict[str, tuple[int, int, int]] = {
    "+X": (1, 0, 0),
    "-X": (-1, 0, 0),
    "+Y": (0, 1, 0),
    "-Y": (0, -1, 0),
    "+Z": (0, 0, 1),
    "-Z": (0, 0, -1),
}


def _param(params: dict[str, Any], key: str, default: Any = None) -> Any:
    return params.get(key, default)


# ---------------------------------------------------------------------------
# Surrogate backend
# ---------------------------------------------------------------------------

class SurrogateStaticCaeToolset(CAEToolset):
    """Deterministic CAE surrogate using analytical beam formulas.

    Detects geometry type from parameter keys instead of ``part_family``:
    - ``height_mm`` present → flat plate formula
    - ``vertical_leg_mm`` present → L-bracket formula
    - neither → generic beam surrogate (requires ``span_mm``)
    """

    def cae_create_analysis(self, task_spec: TaskSpec, cad_spec: CadSpec) -> AnalysisSpec:
        params = cad_spec.parameters
        thickness = float(_param(params, "thickness_mm", 5.0))
        target_size = max(round(min(thickness / 2.0, 5.0), 3), 1.0)
        return AnalysisSpec(
            solver_mode="surrogate_static",
            material=task_spec.material,
            boundary_conditions=[
                BoundaryCondition(
                    name="mounting_fixity",
                    target=task_spec.mounting.fixed_feature,
                    constraint_type="fixed",
                )
            ],
            loads=[
                LoadCondition(
                    name="service_force",
                    target=task_spec.load_case.target_feature,
                    load_type="force",
                    magnitude_n=task_spec.load_case.force_magnitude_n,
                    direction=task_spec.load_case.force_direction,
                )
            ],
            mesh=MeshSpec(
                target_size_mm=target_size,
                element_type="surrogate_region",
                refinement_regions=["mounting_holes", "load_application"],
            ),
            assumptions=[
                "Linear elastic behavior.",
                "Small displacement static response.",
                "Deterministic surrogate model based on analytical beam theory.",
            ],
        )

    def cae_prepare_geometry(
        self,
        run_dir: Path,
        cad_spec: CadSpec,
        build_result: object,
        analysis_spec: AnalysisSpec,
    ) -> dict[str, object]:
        prepared_path = run_dir / "cae" / "prepared_geometry.json"
        prepared_path.parent.mkdir(parents=True, exist_ok=True)
        prepared = {
            "backend": "surrogate_static",
            "source_document": build_result.document_path,
            "document_is_placeholder": build_result.document_is_placeholder,
        }
        prepared_path.write_text(json.dumps(prepared, indent=2), encoding="utf-8")
        return prepared

    def cae_generate_mesh(
        self, run_dir: Path, cad_spec: CadSpec, analysis_spec: AnalysisSpec
    ) -> dict[str, object]:
        params = cad_spec.parameters
        thickness = float(_param(params, "thickness_mm", 5.0))
        width = float(_param(params, "width_mm", 50.0))
        height = float(_param(params, "height_mm", _param(params, "vertical_leg_mm", 50.0)))
        span_measure = width * height
        approx_nodes = int(
            max(50, span_measure / max(analysis_spec.mesh.target_size_mm**2, 1.0))
        )
        return {
            "backend": "surrogate_static",
            "target_size_mm": analysis_spec.mesh.target_size_mm,
            "approx_node_count": approx_nodes,
            "approx_element_count": int(approx_nodes * 1.6),
        }

    def cae_assign_material(self, analysis_spec: AnalysisSpec) -> dict[str, object]:
        return {
            "material_name": analysis_spec.material.name,
            "elastic_modulus_mpa": analysis_spec.material.elastic_modulus_mpa,
            "poisson_ratio": analysis_spec.material.poisson_ratio,
        }

    def cae_apply_boundary_conditions(
        self, analysis_spec: AnalysisSpec
    ) -> dict[str, object]:
        return {
            "boundary_condition_count": len(analysis_spec.boundary_conditions),
            "load_count": len(analysis_spec.loads),
        }

    def cae_run_static_analysis(
        self,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
    ) -> dict[str, object]:
        params = cad_spec.parameters
        force_n = task_spec.load_case.force_magnitude_n
        elastic_modulus_pa = task_spec.material.elastic_modulus_mpa * 1_000_000.0

        # Auto-detect geometry type from parameter keys
        try:
            if "height_mm" in params:
                fp = FlatPlateParameters.model_validate(params)
                width_m = fp.width_mm / 1000.0
                thickness_m = fp.thickness_mm / 1000.0
                span_m = fp.height_mm / 1000.0
                stress_concentration_factor = 1.4
            elif "vertical_leg_mm" in params:
                bp = BracketParameters.model_validate(params)
                width_m = bp.width_mm / 1000.0
                thickness_m = bp.thickness_mm / 1000.0
                span_m = bp.horizontal_leg_mm / 1000.0
                inertia_m4 = width_m * thickness_m**3 / 12.0
                stress_concentration_factor = 1.8
            else:
                raise ValueError("no_known_shape")
        except Exception:
            # Fallback generic beam surrogate
            width_mm = _param(params, "width_mm")
            thickness_mm = _param(params, "thickness_mm")
            span_mm = _param(params, "span_mm") or _param(params, "length_mm")
            if width_mm is None or thickness_mm is None or span_mm is None:
                raise ToolExecutionError(
                    "Surrogate backend requires 'width_mm', 'thickness_mm', and 'span_mm' (or 'length_mm') "
                    "for generic beam geometries."
                )
            width_m = float(width_mm) / 1000.0
            thickness_m = float(thickness_mm) / 1000.0
            span_m = float(span_mm) / 1000.0
            if span_m <= 0 or width_m <= 0 or thickness_m <= 0:
                raise ToolExecutionError("Surrogate geometry parameters must be positive.")
            inertia_m4 = width_m * thickness_m**3 / 12.0
            stress_concentration_factor = 1.5

        moment_nm = force_n * span_m
        extreme_fiber_m = thickness_m / 2.0
        nominal_stress_pa = moment_nm * extreme_fiber_m / inertia_m4
        max_stress_mpa = nominal_stress_pa * stress_concentration_factor / 1_000_000.0
        displacement_m = force_n * span_m**3 / (3.0 * elastic_modulus_pa * inertia_m4)
        max_displacement_mm = displacement_m * 1000.0
        return {
            "backend": "surrogate_static",
            "generated_with_real_solver": False,
            "max_von_mises_stress_mpa": round(max_stress_mpa, 3),
            "max_displacement_mm": round(max_displacement_mm, 6),
            "reaction_force_n": round(force_n, 3),
            "estimated_mass_kg": mass_properties.mass_kg,
            "assumptions": analysis_spec.assumptions,
        }

    def cae_extract_results(
        self,
        task_spec: TaskSpec,
        analysis_spec: AnalysisSpec,
        solver_output: dict[str, object],
    ) -> ResultSummary:
        max_stress = float(solver_output["max_von_mises_stress_mpa"])
        max_displacement = float(solver_output["max_displacement_mm"])
        stress_limit = task_spec.acceptance_criteria.max_von_mises_stress_mpa
        displacement_limit = task_spec.acceptance_criteria.max_displacement_mm
        fos = task_spec.material.yield_strength_mpa / max(max_stress, 1e-6)
        return ResultSummary(
            success=max_stress <= stress_limit and max_displacement <= displacement_limit,
            solver_mode=analysis_spec.solver_mode,
            generated_with_real_solver=bool(solver_output["generated_with_real_solver"]),
            producer_kind="surrogate",
            solver_executed=False,
            mesh_generated=False,
            engineering_validation=False,
            claims_advanced=False,
            max_von_mises_stress_mpa=max_stress,
            max_displacement_mm=max_displacement,
            factor_of_safety=round(fos, 3),
            meets_stress_limit=max_stress <= stress_limit,
            meets_displacement_limit=max_displacement <= displacement_limit,
            notes=[
                "Results come from a deterministic surrogate, not a full mesh solve.",
                "Swap in a CalculiX or FreeCAD FEM adapter without changing workflow stages.",
            ],
        )

    def cae_generate_report_data(
        self,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
        result_summary: ResultSummary,
    ) -> dict[str, object]:
        return {
            "task": task_spec.model_dump(mode="json"),
            "cad": cad_spec.model_dump(mode="json"),
            "analysis": analysis_spec.model_dump(mode="json"),
            "mass_properties": mass_properties.model_dump(mode="json"),
            "results": result_summary.model_dump(mode="json"),
        }

    def cae_run_thermal_analysis(
        self,
        thermal_spec: ThermalAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> ThermalResultSummary:
        params = cad_spec.parameters if cad_spec else {}
        width_m = float(_param(params, "width_mm", 50.0)) / 1000.0
        thickness_m = float(_param(params, "thickness_mm", 5.0)) / 1000.0
        span_m = float(_param(params, "height_mm", _param(params, "vertical_leg_mm", 50.0))) / 1000.0
        cross_section_m2 = max(width_m * thickness_m, 1e-9)
        k = thermal_spec.thermal_conductivity_w_mk

        fixed_temp_bcs = [
            bc for bc in thermal_spec.thermal_boundary_conditions
            if bc.bc_type == "fixed_temperature" and bc.temperature_c is not None
        ]
        base_temp_c = fixed_temp_bcs[0].temperature_c if fixed_temp_bcs else 20.0

        total_q_w = sum(
            (hs.total_heat_w or 0.0) + (hs.heat_flux_w_m2 or 0.0) * cross_section_m2
            for hs in thermal_spec.heat_sources
        )
        for bc in thermal_spec.thermal_boundary_conditions:
            if bc.bc_type == "heat_flux" and bc.heat_flux_w_m2:
                total_q_w += bc.heat_flux_w_m2 * cross_section_m2

        if total_q_w <= 0:
            return ThermalResultSummary(
                success=True,
                solver_mode=thermal_spec.solver_mode,
                generated_with_real_solver=False,
                producer_kind="surrogate",
                solver_executed=False,
                mesh_generated=False,
                engineering_validation=False,
                claims_advanced=False,
                max_temperature_c=round(base_temp_c, 2),
                min_temperature_c=round(base_temp_c, 2),
                max_heat_flux_w_m2=0.0,
                temperature_limit_c=None,
                meets_temperature_limit=True,
                notes=["No heat input detected; isothermal surrogate result."],
            )

        r_thermal = span_m / (k * cross_section_m2)
        delta_t = total_q_w * r_thermal
        max_temp = base_temp_c + delta_t
        max_flux = total_q_w / cross_section_m2
        return ThermalResultSummary(
            success=True,
            solver_mode=thermal_spec.solver_mode,
            generated_with_real_solver=False,
            producer_kind="surrogate",
            solver_executed=False,
            mesh_generated=False,
            engineering_validation=False,
            claims_advanced=False,
            max_temperature_c=round(max_temp, 2),
            min_temperature_c=round(base_temp_c, 2),
            max_heat_flux_w_m2=round(max_flux, 3),
            temperature_limit_c=None,
            meets_temperature_limit=True,
            notes=[
                "Thermal result from 1D steady-state conduction surrogate.",
                f"Thermal conductivity: {k} W/m·K.",
                f"ΔT = {round(delta_t, 2)} °C from {round(base_temp_c, 2)} °C base.",
            ],
        )

    def cae_run_modal_analysis(
        self,
        modal_spec: ModalAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> ModalResultSummary:
        params = cad_spec.parameters if cad_spec else {}
        width_m = float(_param(params, "width_mm", 50.0)) / 1000.0
        thickness_m = float(_param(params, "thickness_mm", 5.0)) / 1000.0
        span_m = float(_param(params, "height_mm", _param(params, "vertical_leg_mm", 50.0))) / 1000.0
        span_m = max(span_m, 1e-6)

        E = modal_spec.material.elastic_modulus_mpa * 1e6
        rho = modal_spec.material.density_kg_m3
        A = max(width_m * thickness_m, 1e-12)
        I = max(width_m * thickness_m**3 / 12.0, 1e-18)
        L = span_m

        # Cantilever (fixed-free) eigenvalue coefficients for first 5 bending modes
        lambdas = [1.8751, 4.6941, 7.8548, 10.9956, 14.1372]
        n_modes = min(modal_spec.num_modes, len(lambdas))
        frequencies = []
        for lam in lambdas[:n_modes]:
            f = (lam**2 / (2.0 * math.pi)) * math.sqrt(E * I / (rho * A * L**4))
            if modal_spec.mass_scaling != 1.0:
                f /= math.sqrt(max(modal_spec.mass_scaling, 1e-9))
            frequencies.append(round(f, 3))

        if modal_spec.freq_range_hz:
            lo, hi = modal_spec.freq_range_hz[0], modal_spec.freq_range_hz[1]
            frequencies = [f for f in frequencies if lo <= f <= hi]

        return ModalResultSummary(
            success=True,
            solver_mode=modal_spec.solver_mode,
            generated_with_real_solver=False,
            producer_kind="surrogate",
            solver_executed=False,
            mesh_generated=False,
            engineering_validation=False,
            claims_advanced=False,
            natural_frequencies_hz=frequencies,
            mode_shapes_available=False,
            notes=[
                "Natural frequencies from Euler-Bernoulli cantilever beam surrogate.",
                f"First mode: {frequencies[0]:.3f} Hz." if frequencies else "No modes in range.",
                "Assumed cantilever (fixed-free) boundary condition.",
            ],
        )

    def cae_run_buckling_analysis(
        self,
        buckling_spec: BucklingAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> BucklingResultSummary:
        params = cad_spec.parameters if cad_spec else {}
        width_m = float(_param(params, "width_mm", 50.0)) / 1000.0
        thickness_m = float(_param(params, "thickness_mm", 5.0)) / 1000.0
        span_m = float(_param(params, "height_mm", _param(params, "vertical_leg_mm", 50.0))) / 1000.0
        span_m = max(span_m, 1e-6)

        E = buckling_spec.material.elastic_modulus_mpa * 1e6
        I = max(width_m * thickness_m**3 / 12.0, 1e-18)

        # Fixed-free column: P_cr = π²EI / (2L)²
        K = 2.0
        p_cr = math.pi**2 * E * I / (K * span_m)**2

        total_applied_n = sum(load.magnitude_n for load in buckling_spec.loads)
        if total_applied_n <= 0:
            clf = 0.0
            stable = False
            all_factors = [0.0] * buckling_spec.num_buckling_modes
        else:
            clf = p_cr / total_applied_n
            stable = clf > 1.0
            n_modes = min(buckling_spec.num_buckling_modes, 5)
            # Higher Euler modes scale as n²
            all_factors = [round(clf * n**2, 4) for n in range(1, n_modes + 1)]

        return BucklingResultSummary(
            success=True,
            solver_mode=buckling_spec.solver_mode,
            generated_with_real_solver=False,
            producer_kind="surrogate",
            solver_executed=False,
            mesh_generated=False,
            engineering_validation=False,
            claims_advanced=False,
            critical_load_factor=round(clf, 4),
            all_load_factors=all_factors,
            is_stable=stable,
            mode_shapes_available=False,
            notes=[
                "Buckling load factors from Euler fixed-free column formula.",
                f"Critical load: {round(p_cr, 1)} N vs applied {round(total_applied_n, 1)} N.",
                f"Critical load factor (mode 1): {round(clf, 3)}.",
                "Assumes uniform cross-section and linear elastic material.",
            ],
        )


# ---------------------------------------------------------------------------
# Real FreeCAD FEM backend
# ---------------------------------------------------------------------------

class FreecadFemCaeToolset(CAEToolset):
    """Thin CAE adapter over FreeCAD FEM + Gmsh + CalculiX via XML-RPC.

    Face selection is purely geometric (bbox + surface type) or explicit.
    No ``part_family`` dependency.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9875,
        timeout_seconds: float = 120.0,
        ccx_binary: str | None = None,
        gmsh_binary: str | None = None,
    ) -> None:
        transport = xmlrpc.client.Transport()
        transport.timeout = timeout_seconds
        self._proxy = xmlrpc.client.ServerProxy(
            f"http://{host}:{port}",
            allow_none=True,
            transport=transport,
        )
        self._ccx_binary = ccx_binary or os.environ.get("MECH_AGENT_CCX_BINARY")
        self._gmsh_binary = gmsh_binary or os.environ.get("MECH_AGENT_GMSH_BINARY")
        self._session: dict[str, Any] = {}

    def cae_create_analysis(
        self, task_spec: TaskSpec, cad_spec: CadSpec
    ) -> AnalysisSpec:
        params = cad_spec.parameters
        thickness = float(_param(params, "thickness_mm", 5.0))
        target_size = max(round(min(thickness * 0.75, 6.0), 3), 2.0)
        return AnalysisSpec(
            solver_mode="freecad_fem",
            material=task_spec.material,
            boundary_conditions=[
                BoundaryCondition(
                    name="mounting_fixity",
                    target=task_spec.mounting.fixed_feature,
                    constraint_type="fixed",
                )
            ],
            loads=[
                LoadCondition(
                    name="service_force",
                    target=task_spec.load_case.target_feature,
                    load_type="force",
                    magnitude_n=task_spec.load_case.force_magnitude_n,
                    direction=task_spec.load_case.force_direction,
                )
            ],
            mesh=MeshSpec(
                target_size_mm=target_size,
                element_type="freecad_gmsh_tet4",
                refinement_regions=["mounting_support", "load_application"],
            ),
            assumptions=[
                "Linear elastic static structural analysis in FreeCAD FEM.",
                "Single-part solid meshed with Gmsh and solved with CalculiX.",
                "Reference features selected by geometric heuristics or explicit agent input.",
            ],
        )

    def cae_prepare_geometry(
        self,
        run_dir: Path,
        cad_spec: CadSpec,
        build_result: CADBuildResult,
        analysis_spec: AnalysisSpec,
    ) -> dict[str, Any]:
        if build_result.document_is_placeholder:
            raise ToolExecutionError(
                "The freecad_fem backend requires a real FreeCAD CAD document, not a placeholder."
            )

        explicit_fixed = _param(cad_spec.parameters, "fixed_references")
        explicit_load = _param(cad_spec.parameters, "load_references")

        payload = {
            "doc_name": cad_spec.document_name,
            "document_path": build_result.document_path,
            "object_name": build_result.primary_object_name,
            "fixed_target": analysis_spec.boundary_conditions[0].target,
            "load_target": analysis_spec.loads[0].target,
            "thickness_mm": float(_param(cad_spec.parameters, "thickness_mm", 5.0)),
            "working_dir": str((run_dir / "cae" / "solver").resolve()),
            "explicit_fixed_references": explicit_fixed,
            "explicit_load_references": explicit_load,
        }
        response = self._execute(self._code_prepare_geometry(payload))
        prepared = response["result"]
        prepared["bridge_stdout"] = response.get("stdout", "")
        prepared["bridge_stderr"] = response.get("stderr", "")
        self._session = {
            "run_dir": run_dir,
            "doc_name": prepared["doc_name"],
            "document_path": prepared["document_path"],
            "object_name": prepared["object_name"],
            "prepared_geometry": prepared,
        }
        return prepared

    def cae_generate_mesh(
        self, run_dir: Path, cad_spec: CadSpec, analysis_spec: AnalysisSpec
    ) -> dict[str, Any]:
        prepared = self._require_session_value("prepared_geometry")
        payload = {
            "doc_name": self._session["doc_name"],
            "document_path": self._session["document_path"],
            "object_name": self._session["object_name"],
            "working_dir": prepared["working_dir"],
            "mesh_size_mm": analysis_spec.mesh.target_size_mm,
            "ccx_binary": self._ccx_binary,
            "gmsh_binary": self._gmsh_binary,
        }
        response = self._execute(self._code_generate_mesh(payload))
        mesh_summary = response["result"]
        mesh_summary["bridge_stdout"] = response.get("stdout", "")
        mesh_summary["bridge_stderr"] = response.get("stderr", "")
        self._session.update(
            {
                "analysis_name": mesh_summary["analysis_name"],
                "solver_name": mesh_summary["solver_name"],
                "mesh_name": mesh_summary["mesh_name"],
                "working_dir": mesh_summary["working_dir"],
            }
        )
        return mesh_summary

    def cae_assign_material(self, analysis_spec: AnalysisSpec) -> dict[str, Any]:
        payload = {
            "doc_name": self._require_session_value("doc_name"),
            "document_path": self._require_session_value("document_path"),
            "analysis_name": self._require_session_value("analysis_name"),
            "material": analysis_spec.material.model_dump(mode="json"),
        }
        response = self._execute(self._code_assign_material(payload))
        result = response["result"]
        result["bridge_stdout"] = response.get("stdout", "")
        result["bridge_stderr"] = response.get("stderr", "")
        return result

    def cae_apply_boundary_conditions(
        self, analysis_spec: AnalysisSpec
    ) -> dict[str, Any]:
        prepared = self._require_session_value("prepared_geometry")
        load = analysis_spec.loads[0]
        payload = {
            "doc_name": self._require_session_value("doc_name"),
            "document_path": self._require_session_value("document_path"),
            "analysis_name": self._require_session_value("analysis_name"),
            "object_name": self._require_session_value("object_name"),
            "fixed_references": prepared["selected_fixed_references"],
            "load_references": prepared["selected_load_references"],
            "force_magnitude_n": load.magnitude_n,
            "force_direction": load.direction,
        }
        response = self._execute(self._code_apply_boundary_conditions(payload))
        result = response["result"]
        result["bridge_stdout"] = response.get("stdout", "")
        result["bridge_stderr"] = response.get("stderr", "")
        return result

    def cae_run_static_analysis(
        self,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
    ) -> dict[str, Any]:
        payload = {
            "doc_name": self._require_session_value("doc_name"),
            "document_path": self._require_session_value("document_path"),
            "analysis_name": self._require_session_value("analysis_name"),
            "solver_name": self._require_session_value("solver_name"),
            "working_dir": self._require_session_value("working_dir"),
            "ccx_binary": self._ccx_binary,
            "gmsh_binary": self._gmsh_binary,
            "reaction_force_n": analysis_spec.loads[0].magnitude_n,
            "estimated_mass_kg": mass_properties.mass_kg,
        }
        response = self._execute(self._code_run_solver(payload))
        result = response["result"]
        solver_dir = Path(self._require_session_value("working_dir"))
        for key in ("inp_file", "frd_file", "dat_file"):
            result[key] = self._materialize_solver_file(result.get(key), solver_dir)
        result["bridge_stdout"] = response.get("stdout", "")
        result["bridge_stderr"] = response.get("stderr", "")
        return result

    def cae_extract_results(
        self,
        task_spec: TaskSpec,
        analysis_spec: AnalysisSpec,
        solver_output: dict[str, Any],
    ) -> ResultSummary:
        max_stress = float(solver_output["max_von_mises_stress_mpa"])
        max_displacement = float(solver_output["max_displacement_mm"])
        stress_limit = task_spec.acceptance_criteria.max_von_mises_stress_mpa
        displacement_limit = task_spec.acceptance_criteria.max_displacement_mm
        fos = task_spec.material.yield_strength_mpa / max(max_stress, 1e-6)
        prepared = self._session.get("prepared_geometry", {})
        notes = [
            "Results were generated by FreeCAD FEM using Gmsh meshing and CalculiX solving.",
        ]
        if prepared:
            notes.append(
                f"Fixed references: {', '.join(prepared.get('selected_fixed_references', []))}"
            )
            notes.append(
                f"Load references: {', '.join(prepared.get('selected_load_references', []))}"
            )
        return ResultSummary(
            success=max_stress <= stress_limit and max_displacement <= displacement_limit,
            solver_mode=analysis_spec.solver_mode,
            generated_with_real_solver=True,
            producer_kind="freecad_fem",
            solver_executed=True,
            mesh_generated=True,
            engineering_validation=False,
            claims_advanced=False,
            max_von_mises_stress_mpa=max_stress,
            max_displacement_mm=max_displacement,
            factor_of_safety=round(fos, 3),
            meets_stress_limit=max_stress <= stress_limit,
            meets_displacement_limit=max_displacement <= displacement_limit,
            notes=notes,
        )

    def cae_generate_report_data(
        self,
        task_spec: TaskSpec,
        cad_spec: CadSpec,
        analysis_spec: AnalysisSpec,
        mass_properties: MassProperties,
        result_summary: ResultSummary,
    ) -> dict[str, Any]:
        report_data = {
            "task": task_spec.model_dump(mode="json"),
            "cad": cad_spec.model_dump(mode="json"),
            "analysis": analysis_spec.model_dump(mode="json"),
            "mass_properties": mass_properties.model_dump(mode="json"),
            "results": result_summary.model_dump(mode="json"),
        }
        if self._session.get("prepared_geometry"):
            report_data["prepared_geometry"] = self._session["prepared_geometry"]
        return report_data

    def cae_run_thermal_analysis(
        self,
        thermal_spec: ThermalAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> ThermalResultSummary:
        if cad_spec is None:
            raise ToolExecutionError(
                "FreecadFemCaeToolset.cae_run_thermal_analysis requires cad_spec "
                "with document_name and parameters['document_path'] and parameters['object_name']."
            )
        doc_name = cad_spec.document_name
        document_path = str(_param(cad_spec.parameters, "document_path", ""))
        object_name = str(_param(cad_spec.parameters, "object_name", ""))
        if not document_path or not object_name:
            raise ToolExecutionError(
                "cad_spec.parameters must include 'document_path' and 'object_name' for thermal FEM."
            )
        working_dir = str(_param(cad_spec.parameters, "working_dir", "/tmp/cae_thermal"))

        fixed_temps = [
            bc for bc in thermal_spec.thermal_boundary_conditions
            if bc.bc_type == "fixed_temperature" and bc.temperature_c is not None
        ]
        heat_flux_bcs = [
            bc for bc in thermal_spec.thermal_boundary_conditions
            if bc.bc_type == "heat_flux" and bc.heat_flux_w_m2 is not None
        ]
        convection_bcs = [
            bc for bc in thermal_spec.thermal_boundary_conditions
            if bc.bc_type == "convection"
        ]

        payload = {
            "doc_name": doc_name,
            "document_path": document_path,
            "object_name": object_name,
            "working_dir": working_dir,
            "mesh_size_mm": thermal_spec.mesh.target_size_mm,
            "thermal_conductivity_w_mk": thermal_spec.thermal_conductivity_w_mk,
            "fixed_temps": [
                {"name": bc.name, "target": bc.target, "temperature_c": bc.temperature_c}
                for bc in fixed_temps
            ],
            "heat_flux_bcs": [
                {"name": bc.name, "target": bc.target, "heat_flux_w_m2": bc.heat_flux_w_m2}
                for bc in heat_flux_bcs
            ],
            "convection_bcs": [
                {
                    "name": bc.name,
                    "target": bc.target,
                    "film_coefficient_w_m2k": bc.film_coefficient_w_m2k,
                    "ambient_temperature_c": bc.ambient_temperature_c,
                }
                for bc in convection_bcs
            ],
            "heat_sources": [hs.model_dump(mode="json") for hs in thermal_spec.heat_sources],
            "ccx_binary": self._ccx_binary,
            "gmsh_binary": self._gmsh_binary,
        }
        response = self._execute(self._code_run_thermal(payload))
        result = response["result"]

        base_temp = fixed_temps[0].temperature_c if fixed_temps else 20.0
        return ThermalResultSummary(
            success=bool(result.get("solver_ok", False)),
            solver_mode=thermal_spec.solver_mode,
            generated_with_real_solver=True,
            producer_kind="freecad_fem",
            solver_executed=True,
            mesh_generated=True,
            engineering_validation=False,
            claims_advanced=False,
            max_temperature_c=float(result.get("max_temperature_c", 0.0)),
            min_temperature_c=float(result.get("min_temperature_c", base_temp)),
            max_heat_flux_w_m2=float(result.get("max_heat_flux_w_m2", 0.0)),
            temperature_limit_c=None,
            meets_temperature_limit=True,
            notes=[
                "Thermal result from FreeCAD FEM using CalculiX steady-state thermomechanical solver.",
                f"Document: {document_path}",
            ],
        )

    def cae_run_modal_analysis(
        self,
        modal_spec: ModalAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> ModalResultSummary:
        if cad_spec is None:
            raise ToolExecutionError(
                "FreecadFemCaeToolset.cae_run_modal_analysis requires cad_spec "
                "with document_name and parameters['document_path'] and parameters['object_name']."
            )
        doc_name = cad_spec.document_name
        document_path = str(_param(cad_spec.parameters, "document_path", ""))
        object_name = str(_param(cad_spec.parameters, "object_name", ""))
        if not document_path or not object_name:
            raise ToolExecutionError(
                "cad_spec.parameters must include 'document_path' and 'object_name' for modal FEM."
            )
        working_dir = str(_param(cad_spec.parameters, "working_dir", "/tmp/cae_modal"))

        fixed_references: list[str] = []
        for bc in modal_spec.boundary_conditions:
            if bc.constraint_type == "fixed":
                fixed_references.append(bc.target)

        payload = {
            "doc_name": doc_name,
            "document_path": document_path,
            "object_name": object_name,
            "working_dir": working_dir,
            "mesh_size_mm": modal_spec.mesh.target_size_mm,
            "num_modes": modal_spec.num_modes,
            "fixed_references": fixed_references,
            "material": modal_spec.material.model_dump(mode="json"),
            "ccx_binary": self._ccx_binary,
            "gmsh_binary": self._gmsh_binary,
        }
        response = self._execute(self._code_run_modal(payload))
        result = response["result"]

        frequencies = [float(f) for f in result.get("natural_frequencies_hz", [])]
        if modal_spec.freq_range_hz:
            lo, hi = modal_spec.freq_range_hz[0], modal_spec.freq_range_hz[1]
            frequencies = [f for f in frequencies if lo <= f <= hi]

        return ModalResultSummary(
            success=bool(result.get("solver_ok", False)),
            solver_mode=modal_spec.solver_mode,
            generated_with_real_solver=True,
            producer_kind="freecad_fem",
            solver_executed=True,
            mesh_generated=True,
            engineering_validation=False,
            claims_advanced=False,
            natural_frequencies_hz=frequencies,
            mode_shapes_available=bool(result.get("mode_shapes_available", False)),
            notes=[
                "Modal analysis via FreeCAD FEM using CalculiX *FREQUENCY step.",
                f"Document: {document_path}",
                f"Fixed references: {', '.join(fixed_references) or 'none specified'}.",
            ],
        )

    def cae_run_buckling_analysis(
        self,
        buckling_spec: BucklingAnalysisSpec,
        cad_spec: CadSpec | None = None,
    ) -> BucklingResultSummary:
        if cad_spec is None:
            raise ToolExecutionError(
                "FreecadFemCaeToolset.cae_run_buckling_analysis requires cad_spec "
                "with document_name and parameters['document_path'] and parameters['object_name']."
            )
        doc_name = cad_spec.document_name
        document_path = str(_param(cad_spec.parameters, "document_path", ""))
        object_name = str(_param(cad_spec.parameters, "object_name", ""))
        if not document_path or not object_name:
            raise ToolExecutionError(
                "cad_spec.parameters must include 'document_path' and 'object_name' for buckling FEM."
            )
        working_dir = str(_param(cad_spec.parameters, "working_dir", "/tmp/cae_buckling"))

        fixed_references = [bc.target for bc in buckling_spec.boundary_conditions if bc.constraint_type == "fixed"]
        loads_payload = [load.model_dump(mode="json") for load in buckling_spec.loads]

        payload = {
            "doc_name": doc_name,
            "document_path": document_path,
            "object_name": object_name,
            "working_dir": working_dir,
            "mesh_size_mm": buckling_spec.mesh.target_size_mm,
            "num_buckling_modes": buckling_spec.num_buckling_modes,
            "fixed_references": fixed_references,
            "loads": loads_payload,
            "material": buckling_spec.material.model_dump(mode="json"),
            "ccx_binary": self._ccx_binary,
            "gmsh_binary": self._gmsh_binary,
        }
        response = self._execute(self._code_run_buckling(payload))
        result = response["result"]

        all_factors = [float(f) for f in result.get("all_load_factors", [])]
        clf = all_factors[0] if all_factors else 0.0
        return BucklingResultSummary(
            success=bool(result.get("solver_ok", False)),
            solver_mode=buckling_spec.solver_mode,
            generated_with_real_solver=True,
            producer_kind="freecad_fem",
            solver_executed=True,
            mesh_generated=True,
            engineering_validation=False,
            claims_advanced=False,
            critical_load_factor=round(clf, 4),
            all_load_factors=[round(f, 4) for f in all_factors],
            is_stable=clf > 1.0,
            mode_shapes_available=bool(result.get("mode_shapes_available", False)),
            notes=[
                "Buckling analysis via FreeCAD FEM using CalculiX *BUCKLE step.",
                f"Document: {document_path}",
                f"Critical load factor (mode 1): {round(clf, 3)}.",
            ],
        )

    # ------------------------------------------------------------------
    # Geometry inspection (extra capability, not part of CAEToolset ABC)
    # ------------------------------------------------------------------

    def inspect_geometry(
        self, document_path: str, object_name: str, doc_name: str | None = None
    ) -> GeometryInspection:
        """Return face catalog with geometric heuristics for agent-driven selection."""
        payload = {
            "document_path": document_path,
            "object_name": object_name,
            "doc_name": doc_name,
        }
        response = self._execute(self._code_inspect_geometry(payload))
        result = response["result"]
        faces = [f for f in result.get("faces", [])]
        return GeometryInspection(
            document_path=result["document_path"],
            object_name=result["object_name"],
            global_bbox=result["global_bbox"],
            faces=faces,
            suggested_fixed=result.get("suggested_fixed", []),
            suggested_load=result.get("suggested_load", []),
            notes=result.get("notes", []),
        )

    def _require_session_value(self, key: str) -> Any:
        if key not in self._session:
            raise ToolExecutionError(f"CAE session is missing required key: {key}")
        return self._session[key]

    def _materialize_solver_file(self, source_path: str | None, solver_dir: Path) -> str:
        if not source_path:
            return ""
        source = Path(source_path)
        if not source.exists():
            return str(source)
        solver_dir.mkdir(parents=True, exist_ok=True)
        destination = solver_dir / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        return str(destination)

    def _execute(self, code: str) -> dict[str, Any]:
        try:
            response = self._proxy.execute(code)
        except Exception as exc:
            raise ToolExecutionError(f"FreeCAD FEM XML-RPC call failed: {exc}") from exc

        if not isinstance(response, dict):
            raise ToolExecutionError("Unexpected FreeCAD FEM XML-RPC response format.")
        if not response.get("success", False):
            error = (
                response.get("error_traceback")
                or response.get("error_message")
                or response.get("stderr")
                or "Unknown FreeCAD FEM execution error."
            )
            raise ToolExecutionError(error)
        return response

    def _code_run_thermal(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import shutil
            import FreeCAD
            import ObjectsFem
            import femmesh.gmshtools as gmshtools
            from femtools import ccxtools

            payload = {payload!r}
            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            obj = doc.getObject(payload["object_name"])
            if obj is None or not hasattr(obj, "Shape"):
                raise ValueError("Target CAD object for thermal FEM not found.")

            working_dir = os.path.abspath(payload["working_dir"])
            os.makedirs(working_dir, exist_ok=True)

            ccx_binary = payload.get("ccx_binary") or shutil.which("ccx") or ""
            gmsh_binary = payload.get("gmsh_binary") or shutil.which("gmsh") or ""
            if not ccx_binary:
                raise FileNotFoundError("CalculiX binary could not be resolved for thermal analysis.")
            if not gmsh_binary:
                raise FileNotFoundError("Gmsh binary could not be resolved for thermal analysis.")

            for name in ["ThermalAnalysis", "ThermalSolver", "ThermalMesh",
                         "InitialTemp", "ThermalMaterial"]:
                existing = doc.getObject(name)
                if existing:
                    doc.removeObject(existing.Name)
            for bc_info in payload["fixed_temps"] + payload["heat_flux_bcs"] + payload["convection_bcs"]:
                existing = doc.getObject(bc_info["name"])
                if existing:
                    doc.removeObject(existing.Name)
            doc.recompute()

            analysis = ObjectsFem.makeAnalysis(doc, "ThermalAnalysis")
            solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "ThermalSolver")
            solver.WorkingDir = working_dir
            solver.WorkingDirectory = working_dir
            solver.AnalysisType = "thermomech"
            solver.ThermoMechSteadyState = True
            solver.GeometricalNonlinearity = "linear"
            solver.MatrixSolverType = "default"
            solver.SplitInputWriter = False
            analysis.addObject(solver)

            mesh_obj = ObjectsFem.makeMeshGmsh(doc, "ThermalMesh")
            mesh_obj.Shape = obj
            mesh_obj.CharacteristicLengthMax = float(payload["mesh_size_mm"])
            mesh_obj.CharacteristicLengthMin = max(float(payload["mesh_size_mm"]) / 3.0, 1.0)
            mesh_obj.ElementOrder = "1st"
            mesh_obj.SecondOrderLinear = False
            mesh_obj.WorkingDirectory = working_dir
            analysis.addObject(mesh_obj)

            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").SetString(
                "ccxBinaryPath", os.path.abspath(ccx_binary)
            )
            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetString(
                "gmshBinaryPath", os.path.abspath(gmsh_binary)
            )
            bin_dirs = []
            for binary in [ccx_binary, gmsh_binary]:
                d = os.path.dirname(os.path.abspath(binary))
                if d and d not in bin_dirs:
                    bin_dirs.append(d)
            if bin_dirs:
                os.environ["PATH"] = ";".join(bin_dirs + [os.environ.get("PATH", "")])

            gmshtools.GmshTools(mesh_obj).create_mesh()
            doc.recompute()

            mat_obj = ObjectsFem.makeMaterialSolid(doc, "ThermalMaterial")
            mat = mat_obj.Material
            mat["Name"] = "ThermalMat"
            mat["ThermalConductivity"] = f"{{payload['thermal_conductivity_w_mk']}} W/m/K"
            mat_obj.Material = mat
            analysis.addObject(mat_obj)

            init_temp = ObjectsFem.makeConstraintInitialTemperature(doc, "InitialTemp")
            init_temp.initialTemperature = 293.15
            analysis.addObject(init_temp)

            for bc_info in payload["fixed_temps"]:
                bc = ObjectsFem.makeConstraintTemperature(doc, bc_info["name"])
                bc.References = [(obj, bc_info["target"])]
                bc.Temperature = float(bc_info["temperature_c"]) + 273.15
                analysis.addObject(bc)

            for bc_info in payload["heat_flux_bcs"]:
                bc = ObjectsFem.makeConstraintHeatflux(doc, bc_info["name"])
                bc.References = [(obj, bc_info["target"])]
                bc.DFlux = float(bc_info["heat_flux_w_m2"])
                analysis.addObject(bc)

            for bc_info in payload["convection_bcs"]:
                bc = ObjectsFem.makeConstraintHeatflux(doc, bc_info["name"])
                bc.References = [(obj, bc_info["target"])]
                bc.AmbientTemp = float(bc_info.get("ambient_temperature_c", 20.0)) + 273.15
                bc.FilmCoef = float(bc_info.get("film_coefficient_w_m2k", 10.0))
                analysis.addObject(bc)

            doc.recompute()
            runner = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
            solver_ok = runner.run()
            doc.recompute()

            result_obj = None
            for candidate in analysis.Group:
                if hasattr(candidate, "Temperature"):
                    result_obj = candidate
                    break

            max_temp_c = 0.0
            min_temp_c = 0.0
            if result_obj is not None:
                temps_k = list(result_obj.Temperature)
                max_temp_c = max(temps_k) - 273.15
                min_temp_c = min(temps_k) - 273.15

            _result_ = {{
                "solver_ok": bool(solver_ok),
                "max_temperature_c": round(max_temp_c, 2),
                "min_temperature_c": round(min_temp_c, 2),
                "max_heat_flux_w_m2": 0.0,
                "result_object_name": result_obj.Name if result_obj else "",
                "working_dir": working_dir,
            }}
            """
        )

    def _code_run_modal(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import shutil
            import FreeCAD
            import ObjectsFem
            import femmesh.gmshtools as gmshtools
            from femtools import ccxtools

            payload = {payload!r}
            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            obj = doc.getObject(payload["object_name"])
            if obj is None or not hasattr(obj, "Shape"):
                raise ValueError("Target CAD object for modal FEM not found.")

            working_dir = os.path.abspath(payload["working_dir"])
            os.makedirs(working_dir, exist_ok=True)

            ccx_binary = payload.get("ccx_binary") or shutil.which("ccx") or ""
            gmsh_binary = payload.get("gmsh_binary") or shutil.which("gmsh") or ""
            if not ccx_binary:
                raise FileNotFoundError("CalculiX binary could not be resolved for modal analysis.")
            if not gmsh_binary:
                raise FileNotFoundError("Gmsh binary could not be resolved for modal analysis.")

            for name in ["ModalAnalysis", "ModalSolver", "ModalMesh", "ModalFixed", "ModalMaterial"]:
                existing = doc.getObject(name)
                if existing:
                    doc.removeObject(existing.Name)
            doc.recompute()

            analysis = ObjectsFem.makeAnalysis(doc, "ModalAnalysis")
            solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "ModalSolver")
            solver.WorkingDir = working_dir
            solver.WorkingDirectory = working_dir
            solver.AnalysisType = "frequency"
            solver.EigenmodesCount = int(payload["num_modes"])
            solver.GeometricalNonlinearity = "linear"
            solver.MatrixSolverType = "default"
            solver.SplitInputWriter = False
            analysis.addObject(solver)

            mesh_obj = ObjectsFem.makeMeshGmsh(doc, "ModalMesh")
            mesh_obj.Shape = obj
            mesh_obj.CharacteristicLengthMax = float(payload["mesh_size_mm"])
            mesh_obj.CharacteristicLengthMin = max(float(payload["mesh_size_mm"]) / 3.0, 1.0)
            mesh_obj.ElementOrder = "1st"
            mesh_obj.SecondOrderLinear = False
            mesh_obj.WorkingDirectory = working_dir
            analysis.addObject(mesh_obj)

            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").SetString(
                "ccxBinaryPath", os.path.abspath(ccx_binary)
            )
            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetString(
                "gmshBinaryPath", os.path.abspath(gmsh_binary)
            )
            bin_dirs = []
            for binary in [ccx_binary, gmsh_binary]:
                d = os.path.dirname(os.path.abspath(binary))
                if d and d not in bin_dirs:
                    bin_dirs.append(d)
            if bin_dirs:
                os.environ["PATH"] = ";".join(bin_dirs + [os.environ.get("PATH", "")])

            gmshtools.GmshTools(mesh_obj).create_mesh()

            mat_obj = ObjectsFem.makeMaterialSolid(doc, "ModalMaterial")
            mat = mat_obj.Material
            spec = payload["material"]
            mat["Name"] = spec["name"]
            mat["YoungsModulus"] = f"{{spec['elastic_modulus_mpa']}} MPa"
            mat["PoissonRatio"] = str(spec["poisson_ratio"])
            mat["Density"] = f"{{spec['density_kg_m3']}} kg/m^3"
            mat_obj.Material = mat
            analysis.addObject(mat_obj)

            fixed_refs = payload.get("fixed_references", [])
            if fixed_refs:
                fixed = ObjectsFem.makeConstraintFixed(doc, "ModalFixed")
                fixed.References = [(obj, ref) for ref in fixed_refs]
                analysis.addObject(fixed)

            doc.recompute()
            runner = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
            solver_ok = runner.run()
            doc.recompute()

            result_obj = None
            for candidate in analysis.Group:
                if hasattr(candidate, "Frequencies"):
                    result_obj = candidate
                    break

            frequencies_hz = []
            mode_shapes_available = False
            if result_obj is not None:
                frequencies_hz = [round(float(f), 3) for f in result_obj.Frequencies]
                mode_shapes_available = len(frequencies_hz) > 0

            _result_ = {{
                "solver_ok": bool(solver_ok),
                "natural_frequencies_hz": frequencies_hz,
                "mode_shapes_available": mode_shapes_available,
                "result_object_name": result_obj.Name if result_obj else "",
                "working_dir": working_dir,
            }}
            """
        )

    def _code_run_buckling(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import shutil
            import FreeCAD
            import ObjectsFem
            import femmesh.gmshtools as gmshtools
            from femtools import ccxtools

            payload = {payload!r}
            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            obj = doc.getObject(payload["object_name"])
            if obj is None or not hasattr(obj, "Shape"):
                raise ValueError("Target CAD object for buckling FEM not found.")

            working_dir = os.path.abspath(payload["working_dir"])
            os.makedirs(working_dir, exist_ok=True)

            ccx_binary = payload.get("ccx_binary") or shutil.which("ccx") or ""
            gmsh_binary = payload.get("gmsh_binary") or shutil.which("gmsh") or ""
            if not ccx_binary:
                raise FileNotFoundError("CalculiX binary could not be resolved for buckling analysis.")
            if not gmsh_binary:
                raise FileNotFoundError("Gmsh binary could not be resolved for buckling analysis.")

            for name in ["BucklingAnalysis", "BucklingSolver", "BucklingMesh",
                         "BucklingFixed", "BucklingMaterial", "BucklingForce", "BucklingForceDir"]:
                existing = doc.getObject(name)
                if existing:
                    doc.removeObject(existing.Name)
            doc.recompute()

            analysis = ObjectsFem.makeAnalysis(doc, "BucklingAnalysis")
            solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "BucklingSolver")
            solver.WorkingDir = working_dir
            solver.WorkingDirectory = working_dir
            solver.AnalysisType = "buckling"
            solver.EigenmodesCount = int(payload["num_buckling_modes"])
            solver.GeometricalNonlinearity = "linear"
            solver.MatrixSolverType = "default"
            solver.SplitInputWriter = False
            analysis.addObject(solver)

            mesh_obj = ObjectsFem.makeMeshGmsh(doc, "BucklingMesh")
            mesh_obj.Shape = obj
            mesh_obj.CharacteristicLengthMax = float(payload["mesh_size_mm"])
            mesh_obj.CharacteristicLengthMin = max(float(payload["mesh_size_mm"]) / 3.0, 1.0)
            mesh_obj.ElementOrder = "1st"
            mesh_obj.SecondOrderLinear = False
            mesh_obj.WorkingDirectory = working_dir
            analysis.addObject(mesh_obj)

            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").SetString(
                "ccxBinaryPath", os.path.abspath(ccx_binary)
            )
            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetString(
                "gmshBinaryPath", os.path.abspath(gmsh_binary)
            )
            bin_dirs = []
            for binary in [ccx_binary, gmsh_binary]:
                d = os.path.dirname(os.path.abspath(binary))
                if d and d not in bin_dirs:
                    bin_dirs.append(d)
            if bin_dirs:
                os.environ["PATH"] = ";".join(bin_dirs + [os.environ.get("PATH", "")])

            gmshtools.GmshTools(mesh_obj).create_mesh()

            mat_obj = ObjectsFem.makeMaterialSolid(doc, "BucklingMaterial")
            mat = mat_obj.Material
            spec = payload["material"]
            mat["Name"] = spec["name"]
            mat["YoungsModulus"] = f"{{spec['elastic_modulus_mpa']}} MPa"
            mat["PoissonRatio"] = str(spec["poisson_ratio"])
            mat["Density"] = f"{{spec['density_kg_m3']}} kg/m^3"
            mat_obj.Material = mat
            analysis.addObject(mat_obj)

            direction_map = {FORCE_DIRECTION_VECTORS!r}
            import Part as _Part

            fixed_refs = payload.get("fixed_references", [])
            if fixed_refs:
                fixed = ObjectsFem.makeConstraintFixed(doc, "BucklingFixed")
                fixed.References = [(obj, ref) for ref in fixed_refs]
                analysis.addObject(fixed)

            for i, load_info in enumerate(payload.get("loads", [])):
                dir_vec = FreeCAD.Vector(*direction_map.get(load_info["direction"], (0, 0, -1)))
                dir_helper = doc.addObject("Part::Feature", f"BucklingForceDir_{{i}}")
                dir_helper.Shape = _Part.makeLine(FreeCAD.Vector(0, 0, 0), dir_vec)
                if hasattr(dir_helper, "ViewObject"):
                    dir_helper.ViewObject.Visibility = False
                force = ObjectsFem.makeConstraintForce(doc, f"BucklingForce_{{i}}")
                force.References = [(obj, load_info["target"])]
                force.Force = f"{{load_info['magnitude_n']}} N"
                force.Direction = (dir_helper, ["Edge1"])
                force.Reversed = False
                analysis.addObject(force)

            doc.recompute()
            runner = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
            solver_ok = runner.run()
            doc.recompute()

            result_obj = None
            for candidate in analysis.Group:
                if hasattr(candidate, "EigenValues"):
                    result_obj = candidate
                    break

            all_factors = []
            mode_shapes_available = False
            if result_obj is not None:
                all_factors = [round(float(ev), 4) for ev in result_obj.EigenValues]
                mode_shapes_available = len(all_factors) > 0

            _result_ = {{
                "solver_ok": bool(solver_ok),
                "all_load_factors": all_factors,
                "mode_shapes_available": mode_shapes_available,
                "result_object_name": result_obj.Name if result_obj else "",
                "working_dir": working_dir,
            }}
            """
        )

    def _code_inspect_geometry(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import FreeCAD
            import json

            payload = {payload!r}
            doc_name = payload.get("doc_name")
            document_path = os.path.abspath(payload["document_path"])
            object_name = payload["object_name"]

            doc = FreeCAD.listDocuments().get(doc_name) if doc_name else FreeCAD.ActiveDocument
            if doc is None:
                if os.path.exists(document_path):
                    doc = FreeCAD.openDocument(document_path)
                else:
                    raise FileNotFoundError(f"Document not found: {{document_path}}")
            FreeCAD.setActiveDocument(doc.Name)

            obj = doc.getObject(object_name)
            if obj is None or not hasattr(obj, "Shape"):
                raise ValueError(f"Object not found or has no Shape: {object_name}")

            shape = obj.Shape
            bbox = shape.BoundBox
            thickness_guess = float(bbox.ZLength) if bbox.ZLength < bbox.YLength else float(bbox.YLength)
            tol = max(0.25, thickness_guess * 0.15)

            faces = []
            planar_faces = []
            cylindrical_faces = []

            for index, face in enumerate(shape.Faces, start=1):
                surface_type = type(face.Surface).__name__
                center = face.CenterOfMass
                descriptor = {{
                    "face": f"Face{{index}}",
                    "surface_type": surface_type,
                    "area": float(face.Area),
                    "center": [float(center.x), float(center.y), float(center.z)],
                    "bbox": {{
                        "xmin": float(face.BoundBox.XMin),
                        "xmax": float(face.BoundBox.XMax),
                        "ymin": float(face.BoundBox.YMin),
                        "ymax": float(face.BoundBox.YMax),
                        "zmin": float(face.BoundBox.ZMin),
                        "zmax": float(face.BoundBox.ZMax),
                    }},
                }}
                if surface_type == "Plane":
                    u0, u1, v0, v1 = face.ParameterRange
                    normal = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
                    descriptor["normal"] = [float(normal.x), float(normal.y), float(normal.z)]
                    planar_faces.append(descriptor)
                elif surface_type == "Cylinder":
                    cylindrical_faces.append(descriptor)
                faces.append(descriptor)

            # Geometric heuristics (no part_family)
            def pick_bottom_face():
                axis = 1
                candidates = [f for f in planar_faces if abs(f["center"][axis] - float(bbox.YMin)) <= tol]
                if not candidates:
                    candidates = [f for f in planar_faces if abs(f["center"][2] - float(bbox.ZMin)) <= tol]
                if not candidates:
                    candidates = planar_faces
                return [max(candidates, key=lambda item: item["area"])["face"]]

            def pick_top_face():
                candidates = [f for f in planar_faces if abs(f["center"][1] - float(bbox.YMax)) <= tol]
                if not candidates:
                    candidates = [f for f in planar_faces if abs(f["center"][2] - float(bbox.ZMin)) <= tol]
                if not candidates:
                    candidates = planar_faces
                return [max(candidates, key=lambda item: item["area"])["face"]]

            def pick_mounting_holes():
                candidates = [f for f in cylindrical_faces if f["center"][1] <= float(bbox.YMin) + max(thickness_guess * 2.0, tol)]
                candidates.sort(key=lambda item: (item["center"][1], item["center"][0]))
                refs = [f["face"] for f in candidates]
                return refs or pick_bottom_face()

            def pick_load_holes():
                candidates = [f for f in cylindrical_faces if f["center"][1] >= float(bbox.YMax) - max(thickness_guess * 3.0, tol * 4.0)]
                candidates.sort(key=lambda item: item["center"][1], reverse=True)
                refs = [f["face"] for f in candidates[:1]]
                return refs or pick_top_face()

            suggested_fixed = pick_mounting_holes()
            suggested_load = pick_load_holes()

            _result_ = {{
                "document_path": doc.FileName or document_path,
                "object_name": obj.Name,
                "global_bbox": {{
                    "xmin": float(bbox.XMin),
                    "xmax": float(bbox.XMax),
                    "ymin": float(bbox.YMin),
                    "ymax": float(bbox.YMax),
                    "zmin": float(bbox.ZMin),
                    "zmax": float(bbox.ZMax),
                }},
                "faces": faces,
                "suggested_fixed": suggested_fixed,
                "suggested_load": suggested_load,
                "notes": [
                    f"Suggested fixed references based on bottom-near geometry.",
                    f"Suggested load references based on top-near geometry.",
                    "Review these suggestions and provide explicit references if needed.",
                ],
            }}
            """
        )

    def _code_prepare_geometry(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import FreeCAD

            payload = {payload!r}

            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            obj = doc.getObject(payload["object_name"])
            if obj is None or not hasattr(obj, "Shape"):
                raise ValueError("Target CAD object for FEM preparation not found.")

            bbox = obj.Shape.BoundBox
            thickness = float(payload["thickness_mm"])
            tol = max(0.25, thickness * 0.15)
            faces = []

            for index, face in enumerate(obj.Shape.Faces, start=1):
                surface_type = type(face.Surface).__name__
                center = face.CenterOfMass
                descriptor = {{
                    "face": f"Face{{index}}",
                    "surface_type": surface_type,
                    "area": float(face.Area),
                    "center": [float(center.x), float(center.y), float(center.z)],
                    "bbox": {{
                        "xmin": float(face.BoundBox.XMin),
                        "xmax": float(face.BoundBox.XMax),
                        "ymin": float(face.BoundBox.YMin),
                        "ymax": float(face.BoundBox.YMax),
                        "zmin": float(face.BoundBox.ZMin),
                        "zmax": float(face.BoundBox.ZMax),
                    }},
                }}
                if surface_type == "Plane":
                    u0, u1, v0, v1 = face.ParameterRange
                    normal = face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
                    descriptor["normal"] = [float(normal.x), float(normal.y), float(normal.z)]
                faces.append(descriptor)

            planar_faces = [face for face in faces if face["surface_type"] == "Plane"]
            cylindrical_faces = [face for face in faces if face["surface_type"] == "Cylinder"]

            explicit_fixed = payload.get("explicit_fixed_references")
            explicit_load = payload.get("explicit_load_references")

            if explicit_fixed is not None and explicit_load is not None:
                selected_fixed = explicit_fixed if isinstance(explicit_fixed, list) else [explicit_fixed]
                selected_load = explicit_load if isinstance(explicit_load, list) else [explicit_load]
            else:
                def pick_bottom_face():
                    axis = 1
                    candidates = [
                        face for face in planar_faces
                        if abs(face["center"][axis] - float(bbox.YMin)) <= tol
                    ]
                    if not candidates:
                        candidates = [
                            face for face in planar_faces
                            if abs(face["center"][2] - float(bbox.ZMin)) <= tol
                        ]
                    if not candidates:
                        candidates = planar_faces
                    return [max(candidates, key=lambda item: item["area"])["face"]]

                def pick_mounting_holes():
                    candidates = [
                        face for face in cylindrical_faces
                        if face["center"][1] <= float(bbox.YMin) + max(thickness * 2.0, tol)
                    ]
                    candidates.sort(key=lambda item: (item["center"][1], item["center"][0]))
                    refs = [face["face"] for face in candidates]
                    return refs or pick_bottom_face()

                def pick_top_face():
                    candidates = [
                        face for face in planar_faces
                        if abs(face["center"][1] - float(bbox.YMax)) <= tol
                    ]
                    if not candidates:
                        candidates = [
                            face for face in planar_faces
                            if abs(face["center"][2] - float(bbox.ZMin)) <= tol
                        ]
                    if not candidates:
                        candidates = planar_faces
                    return [max(candidates, key=lambda item: item["area"])["face"]]

                def pick_load_holes():
                    candidates = [
                        face for face in cylindrical_faces
                        if face["center"][1] >= float(bbox.YMax) - max(thickness * 3.0, tol * 4.0)
                    ]
                    candidates.sort(key=lambda item: item["center"][1], reverse=True)
                    refs = [face["face"] for face in candidates[:1]]
                    return refs or pick_top_face()

                fixed_target = payload["fixed_target"]
                load_target = payload["load_target"]
                selected_fixed = pick_mounting_holes() if fixed_target == "mounting_holes" else pick_bottom_face()
                selected_load = pick_load_holes() if load_target == "load_hole" else pick_top_face()

            if not selected_fixed:
                raise ValueError("No deterministic fixed references could be selected for FEM setup.")
            if not selected_load:
                raise ValueError("No deterministic load references could be selected for FEM setup.")

            _result_ = {{
                "backend": "freecad_fem",
                "doc_name": doc.Name,
                "document_path": doc.FileName or document_path,
                "object_name": obj.Name,
                "working_dir": os.path.abspath(payload["working_dir"]),
                "selected_fixed_references": selected_fixed,
                "selected_load_references": selected_load,
                "face_catalog": faces,
                "bbox": {{
                    "xmin": float(bbox.XMin),
                    "xmax": float(bbox.XMax),
                    "ymin": float(bbox.YMin),
                    "ymax": float(bbox.YMax),
                    "zmin": float(bbox.ZMin),
                    "zmax": float(bbox.ZMax),
                }},
            }}
            """
        )

    def _code_generate_mesh(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import shutil
            import FreeCAD
            import ObjectsFem
            import femmesh.gmshtools as gmshtools

            payload = {payload!r}
            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            obj = doc.getObject(payload["object_name"])
            if obj is None or not hasattr(obj, "Shape"):
                raise ValueError("Target CAD object for meshing not found.")

            working_dir = os.path.abspath(payload["working_dir"])
            os.makedirs(working_dir, exist_ok=True)

            ccx_binary = payload.get("ccx_binary") or FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/Fem/Ccx"
            ).GetString("ccxBinaryPath", "") or shutil.which("ccx")
            gmsh_binary = payload.get("gmsh_binary") or FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/Fem/Gmsh"
            ).GetString("gmshBinaryPath", "") or shutil.which("gmsh")

            if not ccx_binary:
                raise FileNotFoundError("CalculiX binary could not be resolved inside FreeCAD.")
            if not gmsh_binary:
                raise FileNotFoundError("Gmsh binary could not be resolved inside FreeCAD.")

            bin_dirs = []
            for binary in [ccx_binary, gmsh_binary]:
                if binary:
                    bin_dir = os.path.dirname(os.path.abspath(binary))
                    if bin_dir and bin_dir not in bin_dirs:
                        bin_dirs.append(bin_dir)
            if bin_dirs:
                os.environ["PATH"] = ";".join(bin_dirs + [os.environ.get("PATH", "")])

            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").SetString(
                "ccxBinaryPath", os.path.abspath(ccx_binary)
            )
            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetString(
                "gmshBinaryPath", os.path.abspath(gmsh_binary)
            )

            for name in [
                "Analysis", "Solver", "Material", "MountingFixed", "ServiceForce",
                "ServiceForceDirection", "FEMMeshGmsh", "CCX_Results", "CCX_Results_Mesh",
                "Pipeline_CCX_Results", "ccx_dat_file",
            ]:
                existing = doc.getObject(name)
                if existing is not None:
                    doc.removeObject(existing.Name)
            doc.recompute()

            analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
            solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "Solver")
            solver.WorkingDir = working_dir
            solver.WorkingDirectory = working_dir
            solver.AnalysisType = "static"
            solver.GeometricalNonlinearity = "linear"
            solver.ThermoMechSteadyState = False
            solver.MatrixSolverType = "default"
            solver.IterationsControlParameterTimeUse = False
            solver.SplitInputWriter = False
            analysis.addObject(solver)

            mesh_obj = ObjectsFem.makeMeshGmsh(doc, "FEMMeshGmsh")
            analysis.addObject(mesh_obj)
            mesh_obj.Shape = obj
            mesh_obj.CharacteristicLengthMax = float(payload["mesh_size_mm"])
            mesh_obj.CharacteristicLengthMin = max(float(payload["mesh_size_mm"]) / 3.0, 1.0)
            mesh_obj.ElementOrder = "1st"
            mesh_obj.SecondOrderLinear = False
            mesh_obj.WorkingDirectory = working_dir

            gmshtools.GmshTools(mesh_obj).create_mesh()
            doc.recompute()

            _result_ = {{
                "backend": "freecad_fem",
                "analysis_name": analysis.Name,
                "solver_name": solver.Name,
                "mesh_name": mesh_obj.Name,
                "mesh_node_count": int(mesh_obj.FemMesh.NodeCount),
                "mesh_element_count": int(mesh_obj.FemMesh.VolumeCount),
                "working_dir": working_dir,
                "ccx_binary": os.path.abspath(ccx_binary),
                "gmsh_binary": os.path.abspath(gmsh_binary),
            }}
            """
        )

    def _code_assign_material(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import FreeCAD
            import Part
            import ObjectsFem

            payload = {payload!r}
            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            analysis = doc.getObject(payload["analysis_name"])
            if analysis is None:
                raise ValueError("Analysis object not found before material assignment.")

            existing = doc.getObject("Material")
            if existing is not None:
                doc.removeObject(existing.Name)
                doc.recompute()

            material = ObjectsFem.makeMaterialSolid(doc, "Material")
            mat = material.Material
            spec = payload["material"]
            mat["Name"] = spec["name"]
            mat["YoungsModulus"] = f"{{spec['elastic_modulus_mpa']}} MPa"
            mat["PoissonRatio"] = str(spec["poisson_ratio"])
            mat["Density"] = f"{{spec['density_kg_m3']}} kg/m^3"
            material.Material = mat
            analysis.addObject(material)
            doc.recompute()

            _result_ = {{
                "material_name": mat["Name"],
                "elastic_modulus_mpa": spec["elastic_modulus_mpa"],
                "poisson_ratio": spec["poisson_ratio"],
                "density_kg_m3": spec["density_kg_m3"],
            }}
            """
        )

    def _code_apply_boundary_conditions(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import FreeCAD
            import Part
            import ObjectsFem

            payload = {payload!r}
            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            analysis = doc.getObject(payload["analysis_name"])
            obj = doc.getObject(payload["object_name"])
            if analysis is None or obj is None:
                raise ValueError("Analysis or CAD object not found before boundary-condition assignment.")

            for name in ["MountingFixed", "ServiceForce", "ServiceForceDirection"]:
                existing = doc.getObject(name)
                if existing is not None:
                    doc.removeObject(existing.Name)
            doc.recompute()

            fixed = ObjectsFem.makeConstraintFixed(doc, "MountingFixed")
            fixed.References = [(obj, reference) for reference in payload["fixed_references"]]
            analysis.addObject(fixed)

            direction_map = {FORCE_DIRECTION_VECTORS!r}
            direction_vector = FreeCAD.Vector(*direction_map[payload["force_direction"]])
            direction_helper = doc.addObject("Part::Feature", "ServiceForceDirection")
            direction_helper.Shape = Part.makeLine(
                FreeCAD.Vector(0, 0, 0),
                direction_vector,
            )
            if hasattr(direction_helper, "ViewObject"):
                direction_helper.ViewObject.Visibility = False

            force = ObjectsFem.makeConstraintForce(doc, "ServiceForce")
            force.References = [(obj, reference) for reference in payload["load_references"]]
            force.Force = f"{{payload['force_magnitude_n']}} N"
            force.Direction = (direction_helper, ["Edge1"])
            force.Reversed = False
            analysis.addObject(force)
            doc.recompute()

            _result_ = {{
                "boundary_condition_count": 1,
                "load_count": 1,
                "fixed_references": payload["fixed_references"],
                "load_references": payload["load_references"],
                "force_direction": payload["force_direction"],
                "force_direction_vector": [float(force.DirectionVector.x), float(force.DirectionVector.y), float(force.DirectionVector.z)],
                "force_reversed": bool(force.Reversed),
                "force_direction_reference": direction_helper.Name,
            }}
            """
        )

    def _code_run_solver(self, payload: dict[str, Any]) -> str:
        return textwrap.dedent(
            f"""
            import os
            import shutil
            import FreeCAD
            from femtools import ccxtools

            payload = {payload!r}
            doc = FreeCAD.listDocuments().get(payload["doc_name"])
            document_path = os.path.abspath(payload["document_path"])
            if doc is None:
                if not os.path.exists(document_path):
                    raise FileNotFoundError(f"FreeCAD document not found: {{document_path}}")
                doc = FreeCAD.openDocument(document_path)
            FreeCAD.setActiveDocument(doc.Name)

            analysis = doc.getObject(payload["analysis_name"])
            solver = doc.getObject(payload["solver_name"])
            if analysis is None or solver is None:
                raise ValueError("Analysis or solver object not found before solve.")

            ccx_binary = payload.get("ccx_binary") or FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/Fem/Ccx"
            ).GetString("ccxBinaryPath", "") or shutil.which("ccx")
            gmsh_binary = payload.get("gmsh_binary") or FreeCAD.ParamGet(
                "User parameter:BaseApp/Preferences/Mod/Fem/Gmsh"
            ).GetString("gmshBinaryPath", "") or shutil.which("gmsh")
            if not ccx_binary:
                raise FileNotFoundError("CalculiX binary could not be resolved inside FreeCAD.")
            if not gmsh_binary:
                raise FileNotFoundError("Gmsh binary could not be resolved inside FreeCAD.")

            bin_dirs = []
            for binary in [ccx_binary, gmsh_binary]:
                if binary:
                    bin_dir = os.path.dirname(os.path.abspath(binary))
                    if bin_dir and bin_dir not in bin_dirs:
                        bin_dirs.append(bin_dir)
            if bin_dirs:
                os.environ["PATH"] = ";".join(bin_dirs + [os.environ.get("PATH", "")])

            solver.WorkingDir = os.path.abspath(payload["working_dir"])
            solver.WorkingDirectory = solver.WorkingDir
            os.makedirs(solver.WorkingDir, exist_ok=True)

            runner = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
            solver_ok = runner.run()
            doc.recompute()

            result_obj = doc.getObject("CCX_Results")
            if result_obj is None:
                for candidate in analysis.Group:
                    if hasattr(candidate, "vonMises") and hasattr(candidate, "DisplacementLengths"):
                        result_obj = candidate
                        break
            if result_obj is None:
                raise RuntimeError("CalculiX run finished without a readable result object.")

            if doc.FileName:
                doc.save()

            inp_file = runner.inp_file_name or ""
            base_path, _ = os.path.splitext(inp_file)
            frd_file = base_path + ".frd" if inp_file else ""
            dat_file = base_path + ".dat" if inp_file else ""

            _result_ = {{
                "backend": "freecad_fem",
                "generated_with_real_solver": True,
                "solver_ok": bool(solver_ok),
                "max_von_mises_stress_mpa": float(max(result_obj.vonMises)),
                "max_displacement_mm": float(max(result_obj.DisplacementLengths)),
                "reaction_force_n": float(payload["reaction_force_n"]),
                "estimated_mass_kg": float(payload["estimated_mass_kg"]),
                "result_object_name": result_obj.Name,
                "stats": list(result_obj.Stats),
                "document_path": doc.FileName or document_path,
                "working_dir": solver.WorkingDir,
                "inp_file": inp_file,
                "frd_file": frd_file,
                "dat_file": dat_file,
                "ccx_stdout": runner.ccx_stdout,
                "ccx_stderr": runner.ccx_stderr,
            }}
            """
        )
