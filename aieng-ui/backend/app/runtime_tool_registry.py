"""Registration of app-scoped MCP/runtime tool handlers.

Tool implementations are intentionally kept as closures over ``active_settings``
and the shared app context so their behavior and approval semantics stay
unchanged while ``app_factory`` remains a small composition layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .legacy_app_symbols import sync_main_symbols
from .logging_utils import log_exception

LOGGER = logging.getLogger("app.app_factory")


def _split_ccx_cmd(command: str, *, platform: str | None = None) -> list[str]:
    """Split an operator-provided ccx command into subprocess argv."""
    import os
    import shlex

    platform = platform or os.name
    parts = shlex.split(command, posix=platform != "nt")
    if platform == "nt":
        parts = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in {"'", '"'} else part
            for part in parts
        ]
    return parts


def _sync_main_symbols() -> None:
    sync_main_symbols(globals())


def _resolve_ccx_cmd() -> list[str] | None:
    """Resolve the CalculiX (ccx) command, respecting AIENG_CCX_CMD.

    Returns a list of command parts (e.g. ["/usr/bin/ccx"] or
    ["conda", "run", "-n", "calculix-env", "ccx"]) when ccx is available,
    or None when it cannot be found.
    """
    import os
    import shutil

    ccx_env = os.environ.get("AIENG_CCX_CMD")
    if ccx_env:
        try:
            parts = _split_ccx_cmd(ccx_env)
        except ValueError:
            return None
        if parts and shutil.which(parts[0]):
            return parts
        return None
    for candidate in ("ccx", "ccx_linux", "ccx2.21", "ccx_static"):
        path = shutil.which(candidate)
        if path:
            return [path]
    return None


@dataclass(frozen=True)
class RuntimeToolHandlers:
    apply_shape_ir_patch: Any
    derive_topology_optimization_problem: Any
    run_topology_optimization: Any
    writeback_topology_optimization: Any
    run_assembly_topology_optimization: Any


def register_runtime_tools(*, active_settings: Any, app_context: Any) -> RuntimeToolHandlers:
    _sync_main_symbols()
    _delete_project_everywhere = app_context.delete_project_everywhere
    _load_project_feature_parameters = app_context.load_project_feature_parameters

    # ── runtime tool registrations ────────────────────────────────────────────
    # Each closure captures active_settings so tool handlers call existing
    # business-logic functions without duplicating them.

    def _tool_inspect_package(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.inspect_package")
        return package_summary(active_settings, pid)

    def _tool_agent_context(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import agent_context

        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.agent_context")
        return agent_context.build_agent_context(active_settings, str(pid))

    def _tool_refresh_semantics(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.refresh_semantics")
        return validate_aieng_file(active_settings, pid)

    def _tool_generate_preview(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.generate_preview")
        # convert_asset first publishes embedded package previews (GLB/STL), then
        # falls back to STEP conversion when the package has no viewer asset.
        return convert_asset(active_settings, pid)

    def _tool_read_audit_log(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        logs = recent_logs(active_settings, pid) if pid else []
        return {"project_id": pid, "recent_logs": logs}

    def _tool_refresh_cae_summary(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")

        if not package_path and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path = str(pkg)

        if not package_path:
            return {
                "status": "error",
                "code": "missing_cae_summary_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        if not _Path(package_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path}",
            }

        overwrite = bool(inp.get("overwrite", True))
        result = aieng_bridge.refresh_cae_result_summary(
            package_path,
            aieng_root=active_settings.aieng_root,
            overwrite=overwrite,
        )

        if result.get("status") == "ok":
            try:
                _pkg = _Path(package_path)
                _written = [a["path"] for a in result.get("artifacts", [])]
                _evidence = [
                    a["path"] for a in result.get("artifacts", [])
                    if a.get("kind") in ("cae_result_summary", "evidence_index", "field")
                ]
                _append_audit_event_to_package(
                    _pkg,
                    _build_audit_event(
                        tool="postprocess.refresh_cae_summary",
                        event_type="cae_summary_refreshed",
                        status="completed",
                        artifacts_written=_written,
                        evidence_created=_evidence,
                        state_changes={},
                        geometry_revision=None,
                        revalidation_status=None,
                    ),
                )
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to write computed-metrics audit artifact.",
                    subsystem="app_factory.audit.computed_metrics",
                    context={"project_id": project_id},
                )

        return result

    def _tool_generate_computed_metrics(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import computed_metrics as _cm
        from pathlib import Path as _Path

        project_id: str | None = inp.get("project_id")
        input_path: str | None = inp.get("inputPath") or inp.get("input_path")

        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        if not input_path:
            return {"status": "error", "code": "missing_input_path", "message": "inputPath is required."}

        p = _Path(input_path)
        if not p.exists():
            return {"status": "error", "code": "file_not_found", "message": f"Input file not found: {input_path}"}

        text = p.read_text(encoding="utf-8")
        fmt = "csv" if input_path.lower().endswith(".csv") else "json"
        payload: dict[str, Any] = {"format": fmt, "text": text}
        if inp.get("loadCaseId"):
            payload["load_case_id"] = inp["loadCaseId"]
        if inp.get("software"):
            payload["software"] = inp["software"]

        try:
            result = _cm.save_computed_metrics(active_settings, project_id, payload)
        except Exception as exc:
            return {"status": "error", "code": "save_failed", "message": str(exc)}

        return {**result, "status": "ok"}

    def _tool_mcp_check(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for mcp.check")
        return mcp_check(active_settings, pid, inp)

    def _tool_mcp_parse_patch(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        patch_json = inp.get("patch_json")
        if not isinstance(patch_json, dict):
            raise ValueError("patch_json is required for mcp.parse_patch")
        return parse_patch(active_settings, {"patch_json": patch_json})

    def _tool_mcp_prepare_execution(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for mcp.prepare_execution")
        patch_json = inp.get("patch_json")
        if not isinstance(patch_json, dict):
            raise ValueError("patch_json is required for mcp.prepare_execution")
        return prepare_patch_execution(active_settings, pid, inp)

    def _normalize_cae_setup_patches(inp: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        raw_patches = inp.get("patches")
        if raw_patches is not None:
            if isinstance(raw_patches, dict):
                raw_patches = [raw_patches]
            if not isinstance(raw_patches, list):
                return [], "Input field 'patches' must be a list of patch objects."
            patches = list(raw_patches)
        else:
            legacy_patch = inp.get("patch")
            if legacy_patch is None:
                return [], None
            if isinstance(legacy_patch, list):
                patches = list(legacy_patch)
            elif isinstance(legacy_patch, dict):
                if (
                    "path" in legacy_patch
                    or "action_type" in legacy_patch
                    or "operation" in legacy_patch
                ):
                    patches = [dict(legacy_patch)]
                else:
                    patches = []
                    for op_key, op_value in legacy_patch.items():
                        if not isinstance(op_value, dict):
                            return [], (
                                "Legacy input field 'patch' must contain patch objects keyed by "
                                "operation name."
                            )
                        op = dict(op_value)
                        op.setdefault("action_type", str(op_key).split(":", 1)[0])
                        patches.append(op)
            else:
                return [], "Input field 'patch' must be a patch object or list of patch objects."

        normalized: list[dict[str, Any]] = []
        for patch in patches:
            if not isinstance(patch, dict):
                return [], "Each CAE setup patch must be an object."
            op = dict(patch)
            action = op.get("action_type") or op.get("operation")
            if (
                action in {"replace_json", "merge_object", "append_array_item"}
                and "value" not in op
                and "content" in op
            ):
                op["value"] = op.pop("content")
            normalized.append(op)
        return normalized, None

    def _tool_cae_apply_setup_patch(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        # Guard: reject claims_advanced requests
        if inp.get("claims_advanced"):
            return {
                "status": "error",
                "code": "unsupported_operation",
                "message": "claims_advanced=true is not supported in this version.",
            }

        package_path: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")

        if not package_path and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path = str(pkg)

        if not package_path:
            return {
                "status": "error",
                "code": "missing_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        if not _Path(package_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path}",
            }

        patches, patch_error = _normalize_cae_setup_patches(inp)
        if patch_error:
            return {
                "status": "error",
                "code": "invalid_patch_input",
                "message": patch_error,
            }
        if not patches:
            return {
                "status": "error",
                "code": "no_patches",
                "message": "No patches provided.",
            }

        # Validate all patches before applying any
        for i, patch in enumerate(patches):
            path = patch.get("path", "")
            action = patch.get("action_type") or patch.get("operation") or ""
            if not _is_allowed_patch_path(path):
                return {
                    "status": "error",
                    "code": "forbidden_path",
                    "message": (
                        f"Patch {i}: path {path!r} is not in the allowed patch locations. "
                        "Only simulation/cae_imports/, simulation/load_cases/, "
                        "simulation/solver_settings.json, simulation/cae_mapping.json, "
                        "and graph/constraints.json are writable."
                    ),
                }
            if action not in _SUPPORTED_PATCH_OPERATIONS:
                return {
                    "status": "error",
                    "code": "unsupported_operation",
                    "message": (
                        f"Patch {i}: action_type {action!r} is not supported. "
                        f"Supported: {sorted(_SUPPORTED_PATCH_OPERATIONS)}"
                    ),
                }

        try:
            changed_paths, apply_warnings, artifact_diffs = _apply_patches_to_package(
                _Path(package_path), patches
            )
        except ValueError as exc:
            return {"status": "error", "code": "patch_error", "message": str(exc)}
        except Exception as exc:
            return {"status": "error", "code": "patch_error", "message": f"Patch failed: {exc}"}

        refreshed_artifacts: list[dict[str, Any]] = []
        refresh_warnings: list[str] = []

        do_refresh = bool(inp.get("refresh_preprocessing_summary", True))
        if do_refresh:
            try:
                refresh_result = aieng_bridge.refresh_preprocessing_summary(
                    package_path,
                    aieng_root=active_settings.aieng_root,
                    overwrite=True,
                )
                refreshed_artifacts.extend(refresh_result.get("artifacts", []))
            except Exception as exc:
                refresh_warnings.append(
                    f"preprocessing_summary_refresh_failed: {exc}. "
                    "Refresh manually via postprocess.refresh_cae_summary."
                )

        refreshed_paths = [a["path"] for a in refreshed_artifacts]
        stale_artifacts = _compute_stale_artifacts(changed_paths, refreshed_paths)
        all_warnings = apply_warnings + refresh_warnings

        return {
            "status": "ok",
            "changed_artifacts": [
                {"path": p, "kind": "cae_setup_patch", "role": "patched_setup_artifact"}
                for p in changed_paths
            ],
            "refreshed_artifacts": refreshed_artifacts,
            "stale_artifacts": stale_artifacts,
            "artifact_diffs": artifact_diffs,
            "warnings": all_warnings,
        }

    def _tool_cae_extract_solver_results(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        frd_path: str | None = inp.get("frdPath") or inp.get("frd_path")

        if not package_path and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path = str(pkg)

        if not package_path:
            return {
                "status": "error",
                "code": "missing_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        if not frd_path:
            return {
                "status": "error",
                "code": "missing_frd_path",
                "message": "No frdPath provided. Pass the path to the CalculiX .frd result file.",
            }

        if not _Path(package_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path}",
            }

        if not _Path(frd_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"FRD file not found: {frd_path}",
            }

        load_case_id: str = inp.get("loadCaseId") or inp.get("load_case_id") or "load_case_001"
        software: str = inp.get("software") or "CalculiX"
        overwrite: bool = bool(inp.get("overwrite", True))

        try:
            result = aieng_bridge.extract_frd_solver_results(
                package_path,
                frd_path,
                aieng_root=active_settings.aieng_root,
                load_case_id=load_case_id,
                software=software,
                overwrite=overwrite,
            )
        except Exception as exc:
            return {"status": "error", "code": "extraction_error", "message": str(exc)}

        # Optionally refresh the result summary so the UI reflects real numbers
        refresh_warnings: list[str] = []
        if inp.get("refresh_result_summary", True):
            try:
                aieng_bridge.refresh_cae_result_summary(
                    package_path,
                    aieng_root=active_settings.aieng_root,
                    overwrite=True,
                )
            except Exception as exc:
                refresh_warnings.append(
                    f"result_summary_refresh_failed: {exc}. "
                    "Refresh manually via postprocess.refresh_cae_summary."
                )

        if refresh_warnings:
            result.setdefault("warnings", []).extend(refresh_warnings)

        return result

    def _tool_cae_extract_field_regions(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        frd_path: str | None = inp.get("frdPath") or inp.get("frd_path")
        field: str = inp.get("field") or "S"
        metric: str = inp.get("metric") or "von_mises"
        max_clusters: int = int(inp.get("maxClusters") or inp.get("max_clusters") or 3)
        threshold_percentile: float = float(
            inp.get("thresholdPercentile") or inp.get("threshold_percentile") or 90.0
        )
        overwrite: bool = bool(inp.get("overwrite", False))
        refresh_field_summary: bool = bool(inp.get("refreshFieldSummary", inp.get("refresh_field_summary", True)))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        if not frd_path:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "missing_frd_path",
                "message": "No frdPath provided. Pass the path to the CalculiX .frd result file.",
            }

        if not _Path(package_path_str).exists():
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        if not _Path(frd_path).exists():
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "file_not_found",
                "message": f"FRD file not found: {frd_path}",
            }

        try:
            result = aieng_bridge.extract_field_regions(
                package_path_str,
                frd_path,
                aieng_root=active_settings.aieng_root,
                field=field,
                metric=metric,
                max_clusters=max_clusters,
                threshold_percentile=threshold_percentile,
                overwrite=overwrite,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "extraction_error",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        field_summary_status = "not_requested"
        refreshed_artifacts: list[dict[str, Any]] = []
        warnings = list(result.get("warnings", []))
        if refresh_field_summary:
            try:
                summary_result = aieng_bridge.write_field_summary(
                    package_path_str,
                    aieng_root=active_settings.aieng_root,
                    overwrite=True,
                )
                refreshed_artifacts = summary_result.get("artifacts", [])
                field_summary_status = summary_result.get("status", "ok")
                if field_summary_status == "skipped":
                    warnings.append(
                        f"Field summary skipped: {summary_result.get('reason', 'aieng.cae_field_summary unavailable')}"
                    )
            except Exception as exc:
                field_summary_status = "error"
                warnings.append(
                    f"Field regions were extracted, but field summary refresh failed: {type(exc).__name__}: {exc}"
                )

        # Refresh the CAE -> Shape IR result map so hotspots stay tied to nodes.
        cae_result_map_status = "ok"
        try:
            from aieng.converters.cae_result_map import write_cae_result_map
            write_cae_result_map(package_path_str)
        except Exception as exc:  # noqa: BLE001
            cae_result_map_status = "error"
            warnings.append(f"cae_result_map refresh failed: {type(exc).__name__}: {exc}")

        return {
            "ok": True,
            "tool": "cae.extract_field_regions",
            "status": "completed",
            "package_path": package_path_str,
            "out_path": result.get("out_path"),
            "cluster_count": result.get("cluster_count", 0),
            "cae_result_map_refreshed": cae_result_map_status,
            "clusters": result.get("clusters", []),
            "warnings": warnings,
            "artifacts": [
                {
                    "path": result.get("out_path", ""),
                    "kind": "field_regions",
                    "role": "high_magnitude_spatial_clusters",
                }
            ],
            "refreshed_artifacts": refreshed_artifacts,
            "field_summary_status": field_summary_status,
        }

    def _tool_cae_prepare_solver_run(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        import zipfile as _zipfile

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        run_id: str = inp.get("runId") or inp.get("run_id") or "run_001"
        solver: str = inp.get("solver") or "CalculiX"
        load_case_id: str = inp.get("loadCaseId") or inp.get("load_case_id") or "load_case_001"
        input_deck_path_str: str | None = inp.get("inputDeckPath") or inp.get("input_deck_path")
        extract_results: bool = bool(inp.get("extractResults", inp.get("extract_results", True)))
        refresh_summary: bool = bool(inp.get("refreshSummary", inp.get("refresh_summary", True)))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.prepare_solver_run",
                "status": "error",
                "code": "missing_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        package_path = Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.prepare_solver_run",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            with _zipfile.ZipFile(package_path, "r") as zf:
                names = set(zf.namelist())
        except Exception as exc:
            return {
                "ok": False,
                "tool": "cae.prepare_solver_run",
                "status": "error",
                "code": "package_read_error",
                "message": f"Failed to read package: {exc}",
            }

        has_mesh = any(n.startswith("simulation/mesh/") for n in names)
        has_solver_settings = "simulation/solver_settings.json" in names
        has_load_case = f"simulation/load_cases/{load_case_id}.json" in names

        if input_deck_path_str:
            has_input_deck = Path(input_deck_path_str).exists()
        else:
            has_input_deck = f"simulation/runs/{run_id}/solver_input.inp" in names

        # Check ccx availability without executing it
        ccx_available = _resolve_ccx_cmd() is not None

        missing_items: list[str] = []
        if not has_mesh:
            missing_items.append("simulation/mesh/ (no mesh files found in package)")
        if not has_solver_settings:
            missing_items.append("simulation/solver_settings.json")
        if not has_load_case:
            missing_items.append(f"simulation/load_cases/{load_case_id}.json")
        if not has_input_deck:
            deck_hint = f" (or external: {input_deck_path_str})" if input_deck_path_str else ""
            missing_items.append(f"simulation/runs/{run_id}/solver_input.inp{deck_hint}")
        if not ccx_available:
            missing_items.append(
                "CalculiX command unavailable (set AIENG_CCX_CMD or ensure ccx is discoverable on PATH)."
            )

        ready_to_run = len(missing_items) == 0

        run_prefix = f"simulation/runs/{run_id}"
        planned_artifacts: list[dict[str, str]] = [
            {"path": f"{run_prefix}/solver_run.json", "kind": "solver_run_record", "role": "run_metadata"},
            {"path": f"{run_prefix}/solver_log.txt", "kind": "solver_log", "role": "solver_stdout"},
            {"path": f"{run_prefix}/outputs/result.frd", "kind": "frd_result", "role": "primary_result"},
        ]
        if extract_results:
            planned_artifacts.append(
                {"path": "results/computed_metrics.json", "kind": "computed_metrics", "role": "extracted_metrics"}
            )
        if refresh_summary:
            planned_artifacts.extend([
                {"path": "results/result_summary.json", "kind": "result_summary", "role": "postprocessing_summary"},
                {"path": "results/evidence_index.json", "kind": "evidence_index", "role": "evidence_index"},
                {"path": "results/postprocessing_summary.md", "kind": "markdown_report", "role": "human_readable_summary"},
            ])

        warnings: list[str] = [
            "No solver execution was performed.",
            "This is a preflight plan only. Solver execution requires external CalculiX setup.",
        ]
        if not ready_to_run:
            warnings.append(f"Run is not ready: {len(missing_items)} item(s) missing.")

        return {
            "ok": True,
            "tool": "cae.prepare_solver_run",
            "ready_to_run": ready_to_run,
            "solver": solver,
            "run_id": run_id,
            "load_case_id": load_case_id,
            "requires_approval": True,
            "solver_execution_performed": False,
            "preflight": {
                "has_mesh": has_mesh,
                "has_solver_settings": has_solver_settings,
                "has_load_case": has_load_case,
                "has_input_deck": has_input_deck,
                "ccx_available": ccx_available,
                "missing_items": missing_items,
            },
            "planned_artifacts": planned_artifacts,
            "warnings": warnings,
        }

    def _tool_cae_generate_solver_input(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        run_id: str = inp.get("runId") or inp.get("run_id") or "run_001"
        overwrite: bool = bool(inp.get("overwrite", False))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.generate_solver_input(
                package_path,
                aieng_root=active_settings.aieng_root,
                run_id=run_id,
                overwrite=overwrite,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "missing_setup",
                "message": str(exc),
                "missing_items": getattr(exc, "missing_items", []),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "generation_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "cae.generate_solver_input",
            "status": "completed",
            "package_path": str(package_path),
            "out_path": result.get("out_path"),
            "warnings": result.get("warnings", []),
            "artifacts": [
                {
                    "path": result.get("out_path", ""),
                    "kind": "solver_input_deck",
                    "role": "calculix_linear_static_input",
                }
            ],
        }

    def _tool_cae_run_solver(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        import time as _time
        import subprocess as _subprocess
        import tempfile as _tempfile
        import zipfile as _zipfile
        from pathlib import Path as _Path
        from . import aieng_bridge

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        run_id: str = inp.get("runId") or inp.get("run_id") or "run_001"
        solver: str = inp.get("solver") or "CalculiX"
        load_case_id: str = inp.get("loadCaseId") or inp.get("load_case_id") or "load_case_001"
        input_deck_path_str: str | None = inp.get("inputDeckPath") or inp.get("input_deck_path")
        extract_results: bool = bool(inp.get("extractResults", inp.get("extract_results", True)))
        refresh_summary: bool = bool(inp.get("refreshSummary", inp.get("refresh_summary", True)))
        overwrite: bool = bool(inp.get("overwrite", True))
        timeout_seconds: int = int(inp.get("timeout_seconds", inp.get("timeoutSeconds", 120)))
        auto_import_evidence: bool = bool(inp.get("autoImportEvidence", inp.get("auto_import_evidence", True)))

        # Resolve package path
        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
                "solver_execution_performed": False,
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
                "solver_execution_performed": False,
            }

        # Validate input_deck_path
        if not input_deck_path_str:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "missing_input_deck",
                "message": "No input_deck_path provided. Pass the path to the CalculiX .inp file inside the package.",
                "solver_execution_performed": False,
            }

        # Reject absolute paths and path traversal
        normalized = input_deck_path_str.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "forbidden_path",
                "message": "input_deck_path must be a relative path inside the package and must not contain '..' or start with a separator.",
                "solver_execution_performed": False,
            }

        if not input_deck_path_str.lower().endswith(".inp"):
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "invalid_input_deck",
                "message": "input_deck_path must end with .inp",
                "solver_execution_performed": False,
            }

        # Verify input deck exists in package
        try:
            with _zipfile.ZipFile(package_path, "r") as zf:
                names = set(zf.namelist())
                if input_deck_path_str not in names:
                    return {
                        "ok": False,
                        "tool": "cae.run_solver",
                        "status": "error",
                        "code": "input_deck_not_found",
                        "message": f"Input deck not found in package: {input_deck_path_str}",
                        "solver_execution_performed": False,
                    }
                inp_data = zf.read(input_deck_path_str)
        except Exception as exc:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "package_read_error",
                "message": f"Failed to read package: {exc}",
                "solver_execution_performed": False,
            }

        # Locate ccx (respects AIENG_CCX_CMD for cross-env launches)
        ccx_parts = _resolve_ccx_cmd()
        if not ccx_parts:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "solver_not_found",
                "message": (
                    "CalculiX command unavailable; set a valid AIENG_CCX_CMD "
                    "or ensure ccx is discoverable on PATH."
                ),
                "solver_execution_performed": False,
            }

        # Run solver in a temp directory
        started_at = datetime.now(timezone.utc).isoformat()
        start_ts = _time.monotonic()
        temp_dir = _tempfile.mkdtemp(prefix="aieng_solver_")
        work_dir = _Path(temp_dir)
        changed_artifacts: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        frd_path: _Path | None = None
        return_code: int | None = None
        stdout = ""
        stderr = ""

        try:
            stem = _Path(input_deck_path_str).stem
            local_inp = work_dir / f"{stem}.inp"
            local_inp.write_bytes(inp_data)

            try:
                proc = _subprocess.run(
                    ccx_parts + [stem],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    shell=False,
                )
                return_code = proc.returncode
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
            except _subprocess.TimeoutExpired as exc:
                return_code = -1
                stdout = exc.stdout.decode() if exc.stdout else ""
                stderr = exc.stderr.decode() if exc.stderr else ""
                errors.append(f"Solver timed out after {timeout_seconds} seconds.")
                warnings.append("Solver execution was terminated due to timeout.")
            except Exception as exc:
                return {
                    "ok": False,
                    "tool": "cae.run_solver",
                    "status": "error",
                    "code": "solver_subprocess_error",
                    "message": f"Failed to run solver subprocess: {exc}",
                    "solver_execution_performed": False,
                }

            finished_at = datetime.now(timezone.utc).isoformat()
            duration_seconds = round(_time.monotonic() - start_ts, 3)

            # Write solver log
            log_path = work_dir / "solver_log.txt"
            log_path.write_text(
                f"=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}\n=== RETURN CODE ===\n{return_code}\n",
                encoding="utf-8",
            )

            solved = return_code == 0
            # Conservative: don't claim convergence without reliable evidence
            converged = None

            # Locate generated FRD in temp working directory
            result_frd = work_dir / f"{stem}.frd"
            if result_frd.exists():
                frd_path = result_frd

            # Build solver_run.json
            solver_run = {
                "run_id": run_id,
                "solver": solver,
                "state": "completed" if solved else "failed",
                "solved": solved,
                "converged": converged,
                "return_code": return_code,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_seconds": duration_seconds,
                "input_files": [input_deck_path_str],
                "output_files": [],
                "log_file": f"simulation/runs/{run_id}/solver_log.txt",
                "warnings": warnings,
                "errors": errors,
            }
            if frd_path:
                solver_run["output_files"].append(f"simulation/runs/{run_id}/outputs/result.frd")

            # Write artifacts back into package
            run_prefix = f"simulation/runs/{run_id}"

            def _write_safe(artifact_path: str, source: _Path) -> None:
                try:
                    art = write_artifact_to_package(
                        package_path, artifact_path, source, overwrite=overwrite
                    )
                    changed_artifacts.append(art)
                except FileExistsError:
                    warnings.append(f"{artifact_path} already exists and overwrite=False")
                except Exception as exc:
                    warnings.append(f"Failed to write {artifact_path}: {exc}")

            _write_safe(f"{run_prefix}/solver_input.inp", local_inp)
            _write_safe(f"{run_prefix}/solver_log.txt", log_path)

            run_json_path = work_dir / "solver_run.json"
            run_json_path.write_text(json.dumps(solver_run, indent=2), encoding="utf-8")
            _write_safe(f"{run_prefix}/solver_run.json", run_json_path)

            if frd_path:
                _write_safe(f"{run_prefix}/outputs/result.frd", frd_path)

            # Extract FRD results if requested
            extracted_metrics: dict[str, Any] | None = None
            if extract_results and frd_path:
                try:
                    ext_result = aieng_bridge.extract_frd_solver_results(
                        str(package_path),
                        str(frd_path),
                        aieng_root=active_settings.aieng_root,
                        load_case_id=load_case_id,
                        software=solver,
                        overwrite=overwrite,
                    )
                    extracted_metrics = ext_result.get("metrics")
                    changed_artifacts.extend(ext_result.get("artifacts", []))
                except Exception as exc:
                    warnings.append(f"FRD extraction failed: {exc}")

            # Auto-import solver evidence (.dat) if solver succeeded and file exists
            auto_import_result: dict[str, Any] | None = None
            if auto_import_evidence and solved:
                dat_path = work_dir / f"{stem}.dat"
                if dat_path.exists():
                    # Ensure evidence scaffold exists before importing
                    try:
                        with _zipfile.ZipFile(package_path, "r") as zf:
                            has_scaffold = "results/evidence_index.json" in zf.namelist()
                    except Exception:
                        log_exception(
                            LOGGER,
                            "Failed to probe existing solver evidence scaffold in package.",
                            subsystem="app_factory.cae_solver.scaffold_probe",
                            context={"project_id": project_id, "run_id": run_id},
                        )
                        has_scaffold = False
                    if not has_scaffold:
                        try:
                            aieng_bridge.write_evidence_scaffold(
                                package_path,
                                aieng_root=active_settings.aieng_root,
                                overwrite=False,
                                include_claim_map=True,
                            )
                        except Exception as exc:
                            warnings.append(f"Auto-scaffold for evidence import failed: {exc}")
                    try:
                        import_result = aieng_bridge.import_solver_evidence(
                            package_path,
                            dat_path,
                            aieng_root=active_settings.aieng_root,
                            result_format="calculix_dat",
                            producer_tool="calculix",
                            claim_support=["claim_solver_result_001"],
                        )
                        auto_import_result = {
                            "status": "ok",
                            "evidence_id": import_result.get("evidence_id"),
                            "artifacts": import_result.get("artifacts", []),
                        }
                        changed_artifacts.extend(import_result.get("artifacts", []))
                    except Exception as exc:
                        warnings.append(f"Auto-import of solver evidence failed: {exc}")
                        auto_import_result = {"status": "error", "message": str(exc)}

            # Refresh summaries if requested
            refreshed_summaries: list[str] = []
            if refresh_summary:
                try:
                    aieng_bridge.refresh_cae_result_summary(
                        str(package_path),
                        aieng_root=active_settings.aieng_root,
                        overwrite=True,
                    )
                    refreshed_summaries.append("result_summary")
                except Exception as exc:
                    warnings.append(f"CAE result summary refresh failed: {exc}")

                try:
                    aieng_bridge.refresh_preprocessing_summary(
                        str(package_path),
                        aieng_root=active_settings.aieng_root,
                        overwrite=True,
                    )
                    refreshed_summaries.append("preprocessing_summary")
                except Exception as exc:
                    warnings.append(f"Preprocessing summary refresh failed: {exc}")

            # Clear geometry-edit stale state when solver run succeeds — fresh
            # results now exist for the current geometry.
            if solved:
                try:
                    _record_solver_validation_in_package(package_path, run_id=run_id)
                except Exception as _exc:
                    warnings.append(f"Could not update revalidation status: {_exc}")

                try:
                    _rev = _read_revalidation_status(package_path) or {}
                    _solver_artifacts = list(changed_artifacts) + [REVALIDATION_STATUS_PATH]
                    _evidence = [
                        a for a in changed_artifacts
                        if a.endswith("solver_run.json") or a.endswith(".frd")
                    ]
                    _append_audit_event_to_package(
                        package_path,
                        _build_audit_event(
                            tool="cae.run_solver",
                            event_type="solver_run_completed",
                            status="completed",
                            artifacts_written=_solver_artifacts,
                            evidence_created=_evidence,
                            state_changes={
                                "requires_revalidation": False,
                                "last_validated_geometry_revision": _rev.get(
                                    "last_validated_geometry_revision"
                                ),
                                "current_geometry_revision": _rev.get("current_geometry_revision"),
                            },
                            geometry_revision=_rev.get("current_geometry_revision"),
                            revalidation_status="fresh",
                        ),
                    )
                except Exception as _exc:
                    warnings.append(f"Could not write audit event: {_exc}")

            result: dict[str, Any] = {
                "ok": True,
                "tool": "cae.run_solver",
                "status": "completed" if solved else "failed",
                "solver_execution_performed": True,
                "return_code": return_code,
                "changed_artifacts": changed_artifacts,
                "warnings": warnings,
                "errors": errors,
            }
            if extracted_metrics is not None:
                result["extracted_metrics"] = extracted_metrics
            if refreshed_summaries:
                result["refreshed_summaries"] = refreshed_summaries
            if auto_import_result is not None:
                result["auto_import"] = auto_import_result
            return result

        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to clean temporary solver run directory.",
                    subsystem="app_factory.cae_solver.cleanup_tempdir",
                    context={"run_id": run_id},
                )

    def _tool_cae_write_mesh_handoff(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))
        handoff_id: str = inp.get("handoffId") or inp.get("handoff_id") or "mesh_handoff_001"

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.write_mesh_handoff(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
                handoff_id=handoff_id,
            )
        except FileNotFoundError as exc:
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "topology_missing",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "handoff_write_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "cae.write_mesh_handoff",
            "status": "completed",
            "package_path": str(package_path),
            "handoff_id": handoff_id,
            "artifacts": result.get("artifacts", []),
        }

    def _tool_aieng_validate(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.validate",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.validate",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.validate_package(
                package_path,
                aieng_root=active_settings.aieng_root,
            )
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.validate",
                "status": "error",
                "code": "validation_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.validate",
            "status": "completed",
            "package_path": str(package_path),
            "validation_ok": result.get("ok"),
            "messages": result.get("messages", []),
            "counts": result.get("counts", {}),
        }

    def _tool_aieng_convert(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        source_path_str: str | None = inp.get("sourcePath") or inp.get("source_path")
        out_path_str: str | None = inp.get("outPath") or inp.get("out_path")
        project_id: str | None = inp.get("project_id")
        converter_id: str | None = inp.get("converterId") or inp.get("converter_id")
        overwrite: bool = bool(inp.get("overwrite", False))
        runtime_mode: str = inp.get("runtimeMode") or inp.get("runtime_mode") or "auto"
        model_id: str | None = inp.get("modelId") or inp.get("model_id")
        execute_shape_ir: bool = bool(inp.get("executeShapeIr", inp.get("execute_shape_ir", True)))

        # Resolve source_path from project.source_step if not provided
        if not source_path_str and project_id:
            proj = get_project(active_settings, project_id)
            src = resolve_project_path(active_settings, project_id, proj.get("source_step"))
            if src is not None and src.exists():
                source_path_str = str(src)

        if not source_path_str:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "missing_source_path",
                "message": "No source path provided and no project source_step could be resolved.",
            }

        source_path = _Path(source_path_str)
        if not source_path.exists():
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "source_not_found",
                "message": f"Source file not found: {source_path_str}",
            }

        # Resolve out_path: default to project packages dir
        if not out_path_str and project_id:
            proj_name = _Path(source_path_str).stem
            out_path_str = str(project_dir(active_settings, project_id) / "packages" / f"{proj_name}.aieng")

        if not out_path_str:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "missing_out_path",
                "message": "No output path provided and could not infer one from project.",
            }

        out_path = _Path(out_path_str)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = aieng_bridge.convert_source_to_package(
                source_path,
                out_path,
                aieng_root=active_settings.aieng_root,
                model_id=model_id,
                converter_id=converter_id,
                overwrite=overwrite,
                runtime_mode=runtime_mode,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "conversion_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        shape_ir_execution: dict[str, Any] | None = None

        class _ShapeIRRepresentationHandled(Exception):
            """Internal: a non-build123d representation was already handled (run or
            skipped) — break out before the default build123d execution path,
            without falling into the generic error handler."""

        if result.get("source_type") == "shape_ir" and execute_shape_ir:
            try:
                import zipfile as _zipfile
                from . import cad_generation as _cad_generation
                from aieng.converters.shape_ir import (
                    representation_runtime as _shape_ir_runtime,
                    shape_ir_representation as _shape_ir_rep,
                )

                with _zipfile.ZipFile(out_path, "r") as _archive:
                    names = set(_archive.namelist())
                    _ir_payload = (
                        json.loads(_archive.read("geometry/shape_ir.json").decode("utf-8"))
                        if "geometry/shape_ir.json" in names else {}
                    )
                    representation = _shape_ir_rep(_ir_payload) if isinstance(_ir_payload, dict) else "brep_build123d"
                    runtime = _shape_ir_runtime(representation)
                    # build123d-runtime representations (brep_build123d, nurbs_brep)
                    # all execute the generated geometry/source.py through the
                    # build123d runner — exact STEP/B-Rep with per-face topology.
                    if runtime == "build123d":
                        if "geometry/source.py" not in names:
                            raise RuntimeError("Shape IR package did not contain geometry/source.py")
                        source_code = _archive.read("geometry/source.py").decode("utf-8")

                # Mesh backends (SDF / Manifold): run the field/CSG, write mesh-only
                # artifacts, and reconcile provenance (geometry_kind=mesh). Shared path.
                _mesh_backends = {
                    "implicit_sdf": ("geometry/sdf_source.py", _cad_generation._execute_sdf_code, "sdf"),
                    "manifold_mesh": ("geometry/manifold_source.py", _cad_generation._execute_manifold_code, "manifold"),
                }
                if representation in _mesh_backends:
                    src_member, runner_fn, backend_name = _mesh_backends[representation]
                    if src_member not in names:
                        raise RuntimeError(f"{representation} package did not contain {src_member}")
                    with _zipfile.ZipFile(out_path, "r") as _archive:
                        mesh_code = _archive.read(src_member).decode("utf-8")
                    stl_bytes, glb_bytes, mesh_topo = runner_fn(mesh_code, timeout=int(inp.get("timeout") or 120))
                    mesh_fg = _cad_generation._mesh_feature_graph(mesh_topo)
                    _cad_generation._write_mesh_artifacts(out_path, stl_bytes, glb_bytes, mesh_topo, mesh_fg)
                    _cad_generation.reconcile_shape_ir_provenance(
                        out_path, mesh_topo, mesh_fg,
                        representation=representation, backend=backend_name, geometry_kind="mesh",
                    )
                    mesh_named = _cad_generation._named_parts_from_feature_graph(mesh_fg)
                    shape_ir_execution = {
                        "status": "ok",
                        "representation": representation,
                        "backend": backend_name,
                        "geometry_kind": "mesh",
                        "written_artifacts": [
                            "geometry/preview.stl",
                            "geometry/topology_map.json",
                            "graph/feature_graph.json",
                        ] + (["geometry/preview.glb"] if glb_bytes else []),
                        "named_parts": mesh_named,
                        "part_count": len(mesh_named),
                        "geometry_report": _cad_generation._compute_geometry_report(mesh_topo),
                    }
                    raise _ShapeIRRepresentationHandled()

                if runtime != "build123d":
                    # Representations whose runner isn't wired yet (future targets).
                    shape_ir_execution = {
                        "status": "skipped",
                        "code": "runtime_not_wired",
                        "representation": representation,
                        "message": (
                            f"Shape IR uses the '{representation}' representation; its compiled "
                            "source was emitted but no matching runner is wired yet, so no executed "
                            "geometry/preview was produced."
                        ),
                    }
                    raise _ShapeIRRepresentationHandled()

                step_bytes, stl_bytes, glb_bytes, topo = _cad_generation._execute_build123d_code(
                    source_code,
                    timeout=int(inp.get("timeout") or 60),
                )
                mesh_meta = topo.pop("_mesh_meta", None) if isinstance(topo, dict) else None
                feature_graph = _cad_generation._topology_to_feature_graph(
                    topo,
                    source_code=source_code,
                    model_kind=str(inp.get("model_kind") or "organic"),
                )
                _cad_generation._write_cad_artifacts(
                    out_path,
                    step_bytes=step_bytes,
                    stl_bytes=stl_bytes,
                    topology_map=topo,
                    feature_graph=feature_graph,
                    generated_code=source_code,
                    glb_bytes=glb_bytes,
                )
                # The projected topology/feature were just replaced with REAL
                # executed geometry; refresh object_registry + stamp provenance so
                # they don't dangle against the converter's pre-execution slug ids.
                _cad_generation.reconcile_shape_ir_provenance(
                    out_path, topo, feature_graph,
                    representation=representation, backend="build123d", geometry_kind="brep",
                )
                named_parts = _cad_generation._named_parts_from_feature_graph(feature_graph)
                shape_ir_execution = {
                    "status": "ok",
                    "representation": representation,
                    "written_artifacts": [
                        "geometry/generated.step",
                        "geometry/preview.stl",
                        "geometry/topology_map.json",
                        "graph/feature_graph.json",
                        "geometry/source.py",
                    ] + (["geometry/preview.glb"] if glb_bytes else []),
                    "named_parts": named_parts,
                    "part_count": len(named_parts),
                    "geometry_report": _cad_generation._compute_geometry_report(topo),
                    "mesh_meta_available": mesh_meta is not None,
                }
            except _ShapeIRRepresentationHandled:
                pass  # shape_ir_execution already holds the ok/skipped status
            except Exception as exc:  # noqa: BLE001 - return structured tool error, don't throw
                shape_ir_execution = {
                    "status": "error",
                    "code": "shape_ir_execution_failed",
                    "message": f"{type(exc).__name__}: {exc}",
                }

        # Unified Shape IR verification: audit the (now final) package and write
        # diagnostics/shape_ir_verification.json. Best-effort — never fails convert.
        shape_ir_verification: dict[str, Any] | None = None
        shape_ir_object_registry: dict[str, Any] | None = None
        if result.get("source_type") == "shape_ir":
            try:
                from aieng.converters.shape_ir_verification import write_shape_ir_verification
                shape_ir_verification = write_shape_ir_verification(out_path)
            except Exception as exc:  # noqa: BLE001
                shape_ir_verification = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
            # Object registry (depends on verification): links Shape IR nodes to
            # topology/mesh/viewer entities + editable parameters.
            try:
                from aieng.converters.shape_ir_object_registry import write_shape_ir_object_registry
                shape_ir_object_registry = write_shape_ir_object_registry(out_path)
            except Exception as exc:  # noqa: BLE001
                shape_ir_object_registry = {"error": f"{type(exc).__name__}: {exc}"}

        preview_result: dict[str, Any] | None = None

        # Update project aieng_file if project_id is available
        if project_id:
            try:
                proj = get_project(active_settings, project_id)
                rel_out = project_relpath(active_settings, project_id, out_path)
                proj["aieng_file"] = rel_out
                proj["status"] = "converted"
                save_project(active_settings, proj)
                if shape_ir_execution and shape_ir_execution.get("status") == "ok":
                    preview_result = convert_asset(active_settings, project_id)
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to persist converted project metadata; keeping tool result.",
                    subsystem="app_factory.convert_asset.project_update",
                    context={"project_id": project_id},
                )

        return {
            "ok": True,
            "tool": "aieng.convert",
            "status": "completed",
            "out_path": result.get("out_path"),
            "source_type": result.get("source_type"),
            "converter_id": result.get("converter_id"),
            "shape_ir_execution": shape_ir_execution,
            "shape_ir_verification": shape_ir_verification,
            "shape_ir_object_registry": shape_ir_object_registry,
            "preview": preview_result,
        }

    def _tool_aieng_write_completeness_report(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.write_completeness_report(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "write_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.write_completeness_report",
            "status": "completed",
            "package_path": str(package_path),
            "artifacts": result.get("artifacts", []),
        }

    def _tool_aieng_update_validation_status(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))
        extra_status: dict[str, Any] | None = inp.get("extraStatus") or inp.get("extra_status")

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.update_validation_status(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
                extra_status=extra_status,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "update_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.update_validation_status",
            "status": "completed",
            "package_path": str(package_path),
            "artifacts": result.get("artifacts", []),
        }

    def _tool_aieng_write_evidence_scaffold(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.write_evidence_scaffold(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
            )
        except FileExistsError as exc:
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "scaffold_exists",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "scaffold_write_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.write_evidence_scaffold",
            "status": "completed",
            "package_path": str(package_path),
            "claims_advanced": False,
            "artifacts": result.get("artifacts", []),
        }

    def _tool_cae_import_solver_evidence(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path
        import zipfile as _zipfile

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        result_file: str | None = inp.get("resultFile") or inp.get("result_file")
        result_format: str = inp.get("resultFormat") or inp.get("result_format") or "calculix_dat"
        producer_tool: str = inp.get("producerTool") or inp.get("producer_tool") or "calculix"
        claim_support: list[str] = inp.get("claimSupport") or inp.get("claim_support") or ["claim_solver_result_001"]
        verification_status: str = inp.get("verificationStatus") or inp.get("verification_status") or "unverified"
        evidence_id: str | None = inp.get("evidenceId") or inp.get("evidence_id")
        auto_scaffold: bool = bool(inp.get("autoScaffold", inp.get("auto_scaffold", True)))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        if not result_file:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "missing_result_file",
                "message": "No result file provided. Pass resultFile.",
            }

        result_path = _Path(result_file)
        if not result_path.exists():
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "result_file_not_found",
                "message": f"Result file not found: {result_file}",
            }

        # Check if evidence scaffold is present; auto-create if requested
        scaffold_created = False
        if auto_scaffold:
            try:
                with _zipfile.ZipFile(package_path, "r") as zf:
                    has_scaffold = "results/evidence_index.json" in zf.namelist()
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to probe solver evidence scaffold before import.",
                    subsystem="app_factory.import_solver_evidence.scaffold_probe",
                    context={"project_id": project_id, "package_path": package_path},
                )
                has_scaffold = False
            if not has_scaffold:
                try:
                    aieng_bridge.write_evidence_scaffold(
                        package_path,
                        aieng_root=active_settings.aieng_root,
                        overwrite=False,
                        include_claim_map=True,
                    )
                    scaffold_created = True
                except Exception:
                    log_exception(
                        LOGGER,
                        "Failed to create solver evidence scaffold before import.",
                        subsystem="app_factory.import_solver_evidence.scaffold_create",
                        context={"project_id": project_id, "package_path": package_path},
                    )

        try:
            result = aieng_bridge.import_solver_evidence(
                package_path,
                result_path,
                aieng_root=active_settings.aieng_root,
                result_format=result_format,
                producer_tool=producer_tool,
                claim_support=claim_support,
                verification_status=verification_status,
                evidence_id=evidence_id,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "import_validation_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "import_failed",
                "message": str(exc),
            }

        out = {
            "ok": True,
            "tool": "cae.import_solver_evidence",
            "status": "completed",
            "package_path": str(package_path),
            "evidence_id": result.get("evidence_id"),
            "artifacts": result.get("artifacts", []),
            "summary": result.get("summary", {}),
        }
        if scaffold_created:
            out["scaffold_created"] = True
            out.setdefault("warnings", []).append(
                "Evidence scaffold was auto-created because results/evidence_index.json was missing. "
                "No claim status was advanced."
            )
        return out


    from .runtime_tool_schemas import get_schema as _schema

    # ── agent onboarding tools ────────────────────────────────────────────────

    def _tool_aieng_list_projects(_inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """List all .aieng projects the workbench knows about.

        Broken projects (missing or unreadable metadata) are filtered out so the
        agent never receives a project_id that would later return 404.
        """
        projects: list[dict[str, Any]] = []
        for path in active_settings.projects_root.glob("*/metadata.json"):
            metadata = read_json(path, None)
            if metadata is None:
                continue  # unreadable / broken metadata
            if not isinstance(metadata, dict):
                continue
            if not metadata.get("id"):
                continue  # missing project_id — would cause 404 downstream
            projects.append(normalize_project(metadata))
        projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
        return {"projects": projects, "count": len(projects)}

    _rt.register_tool(
        "aieng.list_projects",
        _tool_aieng_list_projects,
        description=(
            "List all projects available in this workbench instance. Returns id, "
            "name, status, last-modified, and (for agent-built geometry) named_parts "
            "+ part_count for each project. Call this first if you don't know which "
            "project_id to use; use aieng.find_projects_by_part to locate a project "
            "by a part label."
        ),
        input_schema=_schema("aieng.list_projects"),
    )

    def _tool_aieng_create_project(_inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Create a new empty project."""
        from .project_io import default_project, save_project

        name = str(_inp.get("name") or "").strip() or "Untitled project"
        project = save_project(active_settings, default_project(name))
        return {
            "id": project["id"],
            "name": project["name"],
            "status": project.get("status", "empty"),
            "created_at": project.get("created_at"),
            "message": f"Project '{project['name']}' created successfully.",
        }

    _rt.register_tool(
        "aieng.create_project",
        _tool_aieng_create_project,
        description=(
            "Create a new empty workbench project. Returns the project's id, name, "
            "and status. Use this when the user wants to start CAD modeling from "
            "scratch and no suitable existing project is available. The returned "
            "id can be passed directly to geometry-mutation tools such as "
            "cad.execute_build123d."
        ),
        input_schema=_schema("aieng.create_project"),
    )

    def _tool_aieng_find_projects_by_part(_inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Find projects whose geometry contains a named part matching the query.

        Scans each project's metadata ``named_parts`` (cheap; populated on every
        agent build); for older projects without that field it falls back to
        reading the package's feature graph. Substring, case-insensitive.
        """
        from .cad_generation import _named_parts_from_package
        from .project_io import resolve_project_path

        query = str(_inp.get("query") or "").strip().lower()
        if not query:
            return {"query": "", "matches": [], "count": 0}
        matches: list[dict[str, Any]] = []
        for path in active_settings.projects_root.glob("*/metadata.json"):
            proj = normalize_project(read_json(path, {}))
            parts = proj.get("named_parts")
            if not isinstance(parts, list):
                parts = []
                pkg_path = resolve_project_path(active_settings, proj["id"], proj.get("aieng_file"))
                if pkg_path and pkg_path.exists():
                    parts = _named_parts_from_package(pkg_path)
            hits = [str(p) for p in parts if query in str(p).lower()]
            if hits:
                matches.append({
                    "id": proj["id"],
                    "name": proj["name"],
                    "status": proj.get("status"),
                    "matched_parts": hits,
                    "part_count": len(parts),
                })
        matches.sort(key=lambda m: (-len(m["matched_parts"]), m["name"]))
        return {"query": query, "matches": matches, "count": len(matches)}

    _rt.register_tool(
        "aieng.find_projects_by_part",
        _tool_aieng_find_projects_by_part,
        description=(
            "Find projects whose geometry contains a named part matching the query "
            "(case-insensitive substring on part labels). Use this to locate a model "
            "by content, e.g. find which project holds the 'optimus' parts."
        ),
        input_schema=_schema("aieng.find_projects_by_part"),
    )

    def _tool_aieng_delete_project(_inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Permanently delete a project: its directory + chat sessions/messages."""
        pid = str(_inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "message": "project_id is required"}
        try:
            result = _delete_project_everywhere(pid)
        except HTTPException:
            return {"status": "error", "code": "not_found", "message": f"project not found: {pid}"}
        return {"status": "ok", **result}

    _rt.register_tool(
        "aieng.delete_project",
        _tool_aieng_delete_project,
        description=(
            "[APPROVAL REQUIRED] Permanently delete a project — its .aieng package, "
            "metadata, viewer assets, and all chat sessions/messages. Irreversible. "
            "Confirm with the user before calling."
        ),
        input_schema=_schema("aieng.delete_project"),
        requires_approval=True,
    )

    def _tool_aieng_apply_shape_ir_patch(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Apply a surgical patch to a project's Shape IR (atomic + validated),
        then recompile through runtime routing. dry_run validates + reports only."""
        import zipfile as _zipfile
        from aieng.converters import shape_ir_patch as _patch
        from . import cad_generation as _cad_generation
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        patch = inp.get("patch") if isinstance(inp.get("patch"), dict) else None
        dry_run = bool(inp.get("dry_run", False))
        if not pid or patch is None:
            return {"status": "error", "code": "bad_input", "message": "project_id and patch are required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            with _zipfile.ZipFile(pkg, "r") as zf:
                if "geometry/shape_ir.json" not in zf.namelist():
                    return {"status": "error", "code": "not_shape_ir",
                            "message": "project has no geometry/shape_ir.json"}
                payload = json.loads(zf.read("geometry/shape_ir.json").decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "read_failed", "message": f"{type(exc).__name__}: {exc}"}

        result = _patch.apply_shape_ir_patch(payload, patch, dry_run=dry_run)
        report = _patch.build_patch_report(patch, result)
        recompile: dict[str, Any] | None = None

        if result["ok"] and not dry_run:
            # Commit the patched Shape IR, then re-run the full pipeline.
            _cad_generation._replace_member(
                pkg, "geometry/shape_ir.json",
                (json.dumps(result["new_payload"], indent=2, sort_keys=True) + "\n").encode(),
            )
            recompile = _cad_generation.recompile_shape_ir_package(pkg, timeout=int(inp.get("timeout") or 120))
            report["recompile"] = recompile
            _patch.write_patch_report(pkg, report)  # persist only when committed
            # Publish the recompiled preview to viewer/model.* so the UI viewer shows
            # the patched geometry (recompile only refreshes the in-package preview, not
            # the on-disk viewer asset the frontend defaults to). Mirrors cad.execute.
            try:
                glb_bytes = stl_bytes = None
                with _zipfile.ZipFile(pkg, "r") as zf:
                    names = zf.namelist()
                    if "geometry/preview.glb" in names:
                        glb_bytes = zf.read("geometry/preview.glb")
                    if "geometry/preview.stl" in names:
                        stl_bytes = zf.read("geometry/preview.stl")
                proj = get_project(active_settings, pid)
                if glb_bytes or stl_bytes:
                    proj["status"] = "viewer_ready_glb" if glb_bytes else "viewer_ready_stl"
                    _cad_generation._publish_preview_to_viewer(active_settings, pid, proj, glb_bytes, stl_bytes)
                proj["updated_at"] = now_iso()
                save_project(active_settings, proj)
            except Exception:
                log_exception(
                    LOGGER,
                    "Failed to persist project metadata after Shape IR patch.",
                    subsystem="app_factory.shape_ir_patch.project_update",
                    context={"project_id": pid},
                )

        return {
            "status": "ok" if result["ok"] else "rejected",
            "dry_run": dry_run,
            "patch_report": report,
            "recompile": recompile,
        }

    _rt.register_tool(
        "aieng.apply_shape_ir_patch",
        _tool_aieng_apply_shape_ir_patch,
        description=(
            "[APPROVAL REQUIRED] Apply a surgical patch to a project's Shape IR "
            "(set_parameter / move_control_point / add_node / remove_node / replace_node / "
            "connect / disconnect / change_representation_backend). Atomic + validated: invalid "
            "patches are rejected without overwriting. On success the package is recompiled through "
            "runtime routing and verification/object-registry are refreshed. Use dry_run to preview."
        ),
        input_schema=_schema("aieng.apply_shape_ir_patch"),
        requires_approval=True,
    )

    def _tool_cae_map_results(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Map CAE results back to topology entities / object_registry / source_ir_node;
        write analysis/cae_result_map.json. Read-only analysis (no solver)."""
        from aieng.converters.cae_result_map import write_cae_result_map
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result_map = write_cae_result_map(pkg)
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "map_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": "ok", "tool": "cae.map_results", "cae_result_map": result_map}

    def _tool_opt_derive_problem_from_cae(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Derive a 2D topology-optimization problem (grid + supports + loads + design
        space) from a project's CAE setup + geometry. Read-only (no mutation)."""
        from aieng.converters.topology_optimization import derive_topopt_problem_from_package
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        kw: dict[str, Any] = {"dimension": str(inp.get("dimension") or "2d").lower()}
        for k in ("resolution", "resolution_3d", "max_iters"):
            if inp.get(k) is not None:
                kw[k] = int(inp[k])
        for k in ("volfrac", "penalty", "rmin"):
            if inp.get(k) is not None:
                kw[k] = float(inp[k])
        try:
            problem = derive_topopt_problem_from_package(pkg, **kw)
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "derive_failed", "message": f"{type(exc).__name__}: {exc}"}
        # 3D derivation may honestly decline to guess BCs.
        if problem.get("status") == "needs_user_input":
            return {"status": "needs_user_input", "tool": "opt.derive_problem_from_cae",
                    "problem": problem, "diagnostics": problem.get("diagnostics")}
        return {"status": "ok", "tool": "opt.derive_problem_from_cae", "problem": problem,
                "derivation": problem.get("derivation")}

    def _tool_opt_run_topology_optimization(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Run topology optimization (built-in 2D SIMP) on a project's design space;
        write analysis/topology_optimization.json. No external solver. If auto_derive
        is set (or no problem is given), the problem is derived from the project's CAE
        setup + geometry first."""
        from aieng.converters.topology_optimization import (
            derive_topopt_problem_from_package,
            write_topology_optimization,
        )
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        problem = inp.get("problem") if isinstance(inp.get("problem"), dict) else None
        auto_derive = bool(inp.get("auto_derive")) or problem is None
        dimension = str(inp.get("dimension") or "2d").lower()
        # An explicit 3D optimizer implies 3D derivation.
        if str(inp.get("optimizer") or "").lower() == "simp_3d":
            dimension = "3d"
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        optimizer = str(inp.get("optimizer") or ("simp_3d" if dimension == "3d" else "simp_2d"))
        try:
            if auto_derive:
                derived = derive_topopt_problem_from_package(pkg, dimension=dimension)
                # 3D derivation may honestly decline to guess BCs — surface it, don't solve.
                if derived.get("status") == "needs_user_input":
                    return {"status": "needs_user_input", "tool": "opt.run_topology_optimization",
                            "problem": derived, "diagnostics": derived.get("diagnostics")}
                if isinstance(problem, dict):  # caller overrides (volfrac, grid, ...) win
                    derived.update({k: v for k, v in problem.items() if k != "bcs"})
                    if isinstance(problem.get("bcs"), dict):
                        derived.setdefault("bcs", {}).update(problem["bcs"])
                problem = derived
            result = write_topology_optimization(pkg, problem, optimizer=optimizer)
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "optimization_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": "ok", "tool": "opt.run_topology_optimization", "topology_optimization": result}

    _rt.register_tool(
        "opt.run_topology_optimization",
        _tool_opt_run_topology_optimization,
        description=(
            "Run topology optimization on a project's design space using the built-in "
            "self-contained 2D SIMP (compliance minimization, pure numpy — no external "
            "solver). Writes analysis/topology_optimization.json (optimizer provenance, "
            "objective history, achieved volume fraction, density grid, honest 2D/coarse "
            "limitations). Optimizer is pluggable; optimizer=precomputed accepts a density grid. "
            "Set auto_derive=true (or omit problem) to derive supports/loads/design-space from "
            "the project's CAE setup + geometry instead of a preset."
        ),
        input_schema=_schema("opt.run_topology_optimization"),
    )

    _rt.register_tool(
        "opt.derive_problem_from_cae",
        _tool_opt_derive_problem_from_cae,
        description=(
            "Derive a 2D topology-optimization problem (grid + supports + loads + design "
            "space) from a project's CAE setup (simulation/setup.yaml supports/loads) + "
            "geometry (topology_map faces + design-space bbox). Read-only — returns the "
            "problem + a 'derivation' block (projection plane, frame, source BC links, "
            "warnings). 3D supports/loads are projected onto the plane of the two largest "
            "design-space dimensions; out-of-plane components are dropped (plane-stress). "
            "Inspect this, then pass it to opt.run_topology_optimization."
        ),
        input_schema=_schema("opt.derive_problem_from_cae"),
    )

    def _tool_opt_writeback_to_shape_ir(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Author a topology-optimization result back into the project's Shape IR
        (one density_voxels node) and recompile through runtime routing — so the
        optimized body meshes/views and gets verification + object_registry."""
        from aieng.converters.topology_optimization import write_shape_ir_from_topology_optimization
        from . import cad_generation as _cad_generation
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}

        # Detect a 3D result up front — it drives both the representation and method
        # defaults (3D is a mesh preview, not a B-Rep / contour body).
        _dim3 = False
        try:
            import zipfile as _zfd
            with _zfd.ZipFile(pkg, "r") as _z:
                if "analysis/topology_optimization.json" in _z.namelist():
                    _topo = json.loads(_z.read("analysis/topology_optimization.json"))
                    _dim3 = _topo.get("dimension") == "3d" or "density_grid_3d" in (_topo.get("result") or {})
        except Exception:
            log_exception(
                LOGGER,
                "Failed to inspect topology optimization artifact; defaulting to 2D writeback mode.",
                subsystem="app_factory.topology_writeback.dimension_detect",
                context={"project_id": pid},
            )
            _dim3 = False
        # Default to B-Rep for 2D (analytic faces an engineer picks / exports to STEP;
        # manifold_mesh is the robust fallback, auto-used if the B-Rep build fails).
        # 3D results default to manifold_mesh — a B-Rep Compound of hundreds of voxel
        # boxes is heavy and beside the point; 3D is an explicitly meshed preview.
        representation = str(inp.get("representation") or ("manifold_mesh" if _dim3 else "brep_build123d"))
        # The optimized body is placed in the design space's derivation frame;
        # cell_size/thickness/origin are honored only if the caller overrides.
        cs = inp.get("cell_size")
        cell_size = (float(cs[0]), float(cs[1] if len(cs) > 1 else cs[0])) if cs else None
        thickness = inp.get("thickness")
        org = inp.get("origin")
        origin = (float(org[0]), float(org[1]), float(org[2])) if org else None
        # 2D default: contour; 3D default: surface (smooth marching-cubes proxy).
        method = str(inp.get("method") or ("surface" if _dim3 else "contour")).lower()
        boundary = str(inp.get("boundary") or "spline").lower()
        timeout = int(inp.get("timeout") or 120)

        def _writeback(rep: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
            pay = write_shape_ir_from_topology_optimization(
                pkg, representation=rep, cell_size=cell_size,
                thickness=(float(thickness) if thickness is not None else None),
                origin=origin,
                node_id=(str(inp["node_id"]) if inp.get("node_id") else None),
                use_frame=bool(inp.get("use_frame", True)),
                method=method, boundary=boundary,
            )
            rc = _cad_generation.recompile_shape_ir_package(pkg, timeout=timeout)
            return pay, rc

        try:
            payload, recompile = _writeback(representation)
            # Safety net: if a non-mesh representation didn't actually execute, retry
            # once as a watertight mesh so the writeback still yields a viewable body.
            if representation != "manifold_mesh" and not (recompile or {}).get("executed", False):
                payload, recompile = _writeback("manifold_mesh")
                payload.setdefault("provenance", {})["representation_fallback"] = (
                    f"{representation} did not execute; fell back to manifold_mesh")
        except FileNotFoundError as exc:
            return {"status": "error", "code": "no_topology_optimization", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            # B-Rep build raised — fall back to mesh once before giving up.
            if representation != "manifold_mesh":
                try:
                    payload, recompile = _writeback("manifold_mesh")
                    payload.setdefault("provenance", {})["representation_fallback"] = (
                        f"{representation} failed ({type(exc).__name__}); fell back to manifold_mesh")
                except Exception as exc2:  # noqa: BLE001
                    return {"status": "error", "code": "writeback_failed",
                            "message": f"{type(exc2).__name__}: {exc2}"}
            else:
                return {"status": "error", "code": "writeback_failed", "message": f"{type(exc).__name__}: {exc}"}

        # Publish the recompiled preview to viewer/model.* + set web_asset so the UI
        # viewer actually shows the optimized body (the frontend's default viewer URL
        # resolves to /assets/projects/{id}/{web_asset}; recompile only refreshes the
        # in-package preview, not the on-disk viewer asset). Mirrors cad.execute_build123d.
        try:
            import zipfile as _zf
            glb_bytes = stl_bytes = None
            with _zf.ZipFile(pkg, "r") as zf:
                names = zf.namelist()
                if "geometry/preview.glb" in names:
                    glb_bytes = zf.read("geometry/preview.glb")
                if "geometry/preview.stl" in names:
                    stl_bytes = zf.read("geometry/preview.stl")
            proj = get_project(active_settings, pid)
            if glb_bytes or stl_bytes:
                proj["status"] = "viewer_ready_glb" if glb_bytes else "viewer_ready_stl"
                _cad_generation._publish_preview_to_viewer(active_settings, pid, proj, glb_bytes, stl_bytes)
            proj["updated_at"] = now_iso()
            save_project(active_settings, proj)
        except Exception:
            log_exception(
                LOGGER,
                "Failed to persist project metadata after topology optimization writeback.",
                subsystem="app_factory.topology_writeback.project_update",
                context={"project_id": pid},
            )

        return {
            "status": "ok",
            "tool": "opt.writeback_to_shape_ir",
            "shape_ir": payload,
            "recompile": recompile,
        }

    _rt.register_tool(
        "opt.writeback_to_shape_ir",
        _tool_opt_writeback_to_shape_ir,
        description=(
            "Author the project's topology-optimization result (analysis/"
            "topology_optimization.json) back into geometry/shape_ir.json as one "
            "density_voxels node, then recompile through runtime routing. The optimized "
            "density field becomes re-compilable, viewable geometry (default representation "
            "manifold_mesh -> watertight voxel mesh; brep_build123d also supported) with "
            "topology + verification + object_registry, linked to its design_space_node. "
            "Run opt.run_topology_optimization first."
        ),
        input_schema=_schema("opt.writeback_to_shape_ir"),
    )

    def _tool_opt_run_assembly_topology_optimization(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Explicit assembly-aware topopt execution for one selected design part.
        Uses the assembly topopt setup artifacts and writes selected-part derived
        artifacts only; no package-level geometry overwrite."""
        from aieng.converters.assembly_topopt import run_assembly_topology_optimization
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = run_assembly_topology_optimization(
                pkg,
                optimizer=(str(inp["optimizer"]) if inp.get("optimizer") else None),
                writeback=bool(inp.get("writeback", True)),
                method=(str(inp["method"]) if inp.get("method") else None),
                representation=(str(inp["representation"]) if inp.get("representation") else None),
                boundary=str(inp.get("boundary") or "spline"),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "assembly_topopt_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {
            "status": result.get("status"),
            "tool": "opt.run_assembly_topology_optimization",
            "assembly_topology_optimization": result,
        }

    _rt.register_tool(
        "opt.run_assembly_topology_optimization",
        _tool_opt_run_assembly_topology_optimization,
        description=(
            "Explicitly run assembly-aware topology optimization for one selected design "
            "part. Consumes assembly_topopt_problem + topology_optimization_problem, calls "
            "the existing optimizer, writes assembly diagnostics/provenance and selected-part "
            "derived artifacts, and never overwrites reference/frozen parts or package-level geometry."
        ),
        input_schema=_schema("opt.run_assembly_topology_optimization"),
    )

    def _tool_opt_propose_candidates(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Generate candidate parameter sets from optimization variables.
        Reads analysis/optimization_variables.json (and optionally
        optimization_study.json) from the project's .aieng package, runs
        the requested sampler, and writes candidate patches to
        patches/design_candidates/<cid>.json. Does NOT execute candidates,
        recompile geometry, run CAE, or modify the baseline."""
        from aieng.converters.optimization_sampler import sample_candidates_package
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = sample_candidates_package(
                pkg,
                algorithm=inp.get("algorithm"),
                count=inp.get("count"),
                seed=inp.get("seed"),
                max_candidates=inp.get("max_candidates"),
                overwrite=bool(inp.get("overwrite", False)),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "sampling_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {
            "status": result.get("status", "error"),
            "tool": "opt.propose_candidates",
            "sampler_result": result,
        }

    _rt.register_tool(
        "opt.propose_candidates",
        _tool_opt_propose_candidates,
        description=(
            "Generate candidate parameter sets from optimization variables. "
            "Reads analysis/optimization_variables.json (required) and optionally "
            "analysis/optimization_study.json from the project's .aieng package, "
            "runs the requested sampler (grid / random / latin_hypercube), and "
            "writes candidate patches to patches/design_candidates/<cid>.json "
            "in the format consumed by the candidate executor/evaluator/ranker. "
            "Does NOT execute candidates, recompile geometry, run CAE, or modify "
            "the baseline. The study's candidate_ids are updated to include the "
            "new candidates. Deterministic given a seed."
        ),
        input_schema=_schema("opt.propose_candidates"),
        # Package-mutating but baseline-safe (writes only derived candidate
        # patches). Kept inside the modeling-plan boundary like
        # cad.execute_build123d / opt.writeback_to_shape_ir rather than carrying
        # a per-call approval gate; the hard gate lives at acceptance.
        requires_approval=False,
        read_only=False,
    )

    def _tool_opt_run_candidates(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Execute proposed design-study candidates into derived workspaces.
        Discovers candidates (or runs an explicit candidate_ids list) and runs
        each through the single-shot executor, applying its patch to a DERIVED
        copy of the baseline Shape IR in candidates/<cid>/. Optionally recompiles
        each candidate in a throwaway copy (compile=true, default). Failures are
        recorded per-candidate and the batch continues. Does NOT run CAE, accept
        a candidate, or modify the baseline."""
        from aieng.converters.design_study_batch import run_design_study_batch
        from .cad_generation import make_candidate_recompiler
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        do_compile = bool(inp.get("compile", True))
        recompiler = make_candidate_recompiler(pkg) if do_compile else None
        try:
            result = run_design_study_batch(
                pkg,
                candidate_ids=inp.get("candidate_ids"),
                recompiler=recompiler,
                max_candidates=inp.get("max_candidates"),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "batch_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.run_candidates", "batch_result": result}

    _rt.register_tool(
        "opt.run_candidates",
        _tool_opt_run_candidates,
        description=(
            "Execute proposed design-study candidates into isolated derived "
            "workspaces (candidates/<cid>/). Discovers the candidate set from the "
            "package (optimization_study/variables candidate_ids + any candidate "
            "patches on disk), or runs an explicit candidate_ids list, applying "
            "each patch to a DERIVED copy of the baseline Shape IR. With "
            "compile=true (default) each candidate is recompiled in a throwaway "
            "copy; a failed candidate is recorded cleanly and the batch CONTINUES. "
            "Records each iteration in analysis/design_study_iterations.json. Does "
            "NOT run CAE, accept/promote any candidate, or modify the baseline."
        ),
        input_schema=_schema("opt.run_candidates"),
        requires_approval=False,
        read_only=False,
    )

    def _tool_opt_evaluate_candidates(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Evaluate executed design-study candidates from candidate-local evidence.
        For each candidate, normalizes mass / volume / max_stress / max_deflection /
        min_safety_factor, evaluates declared constraints, and classifies feasibility.
        Missing CAE metrics are recorded honestly as unknown — never fabricated. With
        cae=true, first derives each candidate's CAE setup and normalizes CAE evidence
        (solver stays disabled by default). Does NOT accept/promote a candidate or
        modify the baseline. Feeds opt.rank_candidates."""
        from aieng.converters.design_study_batch import run_design_study_evaluation_batch
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        cae_options: dict[str, Any] = {}
        if inp.get("cae"):
            if inp.get("mode") is not None:
                cae_options["mode"] = inp.get("mode")
            if inp.get("allow_solver_execution") is not None:
                cae_options["allow_solver_execution"] = bool(inp.get("allow_solver_execution"))
        try:
            result = run_design_study_evaluation_batch(
                pkg,
                candidate_ids=inp.get("candidate_ids"),
                cae=bool(inp.get("cae", False)),
                cae_options=cae_options or None,
                max_candidates=inp.get("max_candidates"),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "evaluation_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.evaluate_candidates", "batch_result": result}

    _rt.register_tool(
        "opt.evaluate_candidates",
        _tool_opt_evaluate_candidates,
        description=(
            "Evaluate executed design-study candidates from candidate-local "
            "evidence (candidates/<cid>/). Normalizes mass / volume / max_stress / "
            "max_deflection / min_safety_factor, evaluates declared constraints, and "
            "classifies each candidate feasible / infeasible / unknown. MISSING CAE "
            "metrics are recorded honestly as unknown — never fabricated. With "
            "cae=true, first derives each candidate's CAE setup and normalizes any "
            "CAE evidence (solver execution stays disabled by default). Writes "
            "candidates/<cid>/analysis/evaluation.json. Does NOT accept/promote any "
            "candidate or modify the baseline; feeds opt.rank_candidates."
        ),
        input_schema=_schema("opt.evaluate_candidates"),
        requires_approval=False,
        read_only=False,
    )

    def _tool_opt_rank_candidates(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Rank evaluated design-study candidates (advisory).
        Reads per-candidate evaluations, classifies feasibility, scores against the
        problem objective + constraints, and writes
        analysis/design_study_candidate_ranking.json +
        diagnostics/design_study_scoring_report.json. Selects best_candidate_id only
        when feasible, improving, and high-confidence. Does NOT accept/promote a
        candidate, run CAE, or modify the baseline."""
        from aieng.converters.design_study_ranking import rank_design_study_candidates
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = rank_design_study_candidates(pkg)
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "ranking_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.rank_candidates", "ranking_result": result}

    _rt.register_tool(
        "opt.rank_candidates",
        _tool_opt_rank_candidates,
        description=(
            "Rank evaluated design-study candidates (advisory). Reads per-candidate "
            "evaluations, classifies feasibility (feasible / infeasible / unknown / "
            "failed), scores against the problem objective + constraints, and writes "
            "analysis/design_study_candidate_ranking.json + the scoring report. "
            "best_candidate_id is selected only when a candidate is feasible, improves "
            "the objective, and is high-confidence; otherwise it is null and "
            "safe_to_accept is false. Does NOT accept/promote a candidate, run CAE, or "
            "modify the baseline."
        ),
        input_schema=_schema("opt.rank_candidates"),
        requires_approval=False,
        read_only=False,
    )

    def _tool_opt_explain_recommendation(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Explain the candidate ranking as an advisory, reason-coded recommendation.
        Reads the existing ranking + scoring report and composes a human-readable
        recommendation (why the top candidate, citing metrics + objective delta; why
        none, when applicable; caveats for missing metrics / low confidence), written
        to analysis/optimization_recommendation.json. Advisory only — does NOT accept a
        candidate, run CAE, or modify the baseline. Run opt.rank_candidates first."""
        from aieng.converters.optimization_recommendation import explain_recommendation
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = explain_recommendation(pkg)
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "explain_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.explain_recommendation", "recommendation": result}

    _rt.register_tool(
        "opt.explain_recommendation",
        _tool_opt_explain_recommendation,
        description=(
            "Explain a candidate ranking as an advisory, reason-coded recommendation. "
            "Reads analysis/design_study_candidate_ranking.json (run opt.rank_candidates "
            "first) and composes a human-readable recommendation: why the top candidate "
            "is recommended (objective delta + metrics), or why none is, plus explicit "
            "caveats for missing CAE metrics / low confidence. Writes "
            "analysis/optimization_recommendation.json. Advisory only and human-approval "
            "gated for acceptance — does NOT accept/promote a candidate, run CAE, or "
            "modify the baseline."
        ),
        input_schema=_schema("opt.explain_recommendation"),
        requires_approval=False,
        read_only=False,
    )

    def _tool_opt_accept_candidate(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Accept ONE ranked design-study candidate into a derived accepted workspace.
        Copies the candidate's derived artifacts into accepted/<cid>/ and writes
        analysis/design_study_acceptance.json. The candidate must be eligible
        (feasible, and best_candidate_id + safe_to_accept unless override_unsafe).
        Does NOT overwrite baseline geometry, does NOT auto-promote, and does NOT
        claim production approval. APPROVAL REQUIRED."""
        from aieng.converters.design_study_acceptance import accept_design_study_candidate
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        cid = str(inp.get("candidate_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        if not cid:
            return {"status": "error", "code": "bad_input", "message": "candidate_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = accept_design_study_candidate(
                pkg,
                cid,
                accepted_by=inp.get("accepted_by", "agent"),
                reasoning=inp.get("reasoning"),
                override_unsafe=bool(inp.get("override_unsafe", False)),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "acceptance_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.accept_candidate", "acceptance_result": result}

    _rt.register_tool(
        "opt.accept_candidate",
        _tool_opt_accept_candidate,
        description=(
            "[APPROVAL REQUIRED] Accept ONE ranked design-study candidate into a "
            "derived accepted workspace (accepted/<cid>/). The candidate must be "
            "eligible: feasible (not failed/infeasible/unknown), and the "
            "best_candidate_id with safe_to_accept=true — otherwise override_unsafe "
            "must be set explicitly. Copies the candidate's derived patch / Shape IR / "
            "evaluation into accepted/<cid>/ and writes "
            "analysis/design_study_acceptance.json + the acceptance report. Does NOT "
            "overwrite baseline geometry, does NOT auto-promote into the baseline, and "
            "does NOT claim production certification — acceptance is an advisory, "
            "human-approved derived design artifact only."
        ),
        input_schema=_schema("opt.accept_candidate"),
        requires_approval=True,
    )

    def _tool_opt_write_report(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Aggregate the optimization study into a single summary report.
        Reads existing package artifacts (problem, variables/objectives/constraints,
        candidates + metrics, ranking, failed candidates, recommendation, acceptance,
        decision log) and writes diagnostics/optimization_report.json. Read-only with
        respect to engineering state: does NOT execute/evaluate/rank/accept candidates,
        run CAE, or modify the baseline. The report is reconstructable from artifacts."""
        from aieng.converters.optimization_report import build_optimization_report
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = build_optimization_report(pkg)
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "report_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.write_report", "report_result": result}

    _rt.register_tool(
        "opt.write_report",
        _tool_opt_write_report,
        description=(
            "Aggregate the optimization study into a single summary report. Reads the "
            "existing package artifacts (problem definition, variables / objectives / "
            "constraints, all candidates + metrics, ranking, failed candidates, the "
            "advisory recommendation, acceptance state, and decision log) and writes "
            "diagnostics/optimization_report.json. Read-only with respect to "
            "engineering state — does NOT execute / evaluate / rank / accept "
            "candidates, run CAE, or modify the baseline. The report is "
            "reconstructable purely from on-disk artifacts."
        ),
        input_schema=_schema("opt.write_report"),
        requires_approval=False,
        read_only=False,
    )

    def _tool_opt_propose_next(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Propose the next batch of candidates by local refinement around the incumbent.
        Reads the ranking incumbent + optimization variables and samples within a
        trust region that shrinks each iteration, or runs an SLSQP local step. Falls
        back to whole-domain LHS when there is no feasible incumbent. Writes candidate
        patches in the existing format. Deterministic given a seed. Does NOT
        run/evaluate/accept candidates, run CAE, or modify the baseline."""
        from aieng.converters.optimization_proposer import propose_next_candidates
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = propose_next_candidates(
                pkg,
                count=int(inp.get("count", 4)),
                shrink=float(inp.get("shrink", 0.5)),
                seed=int(inp.get("seed", 0)),
                algorithm=str(inp.get("algorithm", "trust_region")),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "propose_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.propose_next", "propose_result": result}

    _rt.register_tool(
        "opt.propose_next",
        _tool_opt_propose_next,
        description=(
            "Propose the next batch of design-study candidates by trust-region local "
            "refinement or SLSQP local step around the current ranking incumbent. Falls "
            "back to whole-domain Latin hypercube sampling when there is no feasible "
            "incumbent. Writes candidate patches to patches/design_candidates/<cid>.json "
            "in the format the executor consumes. Deterministic given a seed. Does NOT "
            "run/evaluate/accept candidates, run CAE, or modify the baseline — pair with "
            "opt.run_candidates + opt.evaluate_candidates + opt.rank_candidates + "
            "opt.check_convergence."
        ),
        input_schema=_schema("opt.propose_next"),
        requires_approval=False,
        read_only=False,
    )

    def _tool_opt_check_convergence(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Record the current iteration's incumbent and return a convergence verdict.
        Snapshots the ranking incumbent into analysis/optimization_iterations.json and
        evaluates the deterministic stopping criteria (objective-delta stagnation,
        budget, no-feasible-progress, consecutive failures). Advisory only — tells the
        agent whether to stop; never accepts a candidate, runs CAE, or modifies the
        baseline. Run opt.rank_candidates first."""
        from aieng.converters.optimization_convergence import record_iteration_and_check
        from .project_io import get_project, resolve_project_path

        pid = str(inp.get("project_id") or "").strip()
        if not pid:
            return {"status": "error", "code": "bad_input", "message": "project_id is required"}
        project = get_project(active_settings, pid)
        pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
        if pkg is None or not pkg.exists():
            return {"status": "error", "code": "no_package", "message": ".aieng package not found"}
        try:
            result = record_iteration_and_check(
                pkg,
                evaluations_total=inp.get("evaluations_total"),
                failures_this_round=int(inp.get("failures_this_round", 0)),
                had_success=bool(inp.get("had_success", True)),
                proposer_exhausted=bool(inp.get("proposer_exhausted", False)),
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "code": "convergence_failed", "message": f"{type(exc).__name__}: {exc}"}
        return {"status": result.get("status", "error"), "tool": "opt.check_convergence", "convergence_result": result}

    _rt.register_tool(
        "opt.check_convergence",
        _tool_opt_check_convergence,
        description=(
            "Record the current iteration's incumbent into "
            "analysis/optimization_iterations.json and return a deterministic, advisory "
            "convergence verdict (continue / converged / stop_budget / stop_no_feasible "
            "/ stop_failures / stop_proposer_exhausted). The objective-delta check is "
            "direction-aware (reads the objective sense). Advisory only — it tells the "
            "agent whether to stop; it never accepts a candidate, runs CAE, or modifies "
            "the baseline. Acceptance stays the only hard gate (opt.accept_candidate)."
        ),
        input_schema=_schema("opt.check_convergence"),
        requires_approval=False,
        read_only=False,
    )

    _rt.register_tool(
        "cae.map_results",
        _tool_cae_map_results,
        description=(
            "Map CAE results (stress/displacement clusters + scalar extrema) back to "
            "topology entities, object_registry objects, and source_ir_node where "
            "resolvable. Writes analysis/cae_result_map.json; reports unmapped regions "
            "honestly. Read-only analysis (no solver/mesher)."
        ),
        input_schema=_schema("cae.map_results"),
    )

    def _tool_aieng_agent_readme(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Return compact onboarding by default, with a full-guide compatibility mode."""
        from . import agent_guides

        if str(inp.get("detail") or "quickstart").lower() == "full":
            result = agent_guides.full_result()
        else:
            result = agent_guides.quickstart_result()
        # Registry identity so an agent can tell if this long-lived MCP session
        # is serving a stale tool set (#29) — compare against GET /api/health.
        result["registry"] = _rt.registry_identity()
        return result

    _rt.register_tool(
        "aieng.agent_readme",
        _tool_aieng_agent_readme,
        description=(
            "Return compact operational onboarding. Read this once at the start of a session, "
            "then use aieng.guide only for task-specific detail. detail=full preserves access "
            "to the canonical complete AGENTS.md."
        ),
        input_schema=_schema("aieng.agent_readme"),
    )

    def _tool_aieng_guide(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Return one detailed guide topic extracted from canonical AGENTS.md."""
        from . import agent_guides

        return agent_guides.guide_result(str(inp.get("topic") or ""))

    _rt.register_tool(
        "aieng.guide",
        _tool_aieng_guide,
        description=(
            "Return task-specific detail extracted from the canonical AGENTS.md without "
            "loading the full guide. Topics include cad, cae, pointers, tools, workflows, "
            "package, fallback, frontend, approvals, operators, and full."
        ),
        input_schema=_schema("aieng.guide"),
    )

    _rt.register_tool(
        "aieng.inspect_package",
        _tool_inspect_package,
        description=(
            "Inspect a .aieng package and return the full project semantic summary "
            "(geometry, CAE setup, results, verdict, design targets). "
            "Call this first when starting work on a project to understand its current state."
        ),
        input_schema=_schema("aieng.inspect_package"),
    )
    _rt.register_tool(
        "aieng.agent_context",
        _tool_agent_context,
        description=(
            "Return the compact agent-facing CAD/CAE context: geometry with @face/@feature pointers, "
            "stale-artifact warnings (EDIT IMPACT), CAE setup summary, results, design targets, "
            "and suggested next steps. "
            "Call this before every project-level action — it gives you the pointer IDs needed "
            "to construct valid cad.* and cae.* tool calls."
        ),
        input_schema=_schema("aieng.agent_context"),
    )
    _rt.register_tool(
        "aieng.refresh_semantics",
        _tool_refresh_semantics,
        description=(
            "Re-validate the package and refresh semantic state (face labels, feature graph, "
            "stale-artifact flags). Call this after any geometry edit to clear EDIT IMPACT warnings "
            "before re-running the CAE pipeline."
        ),
        input_schema=_schema("aieng.refresh_semantics"),
    )
    _rt.register_tool(
        "aieng.generate_preview",
        _tool_generate_preview,
        description=(
            "Regenerate the 3-D web preview asset (GLB preferred, STL fallback) from the current STEP file. "
            "Call this after cad.execute_build123d to update the viewer in the React UI."
        ),
        input_schema=_schema("aieng.generate_preview"),
    )
    _rt.register_tool(
        "aieng.read_audit_log",
        _tool_read_audit_log,
        description="Return the most recent audit log entries for this project",
        input_schema=_schema("aieng.read_audit_log"),
    )
    _rt.register_tool(
        "aieng.write_completeness_report",
        _tool_aieng_write_completeness_report,
        description=(
            "Write a completeness/missingness report (validation/completeness_report.json) into a .aieng package. "
            "Assesses 19+ categories: geometry, topology, features, constraints, simulation setup, evidence, etc."
        ),
        input_schema=_schema("aieng.write_completeness_report"),
    )
    _rt.register_tool(
        "aieng.update_validation_status",
        _tool_aieng_update_validation_status,
        description=(
            "Update validation status (validation/status.yaml) inside a .aieng package. "
            "Records geometry, topology, feature, solver/mesh, and CAE import status with explicit claim policy."
        ),
        input_schema=_schema("aieng.update_validation_status"),
    )
    _rt.register_tool(
        "aieng.write_evidence_scaffold",
        _tool_aieng_write_evidence_scaffold,
        description=(
            "Write results/evidence_index.json scaffold into a .aieng package. "
            "Required before importing external solver or mesh evidence; does not create or advance claim maps."
        ),
    )
    _rt.register_tool(
        "aieng.validate",
        _tool_aieng_validate,
        description=(
            "Validate a .aieng package against AIENG schemas and rules. "
            "Returns PASS/WARN/FAIL messages and an overall validation_ok boolean."
        ),
        input_schema=_schema("aieng.validate"),
    )
    _rt.register_tool(
        "aieng.convert",
        _tool_aieng_convert,
        description=(
            "Convert a CAD/Shape source file (.step/.stp/.FCStd/.shape.json/.shape_ir.json) "
            "to a .aieng package. Shape IR sources also generate build123d source.py and, "
            "by default, execute it to publish STEP/STL/GLB viewer artifacts. "
            "Automatically updates project aieng_file on success."
        ),
        input_schema=_schema("aieng.convert"),
    )
    _rt.register_tool(
        "postprocess.generate_computed_metrics",
        _tool_generate_computed_metrics,
        description=(
            "Import computed metrics from a CSV or JSON file (inputPath) into a .aieng package. "
            "Writes results/computed_metrics.json back into the package."
        ),
        input_schema=_schema("postprocess.generate_computed_metrics"),
    )
    _rt.register_tool(
        "postprocess.refresh_cae_summary",
        _tool_refresh_cae_summary,
        description="Regenerate CAE result summary, evidence index, and markdown inside the .aieng package",
        input_schema=_schema("postprocess.refresh_cae_summary"),
    )
    _rt.register_tool(
        "mcp.check",
        _tool_mcp_check,
        description="Check MCP guardrails, capability gaps, and operation policy for this project",
    )
    _rt.register_tool(
        "mcp.parse_patch",
        _tool_mcp_parse_patch,
        description="Parse an .aieng patch proposal without executing it",
    )
    _rt.register_tool(
        "mcp.prepare_execution",
        _tool_mcp_prepare_execution,
        description="Dry-run an .aieng patch proposal and return preflight side effects",
    )
    _rt.register_tool(
        "cae.apply_setup_patch",
        _tool_cae_apply_setup_patch,
        description=(
            "Apply a controlled patch to CAE setup artifacts inside a .aieng package. "
            "Accepts a preferred 'patches' array plus legacy 'patch' compatibility. "
            "Supports create_file, replace_json, merge_object, append_array_item. "
            "Writes only to allowed setup paths; rejects results/ and path traversal."
        ),
        input_schema=_schema("cae.apply_setup_patch"),
    )
    _rt.register_tool(
        "cae.extract_solver_results",
        _tool_cae_extract_solver_results,
        description=(
            "Parse a CalculiX FRD result file and write computed_metrics.json "
            "(max displacement, max von Mises stress) into a .aieng package. "
            "Extracts real numerical extrema from per-node field data."
        ),
        input_schema=_schema("cae.extract_solver_results"),
    )
    _rt.register_tool(
        "cae.extract_field_regions",
        _tool_cae_extract_field_regions,
        description=(
            "Extract high-magnitude spatial clusters from a CalculiX FRD result file. "
            "Partitions nodal stress or displacement fields into ≤ N clusters, "
            "reporting centroid, peak magnitude, and node count per cluster. "
            "Writes results/field_regions.json into the .aieng package."
        ),
        input_schema=_schema("cae.extract_field_regions"),
    )
    _rt.register_tool(
        "cae.prepare_solver_run",
        _tool_cae_prepare_solver_run,
        description=(
            "Inspect a .aieng package and return a reviewable solver run preflight plan. "
            "Checks for mesh, solver settings, load case, and input deck presence. "
            "No solver is executed. Call this before cae.run_solver to verify readiness "
            "and surface any missing_items the agent or user must resolve first."
        ),
        input_schema=_schema("cae.prepare_solver_run"),
    )
    _rt.register_tool(
        "cae.generate_solver_input",
        _tool_cae_generate_solver_input,
        description=(
            "Generate a runnable CalculiX solver input deck from existing .aieng setup artifacts. "
            "Preserves mesh from a previously imported source deck and assembles materials, BCs, loads, and step. "
            "Supports linear static only. Refuses with explicit missing_items if mesh or setup is absent."
        ),
        input_schema=_schema("cae.generate_solver_input"),
    )
    _rt.register_tool(
        "cae.run_solver",
        _tool_cae_run_solver,
        requires_approval=True,
        description=(
            "[APPROVAL REQUIRED] Execute an external CalculiX solver run on an existing input deck. "
            "Copies the .inp into a temp directory, runs ccx with a timeout, "
            "captures stdout/stderr, and writes solver_run.json, solver_log.txt, "
            "and result.frd back into the .aieng package. "
            "Always call cae.prepare_solver_run first to verify the input deck is ready. "
            "After completion call cae.extract_solver_results to parse the FRD output."
        ),
        input_schema=_schema("cae.run_solver"),
    )
    _rt.register_tool(
        "cae.write_mesh_handoff",
        _tool_cae_write_mesh_handoff,
        description=(
            "Write a mesh handoff contract (simulation/mesh_handoff_contract.json) into a .aieng package. "
            "Reads topology_map.json and simulation/setup.yaml to produce a structured handoff spec "
            "for external Gmsh execution. Does not run a mesher."
        ),
    )
    _rt.register_tool(
        "cae.import_solver_evidence",
        _tool_cae_import_solver_evidence,
        description=(
            "Import an external solver result file as evidence into a .aieng package. "
            "Scans the result file for known numeric observations (max von Mises, max displacement, etc.) "
            "and appends them to results/evidence_index.json. Does not auto-advance claim status."
        ),
    )

    def _tool_cad_confirm_modeling_plan(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "ok",
            "plan_confirmed": True,
            "project_id": str(inp.get("project_id") or ""),
            "summary": str(inp.get("summary") or ""),
            "steps": list(inp.get("steps") or []),
            "assumptions": list(inp.get("assumptions") or []),
            "scope": str(inp.get("scope") or ""),
            "message": "Modeling plan confirmed in the agent client. Continue within the approved scope.",
        }

    _rt.register_tool(
        "cad.confirm_modeling_plan",
        _tool_cad_confirm_modeling_plan,
        requires_approval=True,
        input_schema=_schema("cad.confirm_modeling_plan"),
        description=(
            "[APPROVAL REQUIRED] Present a proposed CAD modeling plan in the connecting agent's "
            "native confirmation UI. This authorization tool does not write files or execute CAD. "
            "Call it after preparing the plan instead of ending the conversation or asking for a "
            "plain-text reply. If the user approves, it returns immediately and the agent should "
            "continue in the same task with ordinary CAD build/edit tools. If the user denies it, "
            "do not mutate CAD. A materially changed scope requires another plan confirmation."
        ),
    )

    def _tool_cad_plan_build123d_skill(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_skill_planner as _planner

        return _planner.plan_build123d_skill(inp)

    _rt.register_tool(
        "cad.plan_build123d_skill",
        _tool_cad_plan_build123d_skill,
        input_schema=_schema("cad.plan_build123d_skill"),
        description=(
            "Read-only CAD skill planner. Use this before cad.execute_build123d for common "
            "create-new parts — mechanical (flange, mounting plate, L-bracket, enclosure, "
            "bushing) and organic starters (aircraft, vehicle/car, wheel, built from the "
            "fuselage_profile/naca_airfoil/wheel/rounded_box primitives). It interprets the "
            "request, records assumptions, and returns a parameterized build123d execute_input "
            "(UPPER_SNAKE_CASE constants, named parts) for the agent to review and then pass to "
            "cad.execute_build123d after the modeling plan is explicitly confirmed. It does not mutate the "
            "package and does not bypass Autopilot."
        ),
    )

    def _record_cad_snapshot(result: dict[str, Any], project_id: Any, tool_name: str) -> None:
        # Best-effort undo timeline: snapshot the package after a successful CAD
        # mutation so cad.restore_snapshot can roll back. Never affects the tool.
        if isinstance(result, dict) and result.get("status") == "ok" and project_id:
            from . import snapshots as _snap

            _snap.record_snapshot(active_settings, str(project_id), tool_name)

    def _tool_cad_execute_build123d(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        result = _cg.execute_build123d_code(active_settings, project_id, inp)
        _record_cad_snapshot(result, project_id, "cad.execute_build123d")
        return result

    _rt.register_tool(
        "cad.execute_build123d",
        _tool_cad_execute_build123d,
        read_only=False,
        destructive=False,
        input_schema=_schema("cad.execute_build123d"),
        description=(
            "Execute caller-supplied build123d Python code under an explicitly approved modeling plan. "
            "The agent writes the full build123d script and this tool runs it in a sandboxed subprocess — "
            "no LLM API key needed. "
            "Code contract: bind the final model to a variable named `result`; omit all export calls "
            "(the runner adds export_step/export_stl/export_gltf automatically). "
            "Name parts by setting `.label` on shapes and combining with `Compound(children=[...])` — "
            "labels become named parts in topology_map/feature_graph you can reference later. "
            "Color parts by setting `.color = Color(r, g, b)` (RGB 0..1) — colors render in both "
            "the agent thumbnail AND the GLB the UI viewer displays. "
            "The runner also accepts legacy `Compound([...])` and preserves child labels. "
            "Use mode='append' to build incrementally: the previous model is exposed as `previous_result` "
            "and your code adds to it (still reassigning `result`). "
            "Returns a 2x2 contact-sheet image (front/side/top/iso views) so you can visually verify "
            "alignment from multiple angles — inspect all four views, alignment problems hide in iso. "
            "Also returns named_parts (all named parts now in the model), parts_added (what this step "
            "introduced), mode, and used_base — so you get text-side feedback even if the image isn't rendered. "
            "For iterative loops, pass response_detail='compact' to return a one-line geometry summary "
            "and suppress the thumbnail unless thumbnail=true. Identical source re-runs may return cache_hit=true "
            "without re-running build123d. "
            "Writes source.py, generated.step, preview.stl/.glb, topology_map.json, and feature_graph.json "
            "into the .aieng package; sets project status to viewer_ready_glb."
        ),
    )

    def _tool_cad_get_source(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _cg.read_cad_source(active_settings, project_id)

    _rt.register_tool(
        "cad.get_source",
        _tool_cad_get_source,
        input_schema=_schema("cad.get_source"),
        description=(
            "Read-only: return the project's accumulated build123d source code plus a "
            "state summary {source, named_parts, has_base}. Call this before cad.execute_build123d "
            "to decide replace vs append, see which named parts already exist, and avoid "
            "re-adding prior logic. has_base=true means append mode is available."
        ),
    )

    def _tool_cad_list_editable_parameters(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from .agent_autopilot.parameter_binding import summarize_parameter_index

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        # Reuse the same package read the /modify slot binding uses (single source).
        index = _load_project_feature_parameters(str(project_id))
        if index is None:
            return {
                "status": "ok",
                "project_id": project_id,
                "parameters": [],
                "summary": {"total": 0, "by_scope": {"local": 0, "global": 0, "unscoped": 0}},
                "message": (
                    "No editable-parameter index available — the project has no feature "
                    "graph yet. Build CAD (cad.execute_build123d) with dimensions declared "
                    "as UPPER_SNAKE_CASE constants to make them editable."
                ),
            }
        # Drop the internal search_tokens; keep the user/agent-facing fields.
        parameters = [{k: v for k, v in entry.items() if k != "search_tokens"} for entry in index]
        summary = summarize_parameter_index(index)
        message = (
            f"{summary['total']} editable parameter(s): "
            f"{summary['by_scope']['local']} local, {summary['by_scope']['global']} global "
            f"(shared — edits ripple), {summary['by_scope']['unscoped']} unscoped."
            if summary["total"]
            else (
                "No editable parameters found. Declare dimensions as UPPER_SNAKE_CASE "
                "constants in the build123d source so cad.edit_parameter can target them."
            )
        )
        return {
            "status": "ok",
            "project_id": project_id,
            "parameters": parameters,
            "summary": summary,
            "message": message,
        }

    _rt.register_tool(
        "cad.list_editable_parameters",
        _tool_cad_list_editable_parameters,
        input_schema=_schema("cad.list_editable_parameters"),
        description=(
            "Read-only: list the CAD parameters that can be edited fast and deterministically "
            "via cad.edit_parameter (the 'point' half of point-and-shoot editing). Reads the "
            "project's feature graph and returns, per parameter, its featureId / parameterName / "
            "editable constant (cad_parameter_name) / current value / min-max range, plus a "
            "`scope`: 'local' (one named part — the safe local edit), 'global' (a shared "
            "constant — editing ripples across parts) or 'unscoped'. Use this to answer 'what "
            "can I change here?' and to pick a precise cad.edit_parameter target before editing. "
            "Does not modify the package and is never approval-gated."
        ),
    )

    def _tool_cad_critique(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _cg.critique(active_settings, str(project_id), inp)

    _rt.register_tool(
        "cad.critique",
        _tool_cad_critique,
        input_schema=_schema("cad.critique"),
        description=(
            "Run a deterministic engineering critique of the project geometry. Walks the "
            "feature graph + topology bounding boxes and checks them against manufacturing "
            "rules derived from aieng/schemas/constraints.schema.json: min wall thickness "
            "(3mm CNC default), standard hole sizes, floating-component detection, missing "
            "mounting interfaces on plate-like parts. Returns structured findings (severity, "
            "category, rule, affected feature, observation, suggested fix) plus a "
            "fail_first_objections list of the top blocking issues. Call after "
            "cad.execute_build123d for engineering parts (brackets, housings, fixtures) "
            "to catch manufacturability problems before user review or FEA setup. "
            "Read-only — does not modify the package."
        ),
    )

    def _tool_cad_design_review(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _cg.design_review(active_settings, str(project_id), inp)

    _rt.register_tool(
        "cad.design_review",
        _tool_cad_design_review,
        input_schema=_schema("cad.design_review"),
        description=(
            "Read-only self-review that synthesizes the deterministic critique, structural "
            "geometry signals, and editable parameters into ONE prioritized, actionable list "
            "so you can self-correct before presenting a result — not just fix what the user "
            "points out. On top of cad.critique it adds the left/right symmetry checks critique "
            "lacks (broken / missing mirror pairs from the geometry report) and, for each "
            "fixable finding, binds the concrete cad.edit_parameter target (featureId / "
            "parameterName / current value / allowed range) you would edit. Returns a merged "
            "verdict, a severity-ranked `actions` list (findings with a fast parameter fix), and "
            "a recommendation. Changes NOTHING — applying a fix still goes through the "
            "approved modeling-plan cad.edit_parameter / cad.execute_build123d path. "
            "response_detail='compact' returns actions + summary only; 'full' (default) also "
            "returns every finding. Call after building/editing an engineering part."
        ),
    )

    def _tool_cad_set_reference_image(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _cg.set_reference_image(active_settings, str(project_id), inp)

    _rt.register_tool(
        "cad.set_reference_image",
        _tool_cad_set_reference_image,
        read_only=False,
        destructive=False,
        input_schema=_schema("cad.set_reference_image"),
        description=(
            "Attach a reference image (real-world photo, drawing, or render) to a project so "
            "subsequent cad.execute_build123d thumbnails include it in a right-hand column for "
            "side-by-side comparison. Pass image_url (HTTP/HTTPS) or image_path (local file). "
            "The image is downscaled to 800x800 max and stored as geometry/reference.png in the "
            ".aieng package — set once, used by every future build. Use this when the user names "
            "a real product/character/vehicle and supplies a picture, or when you want the agent "
            "to calibrate proportions against an actual reference instead of memory."
        ),
    )

    def _tool_cad_search_reference_image(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _cg.search_reference_image(active_settings, str(project_id), inp)

    _rt.register_tool(
        "cad.search_reference_image",
        _tool_cad_search_reference_image,
        read_only=False,
        destructive=False,
        input_schema=_schema("cad.search_reference_image"),
        description=(
            "Search Wikimedia Commons for a reference image matching a free-text query "
            "(e.g. 'Boeing 747 side view') and attach the best raster match to the project "
            "as its reference image — a convenience wrapper around cad.set_reference_image "
            "for when the user names a real product/character/vehicle but supplies no picture. "
            "Returns the matched page_url so the source and its license can be verified. "
            "Degrades gracefully: status='no_results' means proceed without a reference. "
            "Like cad.set_reference_image, the image is stored as geometry/reference.png and "
            "every future cad.execute_build123d thumbnail tiles it for side-by-side calibration."
        ),
    )

    def _tool_cad_get_named_part_bbox(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        part_name = inp.get("part_name")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        if not part_name:
            return {"status": "error", "code": "missing_part_name", "message": "part_name is required."}
        return _cg.get_named_part_bbox(active_settings, str(project_id), str(part_name))

    _rt.register_tool(
        "cad.get_named_part_bbox",
        _tool_cad_get_named_part_bbox,
        input_schema=_schema("cad.get_named_part_bbox"),
        description=(
            "Read-only: look up a named part by its exact topology_map label and return "
            "its bounding_box plus derived center point. Useful for grounded follow-up "
            "instructions like moving or resizing one named component."
        ),
    )

    def _tool_cad_refine(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        if not str(inp.get("feedback") or "").strip():
            return {"status": "error", "code": "missing_feedback", "message": "feedback is required."}
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {
                "status": "error",
                "message": "ANTHROPIC_API_KEY not configured; cad.refine requires LLM access",
            }
        try:
            return _cg.refine_cad_generation(active_settings, str(project_id), dict(inp))
        except HTTPException as exc:
            return {"status": "error", "message": str(exc.detail)}
        except Exception as exc:
            return {"status": "error", "message": f"{type(exc).__name__}: {exc}"}

    _rt.register_tool(
        "cad.refine",
        _tool_cad_refine,
        read_only=False,
        destructive=False,
        input_schema=_schema("cad.refine"),
        description=(
            "Refine the existing build123d model within an explicitly approved modeling plan. "
            "Reads geometry/source.py, asks Claude to edit the code, re-executes it, and writes updated "
            "geometry/topology/preview artifacts back into the .aieng package."
        ),
    )

    def _tool_cad_edit_parameter(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg
        result = _cg.edit_build123d_parameter(
            settings=active_settings,
            project_id=str(inp.get("project_id") or ""),
            feature_id=str(inp.get("featureId") or ""),
            parameter_name=str(inp.get("parameterName") or ""),
            new_value=inp.get("newValue"),
            timeout=int(inp.get("timeout", 120)),
            response_detail=str(inp.get("response_detail") or "full"),
            thumbnail=inp.get("thumbnail") if isinstance(inp.get("thumbnail"), bool) else None,
        )
        _record_cad_snapshot(result, inp.get("project_id"), "cad.edit_parameter")
        return result

    _rt.register_tool(
        "cad.edit_parameter",
        _tool_cad_edit_parameter,
        read_only=False,
        destructive=False,
        input_schema=_schema("cad.edit_parameter"),
        description=(
            "Apply a parametric edit to a CAD model feature. "
            "The encompassing modeling plan must already be explicitly approved. "
            "Performs a fast deterministic text replacement in geometry/source.py "
            "(no LLM round-trip) and re-executes build123d so the change is immediate. "
            "The feature graph must carry editable parameters (UPPER_SNAKE_CASE constants)."
        ),
    )

    def _tool_cad_remove_part(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg
        result = _cg.remove_build123d_part(
            settings=active_settings,
            project_id=str(inp.get("project_id") or ""),
            label=str(inp.get("label") or ""),
            timeout=int(inp.get("timeout", 120)),
            response_detail=str(inp.get("response_detail") or "full"),
            thumbnail=inp.get("thumbnail") if isinstance(inp.get("thumbnail"), bool) else None,
        )
        _record_cad_snapshot(result, inp.get("project_id"), "cad.remove_part")
        return result

    _rt.register_tool(
        "cad.remove_part",
        _tool_cad_remove_part,
        read_only=False,
        destructive=False,
        input_schema=_schema("cad.remove_part"),
        description=(
            "Remove a named part from the model by its build123d label. "
            "Appends a filter step to geometry/source.py (keeping the script "
            "self-consistent) and re-executes — no LLM. Returns a regression_diff "
            "confirming only that part was dropped. The encompassing modeling plan must already be approved."
        ),
    )

    def _tool_cad_replace_part(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg
        result = _cg.replace_build123d_part(
            settings=active_settings,
            project_id=str(inp.get("project_id") or ""),
            label=str(inp.get("label") or ""),
            code=str(inp.get("code") or ""),
            timeout=int(inp.get("timeout", 120)),
            response_detail=str(inp.get("response_detail") or "full"),
            thumbnail=inp.get("thumbnail") if isinstance(inp.get("thumbnail"), bool) else None,
        )
        _record_cad_snapshot(result, inp.get("project_id"), "cad.replace_part")
        return result

    _rt.register_tool(
        "cad.replace_part",
        _tool_cad_replace_part,
        read_only=False,
        destructive=False,
        input_schema=_schema("cad.replace_part"),
        description=(
            "Replace a named part by its build123d label with caller-supplied "
            "build123d code (the code must reassign `result` to the new part and "
            "set result.label). Drops the old part, combines the new one in, and "
            "re-executes — no LLM. Lets the agent refine one part without "
            "resubmitting the whole model. Returns a regression_diff. The encompassing modeling plan must already be approved."
        ),
    )

    def _tool_cad_list_snapshots(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import snapshots as _snap

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        limit = inp.get("limit")
        return _snap.list_snapshots(active_settings, str(project_id), int(limit) if limit else 20)

    _rt.register_tool(
        "cad.list_snapshots",
        _tool_cad_list_snapshots,
        input_schema=_schema("cad.list_snapshots"),
        description=(
            "Read-only: list the recent CAD snapshots (undo timeline). A snapshot is "
            "recorded automatically after every successful cad.execute_build123d / "
            "edit_parameter / replace_part / remove_part. Returns tiny metadata only "
            "(snapshot_id, created_at, tool_name, part_count, named_parts) — never "
            "package bytes. Pair with cad.restore_snapshot to roll back."
        ),
    )

    def _tool_cad_restore_snapshot(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import snapshots as _snap

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _snap.restore_snapshot(active_settings, str(project_id), str(inp.get("snapshot_id") or ""))

    _rt.register_tool(
        "cad.restore_snapshot",
        _tool_cad_restore_snapshot,
        requires_approval=True,
        input_schema=_schema("cad.restore_snapshot"),
        description=(
            "[APPROVAL REQUIRED] Roll the project back to an earlier CAD snapshot by "
            "snapshot_id (from cad.list_snapshots). Replaces the current .aieng package "
            "with the snapshot and republishes the viewer preview, clearing stale-artifact "
            "flags. Use to undo an unwanted edit. Irreversible from the agent's side "
            "(the current state is not auto-snapshotted before restore), so confirm first."
        ),
    )

    from . import runtime_tools
    runtime_tools.register_engineering_template_tools(_rt, active_settings)

    def _tool_inspect_mcp_capabilities(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        desired = str(inp.get("desired_outcome") or inp.get("message") or "").strip().lower()
        caps = agent_workbench.list_capabilities(active_settings)
        if desired:
            tokens = [part for part in re.split(r"\W+", desired) if part]
            caps = [
                cap for cap in caps
                if any(
                    token in str(cap.get("name") or "").lower()
                    or token in str(cap.get("purpose") or "").lower()
                    or token in str(cap.get("category") or "").lower()
                    for token in tokens
                )
            ] or caps
        return {
            "status": "success",
            "operation": "aieng_inspect_capabilities",
            "desired_outcome": inp.get("desired_outcome") or "",
            "capabilities": caps[:80],
            "registered_runtime_tool_count": len(_rt.registered_tool_names()),
            "claim_policy": {
                "claims_advanced": False,
                "requires_explicit_update_claim": True,
            },
        }

    # ── materials tools ─────────────────────────────────────────────────────────

    def _tool_list_materials(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import materials_bridge as _mb
        return _mb.list_materials(
            category=str(inp.get("category") or "").strip() or None,
            query=str(inp.get("query") or "").strip() or None,
        )

    _rt.register_tool(
        "list_materials",
        _tool_list_materials,
        description="List all available engineering materials with properties. Optional filter by category or search query.",
        input_schema=_schema("list_materials"),
    )

    def _tool_get_material_details(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import materials_bridge as _mb
        return _mb.get_material_details(str(inp.get("material_name") or "").strip())

    _rt.register_tool(
        "get_material_details",
        _tool_get_material_details,
        description="Return full properties for a specific material including E, nu, density, yield strength, ultimate strength, thermal expansion.",
        input_schema=_schema("get_material_details"),
    )

    def _tool_compare_materials(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import materials_bridge as _mb
        raw = inp.get("material_names")
        names = list(raw) if isinstance(raw, (list, tuple)) else []
        return _mb.compare_materials(names)

    _rt.register_tool(
        "compare_materials",
        _tool_compare_materials,
        description="Compare properties of two or more materials side by side with normalized scores.",
        input_schema=_schema("compare_materials"),
    )

    # ── standard parts tools ────────────────────────────────────────────────────

    def _tool_list_standard_parts(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import standards_bridge as _sb
        return _sb.list_standard_parts(
            category=str(inp.get("category") or "").strip() or None,
        )

    _rt.register_tool(
        "list_standard_parts",
        _tool_list_standard_parts,
        description="List available standard part categories and types (fasteners, bearings, shafts, profiles, holes).",
        input_schema=_schema("list_standard_parts"),
    )

    def _tool_get_standard_part_specs(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import standards_bridge as _sb
        return _sb.get_standard_part_specs(
            part_type=str(inp.get("part_type") or "").strip(),
            preset_name=str(inp.get("preset_name") or "").strip() or None,
        )

    _rt.register_tool(
        "get_standard_part_specs",
        _tool_get_standard_part_specs,
        description="Return Shape IR spec and available presets for a standard part type.",
        input_schema=_schema("get_standard_part_specs"),
    )

    def _tool_insert_standard_part(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import standards_bridge as _sb
        return _sb.insert_standard_part(
            active_settings=active_settings,
            project_id=str(inp.get("project_id") or "").strip() or None,
            package_path=str(inp.get("package_path") or "").strip() or None,
            part_type=str(inp.get("part_type") or "").strip(),
            parameters=inp.get("parameters") if isinstance(inp.get("parameters"), dict) else {},
            position=inp.get("position") if isinstance(inp.get("position"), list) else None,
            orientation=inp.get("orientation") if isinstance(inp.get("orientation"), list) else None,
            part_name=str(inp.get("part_name") or "").strip() or None,
            preset_name=str(inp.get("preset_name") or "").strip() or None,
        )

    _rt.register_tool(
        "insert_standard_part",
        _tool_insert_standard_part,
        requires_approval=True,
        read_only=False,
        destructive=False,
        description="[APPROVAL REQUIRED] Insert a standard part (fastener, bearing, profile, etc.) into the current project as Shape IR. Recompiles the package on success.",
        input_schema=_schema("insert_standard_part"),
    )

    def _tool_set_part_material(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import standards_bridge as _sb
        return _sb.set_part_material(
            active_settings=active_settings,
            project_id=str(inp.get("project_id") or "").strip() or None,
            package_path=str(inp.get("package_path") or "").strip() or None,
            part_name=str(inp.get("part_name") or "").strip(),
            material_name=str(inp.get("material_name") or "").strip(),
            override_properties=inp.get("override_properties") if isinstance(inp.get("override_properties"), dict) else None,
        )

    _rt.register_tool(
        "set_part_material",
        _tool_set_part_material,
        requires_approval=True,
        read_only=False,
        destructive=False,
        description="[APPROVAL REQUIRED] Assign a material to a named part in the current project. Updates graph/feature_graph.json.",
        input_schema=_schema("set_part_material"),
    )

    def _tool_generate_bom(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import standards_bridge as _sb
        return _sb.generate_bom(
            active_settings=active_settings,
            project_id=str(inp.get("project_id") or "").strip() or None,
            package_path=str(inp.get("package_path") or "").strip() or None,
            fmt=str(inp.get("format") or "").strip() or None,
        )

    _rt.register_tool(
        "generate_bom",
        _tool_generate_bom,
        description="Generate a Bill of Materials from the current project parts, including standard parts and their quantities.",
        input_schema=_schema("generate_bom"),
    )

    return RuntimeToolHandlers(
        apply_shape_ir_patch=_tool_aieng_apply_shape_ir_patch,
        derive_topology_optimization_problem=_tool_opt_derive_problem_from_cae,
        run_topology_optimization=_tool_opt_run_topology_optimization,
        writeback_topology_optimization=_tool_opt_writeback_to_shape_ir,
        run_assembly_topology_optimization=_tool_opt_run_assembly_topology_optimization,
    )
