"""CAE pre-processing summary generator for .aieng packages.

This module generates LLM-readable summaries of CAE setup readiness from
detected setup artifacts. It does NOT run solvers, generate meshes, or
validate physical correctness. All claims are honest: presence-only.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .schema_versions import CAE_PREPROCESSING_SUMMARY_SCHEMA

PREPROCESSING_SUMMARY_PATH = "simulation/preprocessing_summary.json"
PREPROCESSING_MARKDOWN_PATH = "simulation/preprocessing_summary.md"
SIMULATION_DIR = "simulation/"

# Setup artifact paths we inspect
_SETUP_ARTIFACT_PATHS: tuple[str, ...] = (
    "graph/constraints.json",
    "simulation/cae_imports/parsed_materials.json",
    "simulation/cae_imports/parsed_boundary_conditions.json",
    "simulation/cae_imports/parsed_loads.json",
    "simulation/cae_mapping.json",
    "simulation/mesh/mesh_metadata.json",
    "simulation/mesh/model.vtk",
    "simulation/mesh/model.vtu",
    "simulation/solver_settings.json",
)


def _read_json_from_zip(zf: zipfile.ZipFile, path: str) -> Any | None:
    """Read and parse JSON from a zip member. Return None on missing or invalid."""
    if path not in zf.namelist():
        return None
    try:
        return json.loads(zf.read(path))
    except (json.JSONDecodeError, KeyError):
        return None


def _read_load_cases(zf: zipfile.ZipFile) -> list[dict[str, Any]]:
    """Read simulation/load_cases/*.json from the package."""
    load_cases: list[dict[str, Any]] = []
    prefix = "simulation/load_cases/"
    for name in zf.namelist():
        if name.startswith(prefix) and name.endswith(".json"):
            raw = _read_json_from_zip(zf, name)
            if isinstance(raw, dict):
                load_cases.append(raw)
    return load_cases


def generate_preprocessing_summary(package_path: str | Path) -> dict[str, Any]:
    """Generate an honest CAE pre-processing summary dict.

    Args:
        package_path: Path to the .aieng package.

    Returns:
        JSON-serializable summary dict (schema_version
        :data:`~aieng.schema_versions.CAE_PREPROCESSING_SUMMARY_SCHEMA`).
    """
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package not found: {path}")

    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())

        has_materials = "simulation/cae_imports/parsed_materials.json" in names
        has_boundary_conditions = "simulation/cae_imports/parsed_boundary_conditions.json" in names
        has_loads = "simulation/cae_imports/parsed_loads.json" in names
        has_constraints = "graph/constraints.json" in names
        has_mesh = any(p in names for p in ("simulation/mesh/mesh_metadata.json", "simulation/mesh/model.vtk", "simulation/mesh/model.vtu"))
        has_solver_settings = "simulation/solver_settings.json" in names
        has_cae_mapping = "simulation/cae_mapping.json" in names

        materials = _read_json_from_zip(zf, "simulation/cae_imports/parsed_materials.json")
        boundary_conditions = _read_json_from_zip(zf, "simulation/cae_imports/parsed_boundary_conditions.json")
        loads = _read_json_from_zip(zf, "simulation/cae_imports/parsed_loads.json")
        constraints = _read_json_from_zip(zf, "graph/constraints.json")
        mesh_metadata = _read_json_from_zip(zf, "simulation/mesh/mesh_metadata.json")
        solver_settings = _read_json_from_zip(zf, "simulation/solver_settings.json")
        cae_mapping = _read_json_from_zip(zf, "simulation/cae_mapping.json")
        load_cases = _read_load_cases(zf)

    warnings: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        if "simulation/mesh/mesh_metadata.json" in zf.namelist() and mesh_metadata is None:
            warnings.append("simulation/mesh/mesh_metadata.json is malformed; ignored.")
        if "simulation/solver_settings.json" in zf.namelist() and solver_settings is None:
            warnings.append("simulation/solver_settings.json is malformed; ignored.")
        if "simulation/cae_mapping.json" in zf.namelist() and cae_mapping is None:
            warnings.append("simulation/cae_mapping.json is malformed; ignored.")

    missing_items: list[str] = []
    if not has_materials:
        missing_items.append("materials")
    if not has_loads:
        missing_items.append("loads")
    if not has_boundary_conditions:
        missing_items.append("boundary_conditions")
    if not has_constraints:
        missing_items.append("constraints")
    if not has_mesh:
        missing_items.append("mesh")
    if not has_solver_settings:
        missing_items.append("solver_settings")
    if not load_cases:
        missing_items.append("load_cases")
    if not has_cae_mapping:
        missing_items.append("cae_mapping")

    # Conservative readiness check
    ready_for_solver = (
        has_materials
        and has_loads
        and has_boundary_conditions
        and has_mesh
        and (has_solver_settings or bool(load_cases))
    )

    setup_files = [p for p in _SETUP_ARTIFACT_PATHS if p in names]
    if load_cases:
        setup_files.append("simulation/load_cases/")

    # Build artifact lists
    materials_list = _extract_list(materials, "materials")
    loads_list = _extract_list(loads, "loads")
    boundary_conditions_list = _extract_list(boundary_conditions, "boundary_conditions")
    constraints_list = _extract_list(constraints, "constraints")
    mesh_files = [p for p in ("simulation/mesh/mesh_metadata.json", "simulation/mesh/model.vtk", "simulation/mesh/model.vtu") if p in names]
    load_cases_list = _normalize_load_cases(load_cases)

    llm = _build_llm_summary(
        ready_for_solver=ready_for_solver,
        has_materials=has_materials,
        has_loads=has_loads,
        has_boundary_conditions=has_boundary_conditions,
        has_constraints=has_constraints,
        has_mesh=has_mesh,
        has_solver_settings=has_solver_settings,
        has_cae_mapping=has_cae_mapping,
        missing_items=missing_items,
    )

    return {
        "schema_version": CAE_PREPROCESSING_SUMMARY_SCHEMA,
        "summary_type": "cae_preprocessing",
        "source": {
            "package_path": str(path),
            "setup_files": setup_files,
        },
        "status": {
            "has_cae_setup": any([has_materials, has_loads, has_boundary_conditions, has_constraints, has_cae_mapping]),
            "has_materials": has_materials,
            "has_loads": has_loads,
            "has_boundary_conditions": has_boundary_conditions,
            "has_constraints": has_constraints,
            "has_mesh": has_mesh,
            "has_load_cases": bool(load_cases),
            "has_solver_settings": has_solver_settings,
            "has_cae_mapping": has_cae_mapping,
            "ready_for_solver": ready_for_solver,
            "missing_items": missing_items,
            "warnings": warnings,
        },
        "artifacts": {
            "materials": materials_list,
            "loads": loads_list,
            "boundary_conditions": boundary_conditions_list,
            "constraints": constraints_list,
            "mesh_files": mesh_files,
            "mesh_metadata": mesh_metadata if isinstance(mesh_metadata, dict) else None,
            "load_cases": load_cases_list,
            "solver_settings": solver_settings if isinstance(solver_settings, dict) else None,
            "cae_mapping": cae_mapping if isinstance(cae_mapping, dict) else None,
        },
        "llm_summary": llm,
    }


def _extract_list(data: Any, key: str) -> list[dict[str, Any]]:
    """Extract a list of items from parsed JSON."""
    if not isinstance(data, dict):
        return []
    items = data.get(key)
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _normalize_load_cases(load_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize load case entries for the summary."""
    result: list[dict[str, Any]] = []
    for lc in load_cases:
        result.append({
            "id": lc.get("id", "unknown"),
            "name": lc.get("name", "unknown"),
            "type": lc.get("type", "unknown"),
            "magnitude": lc.get("magnitude"),
            "unit": lc.get("unit"),
        })
    return result


def _build_llm_summary(
    *,
    ready_for_solver: bool,
    has_materials: bool,
    has_loads: bool,
    has_boundary_conditions: bool,
    has_constraints: bool,
    has_mesh: bool,
    has_solver_settings: bool,
    has_cae_mapping: bool,
    missing_items: list[str],
) -> dict[str, Any]:
    """Build the honest LLM-oriented summary block."""
    present = [k for k, v in {
        "materials": has_materials,
        "loads": has_loads,
        "boundary_conditions": has_boundary_conditions,
        "constraints": has_constraints,
        "mesh": has_mesh,
        "solver_settings": has_solver_settings,
        "cae_mapping": has_cae_mapping,
    }.items() if v]

    if ready_for_solver:
        one_line = "CAE pre-processing setup appears complete; package may be ready for external solver execution."
    elif present:
        one_line = f"Partial CAE pre-processing setup detected ({', '.join(present)}); missing: {', '.join(missing_items)}."
    else:
        one_line = "No CAE pre-processing setup artifacts detected; package is CAD-only."

    key_findings: list[str] = []
    if has_materials:
        key_findings.append("Material definitions present.")
    if has_loads:
        key_findings.append("Load definitions present.")
    if has_boundary_conditions:
        key_findings.append("Boundary condition definitions present.")
    if has_constraints:
        key_findings.append("Constraint definitions present.")
    if has_mesh:
        key_findings.append("Mesh file(s) present.")
    if has_solver_settings:
        key_findings.append("Solver settings present.")
    if has_cae_mapping:
        key_findings.append("CAD-to-CAE mapping present.")
    if not present:
        key_findings.append("No CAE setup artifacts found.")

    risks: list[str] = []
    if missing_items:
        risks.append(f"Missing setup items may prevent solver execution: {', '.join(missing_items)}.")
    if has_mesh and not has_materials:
        risks.append("Mesh present but no material definitions; solver may fail.")
    if has_mesh and not has_boundary_conditions:
        risks.append("Mesh present but no boundary conditions; solver may be unconstrained.")
    if not risks:
        risks.append("No obvious setup risks detected from artifact presence.")

    recommended_next_actions: list[str] = []
    if missing_items:
        recommended_next_actions.append(f"Add missing setup artifacts: {', '.join(missing_items)}.")
    if ready_for_solver:
        recommended_next_actions.append("Export to external solver and execute simulation.")
    if not present:
        recommended_next_actions.append("Import CAE setup (materials, loads, BCs) or define simulation intent.")

    limitations: list[str] = [
        "This summary is based on package artifact presence only.",
        "It does not validate physical correctness, mesh quality, or solver convergence.",
        "It does not execute solvers or generate meshes.",
        "Readiness for solver is a conservative heuristic, not a guarantee.",
    ]

    return {
        "one_line": one_line,
        "key_findings": key_findings,
        "risks": risks,
        "recommended_next_actions": recommended_next_actions,
        "limitations": limitations,
    }


def generate_preprocessing_markdown(summary: dict[str, Any]) -> str:
    """Generate a human/LLM-readable markdown summary from the preprocessing summary dict."""
    status = summary.get("status", {})
    llm = summary.get("llm_summary", {})
    artifacts = summary.get("artifacts", {})
    lines: list[str] = []

    lines.append("# CAE Pre-processing Summary")
    lines.append("")
    lines.append(f"**Schema version:** {summary.get('schema_version', 'unknown')}")
    lines.append("")

    lines.append("## Setup Status")
    lines.append("")
    lines.append(f"- **Materials:** {'present' if status.get('has_materials') else 'missing'}")
    lines.append(f"- **Loads:** {'present' if status.get('has_loads') else 'missing'}")
    lines.append(f"- **Boundary conditions:** {'present' if status.get('has_boundary_conditions') else 'missing'}")
    lines.append(f"- **Constraints:** {'present' if status.get('has_constraints') else 'missing'}")
    lines.append(f"- **Mesh:** {'present' if status.get('has_mesh') else 'missing'}")
    lines.append(f"- **Solver settings:** {'present' if status.get('has_solver_settings') else 'missing'}")
    lines.append(f"- **Load cases:** {'present' if status.get('has_load_cases') else 'missing'}")
    lines.append(f"- **CAE mapping:** {'present' if status.get('has_cae_mapping') else 'missing'}")
    lines.append(f"- **Ready for solver:** {'yes' if status.get('ready_for_solver') else 'no'}")
    lines.append("")

    if status.get("missing_items"):
        lines.append("## Missing items")
        lines.append("")
        for item in status["missing_items"]:
            lines.append(f"- {item}")
        lines.append("")

    if artifacts.get("load_cases"):
        lines.append("## Load cases")
        lines.append("")
        for lc in artifacts["load_cases"]:
            mag = f" — {lc.get('magnitude')}{lc.get('unit', '')}" if lc.get("magnitude") is not None else ""
            lines.append(f"- {lc.get('name', 'unknown')} ({lc.get('type', 'unknown')}){mag}")
        lines.append("")

    if artifacts.get("solver_settings"):
        lines.append("## Solver settings")
        lines.append("")
        ss = artifacts["solver_settings"]
        lines.append(f"- Solver type: {ss.get('solver_type', 'unknown')}")
        lines.append(f"- Analysis type: {ss.get('analysis_type', 'unknown')}")
        lines.append("")

    if llm.get("risks"):
        lines.append("## Risks")
        lines.append("")
        for risk in llm["risks"]:
            lines.append(f"- {risk}")
        lines.append("")

    if llm.get("recommended_next_actions"):
        lines.append("## Recommended next actions")
        lines.append("")
        for action in llm["recommended_next_actions"]:
            lines.append(f"- {action}")
        lines.append("")

    if llm.get("limitations"):
        lines.append("## Limitations")
        lines.append("")
        for lim in llm["limitations"]:
            lines.append(f"- {lim}")
        lines.append("")

    return "\n".join(lines)


def write_preprocessing_summary_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write preprocessing_summary.json and preprocessing_summary.md into the package.

    Uses the standard aieng safe-rewrite pattern (temp file + atomic move).

    Args:
        package_path: Path to the .aieng package.
        overwrite: Whether to overwrite existing summary files.

    Returns:
        Path to the updated package.
    """
    path = Path(package_path)
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if not overwrite:
                for existing in (PREPROCESSING_SUMMARY_PATH, PREPROCESSING_MARKDOWN_PATH):
                    if existing in names:
                        raise FileExistsError(
                            f"{existing} already exists; use --overwrite to replace it"
                        )
            manifest = json.loads(package.read("manifest.json"))
            existing_members = _read_existing_members(package)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    summary = generate_preprocessing_summary(path)
    markdown = generate_preprocessing_markdown(summary)

    _rewrite_package_with_preprocessing(path, existing_members, manifest, summary, markdown)
    return path


def _read_existing_members(package: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, bytes]]:
    skip = {
        "manifest.json",
        PREPROCESSING_SUMMARY_PATH,
        PREPROCESSING_MARKDOWN_PATH,
    }
    seen: set[str] = set()
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info in package.infolist():
        if info.filename in skip or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members


def _rewrite_package_with_preprocessing(
    path: Path,
    existing_members: list[tuple[zipfile.ZipInfo, bytes]],
    manifest: dict[str, Any],
    summary: dict[str, Any],
    markdown: str,
) -> None:
    resources = manifest.setdefault("resources", {})
    sim_resources = resources.setdefault("simulation", {})
    if not isinstance(sim_resources, dict):
        raise ValueError("manifest resources.simulation must be an object")
    sim_resources["preprocessing_summary"] = PREPROCESSING_SUMMARY_PATH
    sim_resources["preprocessing_summary_md"] = PREPROCESSING_MARKDOWN_PATH

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    existing_filenames = {info.filename for info, _ in existing_members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out_package:
            for info, data in existing_members:
                out_package.writestr(info, data)
            if SIMULATION_DIR not in existing_filenames:
                out_package.writestr(SIMULATION_DIR, b"")
            out_package.writestr("manifest.json", manifest_json)
            out_package.writestr(
                PREPROCESSING_SUMMARY_PATH,
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
            )
            out_package.writestr(PREPROCESSING_MARKDOWN_PATH, markdown.encode("utf-8"))
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
