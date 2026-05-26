from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import yaml

from .providers import get_provider
from . import runtime as _rt
from . import agent_workbench
from . import agent_engine

from .config import (
    APP_ROOT,
    AIENG_EXT,
    PLATFORM_ROOT,
    RUNTIME_CONFIG_FILENAME,
    SAFE_NAME,
    STEP_EXTENSIONS,
    SUPPORTED_TOPOLOGY_BACKENDS,
    TOOLS_ALLOWED,
    WORKSPACE_ROOT,
    Settings,
    now_iso,
    read_json,
    write_json,
)
from .core_dependencies import (
    _STALE_EVIDENCE_CATEGORIES,
    _build_audit_event,
    _build_claim_proposal,
    _build_review_readiness,
    _check_claim_proposals,
    _classify_artifact_path,
    _core_generate_artifact_manifest,
    _is_internal_package_path,
    _rollup_check_status,
)
from .package_inspection import (
    _detect_cae_artifacts,
    _generate_cad_recommendations_with_verification,
    _generate_cae_preprocessing_summary,
    _generate_cae_result_summary,
    _generate_cae_simulation_run_summary,
    build_cae_review_report,
    package_member_count,
    package_member_items,
    package_summary_fallback,
    read_package_json,
    read_package_json_candidates,
    read_package_text,
    read_package_yaml,
    read_package_yaml_candidates,
    summarize_cae_payload,
    summarize_evidence_items,
)
from .project_io import (
    ARTIFACT_MANIFEST_PATH,
    AUDIT_EVENTS_PATH,
    CLAIM_PROPOSALS_DIR,
    REVALIDATION_STATUS_PATH,
    _ALLOWED_PATCH_EXACT,
    _ALLOWED_PATCH_PREFIXES,
    _ARTIFACT_MAX_PARSE_BYTES,
    _ARTIFACT_MAX_TEXT_BYTES,
    _ARTIFACT_MEDIA_HINTS,
    _ARTIFACT_TEXT_SUFFIXES,
    _CAE_RESULT_FIELDS,
    _GEOMETRY_STALE_ARTIFACTS,
    _RUN_ID_PATTERN,
    _SETUP_STALE_ARTIFACTS,
    _SOLVER_INPUT_MAX_BYTES,
    _SUPPORTED_PATCH_OPERATIONS,
    _TOOL_CAPABILITY_PROFILE,
    _VALID_PROPOSED_STATUSES,
    _append_audit_event_to_package,
    _apply_patches_to_package,
    _apply_single_patch,
    _build_claim_support_packet,
    _build_revalidation_response,
    _classify_artifact_media_type,
    _compute_stale_artifacts,
    _feature_list_from_graph,
    _generate_artifact_manifest,
    _is_allowed_patch_path,
    _is_safe_artifact_path,
    _is_safe_run_id,
    _json_diff_paths,
    _json_pointer_get,
    _json_pointer_set,
    _parse_calculix_input_deck,
    _parse_json_pointer,
    _read_artifact_from_package,
    _read_audit_events_from_package,
    _read_claim_proposals_from_package,
    _read_revalidation_status,
    _record_geometry_edit_in_package,
    _record_solver_validation_in_package,
    _resolve_evidence_reference,
    _run_package_consistency_checks,
    _unpack_geometry_from_package,
    _validate_cad_parameter_edit_contract,
    _validate_claim_proposal_request,
    _write_claim_proposal_to_package,
    _write_mesh_into_package_atomic,
    _write_modified_step_into_package,
    _write_revalidation_status,
    _write_revalidation_status_dict,
    convert_stl_to_glb,
    default_project,
    ensure_dirs,
    ensure_step_source,
    extract_step_from_package,
    get_project,
    metadata_path,
    normalize_project,
    project_dir,
    project_relpath,
    resolve_project_path,
    save_project,
    write_artifact_to_package,
    write_audit_log,
)


# Keep legacy introspection stable for helpers that used to live in app.main.
for _compat_name in (
    "_detect_cae_artifacts",
    "_generate_cae_preprocessing_summary",
    "_generate_cae_result_summary",
    "_generate_cae_simulation_run_summary",
    "_record_geometry_edit_in_package",
    "_record_solver_validation_in_package",
):
    _compat_obj = globals().get(_compat_name)
    if callable(_compat_obj):
        _compat_obj.__module__ = __name__
del _compat_name, _compat_obj


def default_runtime_config(settings: Settings) -> dict[str, str]:
    return {
        "provider": "freecad",
        "aieng_root": str(settings.aieng_root),
        "freecad_mcp_root": "",
        "freecad_home": "",
        "topology_backend": "auto",
    }


def normalize_runtime_config(settings: Settings, payload: dict[str, Any] | None) -> dict[str, str]:
    defaults = default_runtime_config(settings)
    merged = {**defaults, **(payload or {})}

    topology_backend = str(merged.get("topology_backend") or defaults["topology_backend"]).strip().lower()
    if topology_backend not in SUPPORTED_TOPOLOGY_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_TOPOLOGY_BACKENDS))
        raise HTTPException(
            status_code=400,
            detail=f"unsupported topology backend: {topology_backend}; supported: {supported}",
        )

    normalized: dict[str, str] = {
        "provider": str(merged.get("provider") or defaults["provider"]).strip() or defaults["provider"],
        "topology_backend": topology_backend,
        "freecad_mcp_root": str(merged.get("freecad_mcp_root") or "").strip(),
        "freecad_home": str(merged.get("freecad_home") or "").strip(),
    }
    raw_aieng_root = str(merged.get("aieng_root") or "").strip()
    if not raw_aieng_root:
        raise HTTPException(status_code=400, detail="aieng_root must be a non-empty string")
    normalized["aieng_root"] = str(Path(raw_aieng_root).resolve())
    return normalized


def read_persisted_runtime_config(settings: Settings) -> dict[str, Any]:
    try:
        stored = read_json(settings.runtime_config_path, {})
    except (OSError, json.JSONDecodeError):
        return {}
    return stored if isinstance(stored, dict) else {}


def resolve_runtime_config(settings: Settings, overrides: dict[str, Any] | None = None) -> dict[str, str]:
    persisted = read_persisted_runtime_config(settings)
    return normalize_runtime_config(settings, {**persisted, **(overrides or {})})


def persist_runtime_config(settings: Settings, payload: dict[str, Any] | None) -> dict[str, Any]:
    ensure_dirs(settings)
    config = resolve_runtime_config(settings, payload)
    write_json(settings.runtime_config_path, config)
    return runtime_config_snapshot(settings)


def settings_with_runtime_config(settings: Settings, config: dict[str, str]) -> Settings:
    return Settings(
        platform_root=settings.platform_root,
        workspace_root=settings.workspace_root,
        data_root=settings.data_root,
        aieng_root=Path(config["aieng_root"]).resolve(),
        sample_step=settings.sample_step,
    )


def resolve_effective_settings(settings: Settings, overrides: dict[str, Any] | None = None) -> Settings:
    return settings_with_runtime_config(settings, resolve_runtime_config(settings, overrides))


def resolve_provider_bundle(
    settings: Settings,
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, str], Settings, Any]:
    config = resolve_runtime_config(settings, overrides)
    effective_settings = settings_with_runtime_config(settings, config)
    provider = get_provider(effective_settings, config)
    return config, effective_settings, provider


def runtime_probe(settings: Settings, config: dict[str, str]) -> dict[str, Any]:
    _, _, provider = resolve_provider_bundle(settings, config)
    return provider.probe_capabilities(whitelisted_tools=TOOLS_ALLOWED)


def runtime_config_snapshot(settings: Settings, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = resolve_runtime_config(settings, overrides)
    return {
        "config": config,
        "defaults": default_runtime_config(settings),
        "probe": runtime_probe(settings, config),
        "config_path": str(settings.runtime_config_path),
        "persisted_exists": settings.runtime_config_path.exists(),
    }


from .services import platform_logic as _platform_logic

def runtime_status(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.runtime_status(*args, **kwargs)


def compact_chat_output(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.compact_chat_output(*args, **kwargs)


def find_patch_json(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.find_patch_json(*args, **kwargs)


def build_chat_plan(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.build_chat_plan(*args, **kwargs)


def import_aieng_file(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.import_aieng_file(*args, **kwargs)


def validate_aieng_file(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.validate_aieng_file(*args, **kwargs)


def convert_asset(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.convert_asset(*args, **kwargs)


def recent_logs(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.recent_logs(*args, **kwargs)


def package_summary(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.package_summary(*args, **kwargs)


def mcp_check(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.mcp_check(*args, **kwargs)


def parse_patch(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.parse_patch(*args, **kwargs)


def prepare_patch_execution(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.prepare_patch_execution(*args, **kwargs)


def execute_chat_step(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.execute_chat_step(*args, **kwargs)


def chat_orchestrator(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic.chat_orchestrator(*args, **kwargs)


def _resolve_frd_in_package(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic._resolve_frd_in_package(*args, **kwargs)


def _extract_frd_field_data(*args: Any, **kwargs: Any) -> Any:
    _platform_logic.sync_main_symbols()
    return _platform_logic._extract_frd_field_data(*args, **kwargs)


from .app_factory import create_app as _create_app


def create_app(settings: Settings | None = None) -> FastAPI:
    return _create_app(settings)


app = create_app()
