from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION, __version__
from aieng.backend_adapter import BackendAdapter
from aieng.backend_discovery import discover_backend
from aieng.geometry.topology_extractor import extract_topology_package
from aieng.graph.aag import build_aag_package
from aieng.graph.feature_graph import recognize_features_package
from aieng.modeling_plan.validate import validate_modeling_plan
from aieng.package import model_id_from_package_path
from aieng.validation.status_writer import update_validation_status_package


# Directories required inside a .aieng package
_PACKAGE_DIRECTORIES = (
    "geometry/",
    "graph/",
    "engineering_context/",
    "simulation/",
    "ai/",
    "ai/patches/",
    "results/",
    "previews/",
    "validation/",
    "visual/",
    "provenance/",
    "authoring/",
)


def _build_modeling_summary(result, *, geometry_available: bool = False) -> dict[str, Any]:
    """Build modeling summary for status.yaml from a BackendExecutionResult."""
    modeling_steps = [s for s in result.steps if s.operation in {"create_box", "create_cylindrical_cut"}]
    return {
        "modeling_phase": "phase_1",
        "modeling_status": result.overall_status,
        "plan_validation": "pass",
        "backend_id": result.backend_id,
        "transport_type": result.transport_type,
        "kernel": result.kernel,
        "geometry_available": geometry_available,
        "diagnostic_package": result.overall_status != "success",
        "step_count": len(modeling_steps),
        "successful_steps": sum(1 for s in modeling_steps if s.status == "success"),
        "failed_steps": [s.step_id for s in modeling_steps if s.status == "failed"],
        "errors": result.errors,
        "warnings": result.warnings,
    }


def _run_semantic_postprocess(package_path: Path, *, strict: bool = False) -> dict[str, Any]:
    """Run semantic post-processing chain on a .aieng package.

    Returns a postprocess summary dict.
    """
    summary: dict[str, Any] = {
        "requested": True,
        "topology_status": "skipped",
        "aag_status": "skipped",
        "feature_graph_status": "skipped",
        "errors": [],
        "warnings": [],
    }

    # Step 1: Topology extraction
    try:
        extract_topology_package(package_path, overwrite=True)
        summary["topology_status"] = "success"
    except Exception as exc:
        summary["topology_status"] = "failed"
        summary["errors"].append(f"topology extraction failed: {exc}")
        if strict:
            raise
        summary["warnings"].append("AAG and feature graph skipped due to topology extraction failure.")
        return summary

    # Step 2: AAG
    try:
        build_aag_package(package_path, overwrite=True)
        summary["aag_status"] = "success"
    except Exception as exc:
        summary["aag_status"] = "failed"
        summary["errors"].append(f"AAG build failed: {exc}")
        if strict:
            raise
        summary["warnings"].append("Feature graph skipped due to AAG build failure.")
        return summary

    # Step 3: Feature graph
    try:
        recognize_features_package(package_path, overwrite=True)
        summary["feature_graph_status"] = "success"
    except Exception as exc:
        summary["feature_graph_status"] = "failed"
        summary["errors"].append(f"feature recognition failed: {exc}")
        if strict:
            raise

    return summary


def init_from_plan(
    plan_path: str | Path,
    out_path: str | Path,
    *,
    backend_id: str = "fake",
    overwrite: bool = False,
    backend_options: dict[str, object] | None = None,
    run_postprocess: bool = True,
    postprocess_strict: bool = False,
) -> Path:
    """Execute a modeling plan through a backend and assemble a .aieng package.

    Args:
        plan_path: Path to the modeling_plan.json file.
        out_path: Path for the output .aieng package.
        backend_id: Backend identifier for discover_backend().
        overwrite: If True, replace an existing package.
        backend_options: Optional kwargs passed to the backend constructor.
        run_postprocess: If True (default), run semantic post-processing
            (topology extraction, AAG build, feature recognition) after
            successful modeling. Only applies when this function is explicitly
            invoked; the authoring pipeline itself is not auto-triggered.
        postprocess_strict: If True, any post-processing failure raises an
            exception. If False (default), failures are logged in the
            postprocess summary and the package is preserved.

    Returns:
        Path to the created .aieng package.

    Raises:
        ValueError: If plan validation fails.
        RuntimeError: If backend capability check fails.
    """
    plan_path = Path(plan_path)
    out_path = Path(out_path)

    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    if out_path.suffix != ".aieng":
        raise ValueError("output path must end with .aieng")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"package already exists: {out_path}")

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    # 1. Plan validation — HARD GATE. No package on failure.
    report = validate_modeling_plan(plan)
    if not report.ok:
        raise ValueError(f"Plan validation failed:\n{report.render()}")

    # 2. Discover & instantiate backend
    BackendClass = discover_backend(backend_id)
    if backend_options:
        backend: BackendAdapter = BackendClass(**backend_options)
    else:
        backend = BackendClass()

    unsupported = backend.validate_capabilities(plan)
    if unsupported:
        raise RuntimeError(f"Backend capability check failed: {unsupported}")

    # 3. Execute plan in temp dir
    with tempfile.TemporaryDirectory(prefix="aieng_backend_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        result = backend.execute_plan(plan, tmpdir_path)

        # 4. Build package
        out_path.parent.mkdir(parents=True, exist_ok=True)
        model_id = model_id_from_package_path(out_path)

        manifest = {
            "model_id": model_id,
            "format_version": FORMAT_VERSION,
            "units": {
                "length": plan.get("units", {}).get("length", "mm"),
                "mass": "kg",
                "force": "N",
                "stress": "MPa",
            },
            "resources": {
                "geometry": {},
                "graph": {},
                "simulation": {},
                "ai": {"patches": []},
                "results": {},
                "previews": {},
                "authoring": {},
                "provenance": {},
                "validation": {},
            },
            "created_by": {
                "tool": f"aieng {__version__}",
                "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            },
        }

        # Register resources
        manifest["resources"]["authoring"]["modeling_plan"] = "authoring/modeling_plan.json"
        manifest["resources"]["authoring"]["construction_history"] = "authoring/construction_history.json"
        manifest["resources"]["provenance"]["tool_trace"] = "provenance/tool_trace.jsonl"
        manifest["resources"]["validation"]["status"] = "validation/status.yaml"

        # Fallback evidence if backend provided none
        evidence_entries = list(result.evidence_entries)
        if not evidence_entries:
            evidence_entries.append({
                "evidence_id": "ev_fallback_0001",
                "evidence_type": "validation_report",
                "producer": {
                    "kind": "backend_adapter",
                    "tool_id": backend_id,
                },
                "artifact": {
                    "kind": "json",
                    "path": "authoring/construction_history.json",
                },
                "claim_support": [],
                "verification": {
                    "status": "missing",
                    "notes": "Backend did not provide evidence entries.",
                },
            })
        manifest["resources"]["results"]["evidence_index"] = "results/evidence_index.json"

        # FIX: Register geometry resources BEFORE manifest is serialized into the zip.
        has_geometry = result.exported_step_path is not None and Path(result.exported_step_path).exists()
        if has_geometry:
            manifest["resources"]["geometry"]["source"] = "geometry/source.step"
            manifest["resources"]["geometry"]["normalized"] = "geometry/normalized.step"

        with zipfile.ZipFile(out_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Directories
            for directory in _PACKAGE_DIRECTORIES:
                zf.writestr(directory, b"")

            # Manifest
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")

            # Modeling plan (frozen intent)
            zf.writestr("authoring/modeling_plan.json", json.dumps(plan, indent=2, sort_keys=True) + "\n")

            # Construction history
            zf.writestr(
                "authoring/construction_history.json",
                json.dumps(result.construction_history, indent=2, sort_keys=True) + "\n",
            )

            # Tool trace — canonical jsonl
            trace_lines = "\n".join(json.dumps(e, sort_keys=True) for e in result.trace_entries)
            zf.writestr("provenance/tool_trace.jsonl", trace_lines + "\n" if trace_lines else "\n")

            # Evidence
            zf.writestr(
                "results/evidence_index.json",
                json.dumps({"entries": evidence_entries}, indent=2, sort_keys=True) + "\n",
            )

            # Geometry — only if exported successfully
            if has_geometry:
                step_bytes = Path(result.exported_step_path).read_bytes()
                zf.writestr("geometry/source.step", step_bytes)
                zf.writestr("geometry/normalized.step", step_bytes)

    # 5. Semantic post-processing & final status
    modeling_summary = _build_modeling_summary(result, geometry_available=has_geometry)

    if result.overall_status == "success" and has_geometry and run_postprocess:
        postprocess_summary = _run_semantic_postprocess(out_path, strict=postprocess_strict)
    else:
        postprocess_summary: dict[str, Any] = {
            "requested": run_postprocess,
            "topology_status": "skipped",
            "aag_status": "skipped",
            "feature_graph_status": "skipped",
            "errors": [],
            "warnings": [],
        }
        if result.overall_status != "success":
            postprocess_summary["warnings"].append(
                "Semantic post-processing skipped because modeling did not succeed."
            )
        elif not has_geometry:
            postprocess_summary["warnings"].append(
                "Semantic post-processing skipped because no geometry was exported."
            )
        elif not run_postprocess:
            postprocess_summary["warnings"].append(
                "Semantic post-processing skipped because run_postprocess=False."
            )

    extra_status = {**modeling_summary, "semantic_postprocess": postprocess_summary}
    update_validation_status_package(out_path, overwrite=True, extra_status=extra_status)

    return out_path
