"""Optional .aieng package context loader.

FreeCAD MCP must remain useful as a standalone server.
When a .aieng package path is provided, this module loads relevant resources
to improve constraint validation, evidence persistence, and auditability.

Missing optional resources are recorded as warnings, never inferred.
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AiengPackageContext(BaseModel):
    """Snapshot of an .aieng package's loaded state."""

    model_config = ConfigDict(extra="forbid")

    package_path: str = ""
    available: bool = False
    mode: Literal["standalone", "aieng_enhanced"] = "standalone"
    manifest: dict[str, Any] | None = None
    task_spec: dict[str, Any] | None = None
    external_tool_requirements: dict[str, Any] | None = None
    feature_graph: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    simulation_setup: dict[str, Any] | None = None
    claim_map: dict[str, Any] | None = None
    evidence_index: dict[str, Any] | None = None
    tool_trace: dict[str, Any] | None = None
    completeness_report: dict[str, Any] | None = None
    reference_map: dict[str, Any] | None = None
    interface_graph: dict[str, Any] | None = None
    cae_mapping: dict[str, Any] | None = None
    warnings: list[str] = []
    unsupported: list[str] = []


def _try_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _try_load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def _is_zipped_aieng(path: Path) -> bool:
    return path.is_file() and path.suffix == ".aieng"


def _load_from_directory(package_path: Path) -> AiengPackageContext:
    warnings: list[str] = []
    unsupported: list[str] = []

    manifest = _try_load_json(package_path / "manifest.json")
    if manifest is None:
        warnings.append("manifest.json not found; package identity unknown.")

    task_spec = _try_load_yaml(package_path / "task" / "task_spec.yaml")
    external_tool_requirements = _try_load_json(
        package_path / "task" / "external_tool_requirements.json"
    )
    feature_graph = _try_load_json(package_path / "graph" / "feature_graph.json")
    constraints = _try_load_json(package_path / "graph" / "constraints.json")
    simulation_setup = _try_load_yaml(package_path / "simulation" / "setup.yaml")
    claim_map = _try_load_json(package_path / "results" / "claim_map.json")
    evidence_index = _try_load_json(package_path / "results" / "evidence_index.json")
    tool_trace = _try_load_json(package_path / "provenance" / "tool_trace.json")
    completeness_report = _try_load_json(
        package_path / "validation" / "completeness_report.json"
    )
    reference_map = _try_load_json(package_path / "objects" / "reference_map.json")
    interface_graph = _try_load_json(package_path / "objects" / "interface_graph.json")
    cae_mapping = _try_load_json(package_path / "simulation" / "cae_mapping.json")

    return AiengPackageContext(
        package_path=str(package_path.resolve()),
        available=True,
        mode="aieng_enhanced",
        manifest=manifest,
        task_spec=task_spec,
        external_tool_requirements=external_tool_requirements,
        feature_graph=feature_graph,
        constraints=constraints,
        simulation_setup=simulation_setup,
        claim_map=claim_map,
        evidence_index=evidence_index,
        tool_trace=tool_trace,
        completeness_report=completeness_report,
        reference_map=reference_map,
        interface_graph=interface_graph,
        cae_mapping=cae_mapping,
        warnings=warnings,
        unsupported=unsupported,
    )


def _try_load_json_from_zip(
    zf: zipfile.ZipFile, name: str
) -> dict[str, Any] | None:
    try:
        with zf.open(name) as f:
            return json.load(f)
    except (KeyError, json.JSONDecodeError, Exception):
        return None


def _try_load_yaml_from_zip(
    zf: zipfile.ZipFile, name: str
) -> dict[str, Any] | None:
    try:
        with zf.open(name) as f:
            import yaml

            return yaml.safe_load(f) or {}
    except (KeyError, Exception):
        return None


def _load_from_zip(package_path: Path) -> AiengPackageContext:
    warnings: list[str] = []
    unsupported: list[str] = []

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            manifest = _try_load_json_from_zip(zf, "manifest.json")
            if manifest is None:
                warnings.append("manifest.json not found; package identity unknown.")

            task_spec = _try_load_yaml_from_zip(zf, "task/task_spec.yaml")
            external_tool_requirements = _try_load_json_from_zip(
                zf, "task/external_tool_requirements.json"
            )
            feature_graph = _try_load_json_from_zip(zf, "graph/feature_graph.json")
            constraints = _try_load_json_from_zip(zf, "graph/constraints.json")
            simulation_setup = _try_load_yaml_from_zip(zf, "simulation/setup.yaml")
            claim_map = _try_load_json_from_zip(zf, "results/claim_map.json")
            evidence_index = _try_load_json_from_zip(zf, "results/evidence_index.json")
            tool_trace = _try_load_json_from_zip(zf, "provenance/tool_trace.json")
            completeness_report = _try_load_json_from_zip(
                zf, "validation/completeness_report.json"
            )
            reference_map = _try_load_json_from_zip(zf, "objects/reference_map.json")
            interface_graph = _try_load_json_from_zip(zf, "objects/interface_graph.json")
            cae_mapping = _try_load_json_from_zip(zf, "simulation/cae_mapping.json")
    except zipfile.BadZipFile as exc:
        return AiengPackageContext(
            package_path=str(package_path.resolve()),
            available=False,
            mode="standalone",
            warnings=[f"Malformed .aieng zip file: {exc}"],
            unsupported=["Zipped .aieng package could not be read."],
        )

    return AiengPackageContext(
        package_path=str(package_path.resolve()),
        available=True,
        mode="aieng_enhanced",
        manifest=manifest,
        task_spec=task_spec,
        external_tool_requirements=external_tool_requirements,
        feature_graph=feature_graph,
        constraints=constraints,
        simulation_setup=simulation_setup,
        claim_map=claim_map,
        evidence_index=evidence_index,
        tool_trace=tool_trace,
        completeness_report=completeness_report,
        reference_map=reference_map,
        interface_graph=interface_graph,
        cae_mapping=cae_mapping,
        warnings=warnings,
        unsupported=unsupported,
    )


def load_aieng_context(package_path: str | None) -> AiengPackageContext:
    """Load an .aieng package context, or return standalone mode.

    Args:
        package_path: Path to an unpacked .aieng directory, a zipped .aieng
            file, or None for standalone mode.

    Returns:
        AiengPackageContext with loaded resources and any warnings.
    """
    if package_path is None:
        return AiengPackageContext(
            available=False,
            mode="standalone",
            warnings=["No .aieng context provided; running in standalone mode without package-level constraints."],
        )

    path = Path(package_path)
    if not path.exists():
        return AiengPackageContext(
            package_path=str(path),
            available=False,
            mode="standalone",
            warnings=[f"Provided package path does not exist: {path}"],
        )

    if _is_zipped_aieng(path):
        return _load_from_zip(path)

    if path.is_dir():
        return _load_from_directory(path)

    return AiengPackageContext(
        package_path=str(path),
        available=False,
        mode="standalone",
        warnings=[f"Package path is not a directory or recognised .aieng file: {path}"],
    )
