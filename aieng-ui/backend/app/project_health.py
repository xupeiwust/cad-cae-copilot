"""Read-only project health check for the AIENG Decision Review Workbench.

Inspects a project's `.aieng` package, Copilot loops, and metadata without
mutating anything, running solvers, or advancing claims.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import Settings, read_json
from .copilot_loop import _loop_path, _read_report_text, list_loops
from .package_inspection import (
    read_package_json,
    read_package_json_candidates,
    read_package_text,
    read_package_yaml,
    read_package_yaml_candidates,
)
from .project_io import REVALIDATION_STATUS_PATH, get_project, project_dir


# Prohibited certification language (same list used in demo smoke-check).
_PROHIBITED_CERTIFICATION_PHRASES = (
    "design is certified",
    "claim accepted",
    "certified safe",
    "engineering claim approved",
)

_CLAIM_BOUNDARY_EXPORT_NOTE = (
    "This decision review export is a reviewable record of one or two Copilot "
    "loops. It does not certify either design, does not advance engineering "
    "claims, and must be reviewed by a qualified engineer before being cited "
    "in any acceptance decision."
)


def _check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    category: str,
    label: str,
    status: str,
    summary: str,
    details: list[str] | None = None,
    next_action: str | None = None,
) -> None:
    checks.append(
        {
            "id": check_id,
            "category": category,
            "label": label,
            "status": status,
            "summary": summary,
            "details": details or [],
            "next_action": next_action,
        }
    )


def _action(
    action_id: str,
    priority: str,
    action_type: str,
    label: str,
    summary: str,
    source_check_ids: list[str],
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "priority": priority,
        "action_type": action_type,
        "label": label,
        "summary": summary,
        "source_check_ids": source_check_ids,
        "target": target,
        "safety": {
            "mutates_package": False,
            "runs_solver": False,
            "advances_claim": False,
        },
    }


def _package_digest(path: Path) -> str:
    """Return a SHA-256 hex digest of the file for mutation detection."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _find_package_members(archive: zipfile.ZipFile, prefix: str) -> list[str]:
    return [m for m in archive.namelist() if m.startswith(prefix)]


def _has_cae_solver_run_artifacts(archive: zipfile.ZipFile) -> bool:
    members = archive.namelist()
    return any(
        "simulation/runs/" in m and (m.endswith("solver_input.inp") or m.endswith("solver_run.json"))
        for m in members
    )


def _has_frd_output(archive: zipfile.ZipFile) -> bool:
    members = archive.namelist()
    return any("result.frd" in m or ".frd" in m for m in members if "simulation/runs/" in m)


def _read_any_report_text(settings: Settings, project_id: str, loop: dict[str, Any]) -> str | None:
    """Best-effort read of a loop report text for claim-boundary scanning."""
    try:
        text, _ = _read_report_text(settings, project_id, loop)
        return text
    except Exception:
        return None


def _scan_report_for_claim_boundary(text: str | None) -> tuple[bool, list[str]]:
    if not text:
        return False, []
    has_en = "does not certify" in text.lower()
    has_zh = "does not certify" in text.lower()
    missing: list[str] = []
    if not has_en:
        missing.append("English claim boundary missing")
    if not has_zh:
        missing.append("Chinese claim boundary missing")
    return has_en and has_zh, missing


def _scan_report_for_prohibited_language(text: str | None) -> list[str]:
    found: list[str] = []
    if not text:
        return found
    lower = text.lower()
    for phrase in _PROHIBITED_CERTIFICATION_PHRASES:
        if phrase in lower:
            found.append(phrase)
    return found


def run_project_health_check(settings: Settings, project_id: str) -> dict[str, Any]:
    """Run a read-only health check on a project and return structured results.

    This function never mutates the project, package, or loops. It only reads
    metadata, ZIP contents, and persisted loop files.
    """
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    limitations: list[str] = [
        "Health check is read-only and heuristic only.",
        "It does not prove physical correctness, convergence, or design safety.",
        "It does not run solvers, meshers, or CAD kernels.",
    ]

    # --- 1. Resolve project -------------------------------------------------
    try:
        project = get_project(settings, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            _check(checks, check_id="project_exists", category="package", label="Project exists", status="failed", summary="Project not found.", next_action="Create or select a project.")
            actions = _build_recommended_actions(checks)
            return _build_response(project_id, "not_ready", checks, warnings, limitations, project_name=None, package_path=None, recommended_actions=actions, overall_next_action=_build_overall_next_action("not_ready", actions))
        raise

    project_name = project.get("name")
    _check(checks, check_id="project_exists", category="package", label="Project exists", status="passed", summary=f"Project '{project_name}' found.")

    # --- 2. Package health --------------------------------------------------
    aieng_file = project.get("aieng_file")
    if not aieng_file:
        _check(checks, check_id="package_path", category="package", label="Package path configured", status="failed", summary="Project has no .aieng package configured.", next_action="Import or create a .aieng package.")
        actions = _build_recommended_actions(checks)
        return _build_response(project_id, "not_ready", checks, warnings, limitations, project_name=project_name, package_path=None, recommended_actions=actions, overall_next_action=_build_overall_next_action("not_ready", actions))

    package_path = project_dir(settings, project_id) / aieng_file
    package_path_resolved = package_path.resolve()
    try:
        package_path_resolved.relative_to(project_dir(settings, project_id).resolve())
    except ValueError:
        _check(checks, check_id="package_path_safe", category="package", label="Package path safe", status="failed", summary="Package path escapes project directory.")
        actions = _build_recommended_actions(checks)
        return _build_response(project_id, "not_ready", checks, warnings, limitations, project_name=project_name, package_path=str(package_path), recommended_actions=actions, overall_next_action=_build_overall_next_action("not_ready", actions))

    if not package_path.exists():
        _check(checks, check_id="package_file", category="package", label="Package file exists", status="failed", summary=f"Package file not found: {aieng_file}", next_action="Re-import the .aieng package.")
        actions = _build_recommended_actions(checks)
        return _build_response(project_id, "not_ready", checks, warnings, limitations, project_name=project_name, package_path=str(package_path), recommended_actions=actions, overall_next_action=_build_overall_next_action("not_ready", actions))

    _check(checks, check_id="package_file", category="package", label="Package file exists", status="passed", summary=f"Package file found ({package_path.stat().st_size} bytes).")

    # Record digest for post-check mutation verification.
    before_digest = _package_digest(package_path)

    # Open ZIP and inspect contents.
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            members = archive.namelist()
            manifest = read_package_json(archive, "manifest.json")
            evidence_index = read_package_json(archive, "results/evidence_index.json")
            computed_metrics = read_package_json(archive, "results/computed_metrics.json")
            result_summary = read_package_json(archive, "results/result_summary.json")
            design_targets = read_package_yaml_candidates(archive, ("task/design_targets.yaml", "task/design_targets.yml"))
            engineering_setup_draft = read_package_json(archive, "task/engineering_setup_draft.json")
            feature_graph = read_package_json(archive, "graph/feature_graph.json")
            topology = read_package_json(archive, "geometry/topology_map.json")
            parsed_features = read_package_json(archive, "simulation/cae_imports/parsed_features.json")
            validation_status = read_package_yaml(archive, "validation/status.yaml")
            revalidation_status = read_package_json(archive, REVALIDATION_STATUS_PATH)
            if revalidation_status is None:
                revalidation_status = read_package_json(archive, "revalidation_status.json")
            completeness_report = read_package_json(archive, "validation/completeness_report.json")
    except zipfile.BadZipFile:
        _check(checks, check_id="package_readable", category="package", label="Package readable", status="failed", summary="Package is not a valid ZIP file.", next_action="Re-create or re-import the .aieng package.")
        actions = _build_recommended_actions(checks)
        return _build_response(project_id, "not_ready", checks, warnings, limitations, project_name=project_name, package_path=str(package_path), recommended_actions=actions, overall_next_action=_build_overall_next_action("not_ready", actions))
    except Exception as exc:
        _check(checks, check_id="package_readable", category="package", label="Package readable", status="failed", summary=f"Could not open package: {type(exc).__name__}.")
        actions = _build_recommended_actions(checks)
        return _build_response(project_id, "not_ready", checks, warnings, limitations, project_name=project_name, package_path=str(package_path), recommended_actions=actions, overall_next_action=_build_overall_next_action("not_ready", actions))

    _check(checks, check_id="package_readable", category="package", label="Package readable", status="passed", summary=f"Package opened as ZIP with {len(members)} member(s).")

    if manifest is None:
        _check(checks, check_id="manifest", category="package", label="Manifest readable", status="failed", summary="manifest.json missing or unreadable.", next_action="Validate and re-export the package.")
    else:
        _check(checks, check_id="manifest", category="package", label="Manifest readable", status="passed", summary="manifest.json present and valid JSON.")

    # --- 3. Evidence health -------------------------------------------------
    if evidence_index is None:
        _check(checks, check_id="evidence_index", category="evidence", label="Evidence index present", status="warning", summary="results/evidence_index.json missing.", next_action="Run evidence scaffolding or import solver results.")
    else:
        _check(checks, check_id="evidence_index", category="evidence", label="Evidence index present", status="passed", summary="Evidence index present.")

    stale_markers = 0
    if isinstance(revalidation_status, dict):
        for key, value in revalidation_status.items():
            if isinstance(value, dict) and value.get("stale"):
                stale_markers += 1
            elif value is True:
                stale_markers += 1
    if stale_markers > 0:
        _check(checks, check_id="stale_evidence", category="evidence", label="Stale evidence", status="warning", summary=f"{stale_markers} artifact(s) marked stale.", next_action="Re-run affected simulations or refresh summaries.")
    else:
        _check(checks, check_id="stale_evidence", category="evidence", label="Stale evidence", status="passed", summary="No stale evidence markers detected.")

    # --- 4. CAD readiness ---------------------------------------------------
    has_cad_context = feature_graph is not None or topology is not None or parsed_features is not None
    if not has_cad_context:
        _check(checks, check_id="cad_context", category="cad", label="CAD context present", status="warning", summary="No feature graph, topology, or parsed features found.", next_action="Import or convert CAD geometry.")
    else:
        details: list[str] = []
        if feature_graph is not None:
            details.append("Feature graph present")
        if topology is not None:
            details.append("Topology map present")
        if parsed_features is not None:
            details.append("Parsed features present")
        _check(checks, check_id="cad_context", category="cad", label="CAD context present", status="passed", summary="CAD geometry context available.", details=details)

    editable_params: list[str] = []
    if isinstance(feature_graph, dict):
        for feat in feature_graph.get("features") or []:
            if isinstance(feat, dict) and feat.get("editable_parameters"):
                editable_params.extend(feat["editable_parameters"])
            elif isinstance(feat, dict) and "parameter" in str(feat.get("name", "")).lower():
                editable_params.append(str(feat.get("name")))
    if isinstance(parsed_features, dict):
        for feat in parsed_features.get("features") or []:
            if isinstance(feat, dict) and feat.get("thickness_mm") is not None:
                editable_params.append(f"{feat.get('name', 'feature')}: thickness_mm")
    if not editable_params:
        _check(checks, check_id="editable_parameters", category="cad", label="Editable parameters", status="warning", summary="No editable parameters detected.", next_action="Ensure CAD features carry parameter metadata.")
    else:
        _check(checks, check_id="editable_parameters", category="cad", label="Editable parameters", status="passed", summary=f"{len(editable_params)} editable parameter(s) found.", details=editable_params[:8])

    # --- 5. CAE readiness ---------------------------------------------------
    has_solver_input = any("solver_input.inp" in m for m in members)
    has_solver_run = _has_cae_solver_run_artifacts(archive) if 'archive' in dir() else False
    has_frd = _has_frd_output(archive) if 'archive' in dir() else False
    has_computed_metrics = computed_metrics is not None
    has_result_summary = result_summary is not None

    cae_details: list[str] = []
    if has_solver_input:
        cae_details.append("Solver input deck present")
    if has_solver_run:
        cae_details.append("Solver run metadata present")
    if has_frd:
        cae_details.append("FRD output present")
    if has_computed_metrics:
        cae_details.append("Computed metrics present")
    if has_result_summary:
        cae_details.append("Result summary present")

    if not cae_details:
        _check(checks, check_id="cae_artifacts", category="cae", label="CAE artifacts present", status="warning", summary="No CAE solver artifacts found.", next_action="Import solver input, run a solver, or import external results.")
    else:
        _check(checks, check_id="cae_artifacts", category="cae", label="CAE artifacts present", status="passed", summary=f"{len(cae_details)} CAE artifact type(s) found.", details=cae_details)

    if not has_computed_metrics:
        _check(checks, check_id="computed_metrics", category="cae", label="Computed metrics present", status="warning", summary="No computed metrics found. Target comparison and postprocessing will be limited.", next_action="Import computed metrics or run postprocessing before comparing targets.")
    else:
        metric_count = 0
        load_case_count = 0
        if isinstance(computed_metrics, dict):
            global_metrics = computed_metrics.get("global_metrics") or {}
            if isinstance(global_metrics, dict):
                metric_count += len(global_metrics)
            load_cases = computed_metrics.get("load_cases") or []
            if isinstance(load_cases, list):
                load_case_count = len([lc for lc in load_cases if isinstance(lc, dict)])
                for lc in load_cases:
                    metrics = lc.get("metrics") if isinstance(lc, dict) else None
                    if isinstance(metrics, dict):
                        metric_count += len(metrics)
        count_text = f" ({metric_count} metric(s), {load_case_count} load case(s))." if metric_count or load_case_count else "."
        _check(checks, check_id="computed_metrics", category="cae", label="Computed metrics present", status="passed", summary=f"Computed metrics present{count_text}")

    # --- 6. Design targets --------------------------------------------------
    if design_targets is None:
        _check(checks, check_id="design_targets", category="targets", label="Design targets present", status="warning", summary="No design targets found. Copilot Loop can still run, but target comparison will be limited.", next_action="Add task/design_targets.yaml to the package.")
    else:
        targets_list: list[Any] = []
        if isinstance(design_targets, dict):
            targets_list = design_targets.get("targets") or []
        target_count = len(targets_list) if isinstance(targets_list, list) else 0
        _check(checks, check_id="design_targets", category="targets", label="Design targets present", status="passed", summary=f"{target_count} design target(s) found.")

    # --- 6b. Engineering setup draft (informational) -----------------------
    # v0.34 — surface the template draft only when one exists. Absence is not
    # a warning: most projects don't use the template authoring path.
    if isinstance(engineering_setup_draft, dict):
        template_id = engineering_setup_draft.get("template_id") or "unknown"
        params = engineering_setup_draft.get("parameters") or {}
        param_count = len(params) if isinstance(params, dict) else 0
        _check(
            checks,
            check_id="engineering_setup_draft",
            category="targets",
            label="Engineering setup draft present",
            status="passed",
            summary=(
                f"Template draft '{template_id}' with {param_count} parameter(s) saved. "
                "Draft is informational only — it does not certify the design and is not "
                "a substitute for design targets, CAD, or solver evidence."
            ),
            details=["This is a reviewable draft. The user must explicitly proceed through the existing CAD edit and structural solver run workflows."],
            next_action="Review the draft and explicitly continue through the existing approval-gated workflows.",
        )

    if design_targets is not None and computed_metrics is not None:
        try:
            from . import target_comparison

            comparison_result = target_comparison.compare_package_targets(settings, project_id)
            summary = comparison_result.get("summary") or {}
            details = []
            for item in comparison_result.get("items") or []:
                if not isinstance(item, dict):
                    continue
                details.append(
                    f"{item.get('target_id')}: {item.get('status')}"
                    + (f" ({item.get('reason_code')})" if item.get("reason_code") else "")
                )
            _check(
                checks,
                check_id="target_comparison",
                category="targets",
                label="Target comparison available",
                status="passed",
                summary=(
                    f"{summary.get('pass', 0)} pass, {summary.get('fail', 0)} fail, "
                    f"{summary.get('unknown', 0)} unknown, {summary.get('not_evaluated', 0)} not evaluated "
                    f"across {summary.get('total', 0)} target(s)."
                ),
                details=details[:12],
            )
        except Exception as exc:
            _check(
                checks,
                check_id="target_comparison",
                category="targets",
                label="Target comparison available",
                status="warning",
                summary=f"Target comparison could not be evaluated: {type(exc).__name__}.",
                next_action="Check design targets and computed metrics before comparing.",
            )
    else:
        _check(
            checks,
            check_id="target_comparison",
            category="targets",
            label="Target comparison available",
            status="skipped",
            summary="Design targets and computed metrics are both required for target comparison.",
        )

    # --- 7. Claims / safety -------------------------------------------------
    # Scan loop reports for claim boundary and prohibited language.
    try:
        loops_result = list_loops(settings, project_id)
        loops = loops_result.get("loops") or []
    except Exception:
        loops = []

    report_texts: list[str] = []
    for loop_summary in loops:
        loop_id = loop_summary.get("loop_id")
        if not loop_id:
            continue
        try:
            loop_data = read_json(_loop_path(settings, project_id, loop_id), None)
            if isinstance(loop_data, dict):
                text = _read_any_report_text(settings, project_id, loop_data)
                if text:
                    report_texts.append(text)
        except Exception:
            continue

    if report_texts:
        all_boundaries_ok = True
        all_boundary_missing: list[str] = []
        all_prohibited: list[str] = []
        for text in report_texts:
            ok, missing = _scan_report_for_claim_boundary(text)
            if not ok:
                all_boundaries_ok = False
                all_boundary_missing.extend(missing)
            prohibited = _scan_report_for_prohibited_language(text)
            all_prohibited.extend(prohibited)

        if all_boundaries_ok:
            _check(checks, check_id="claim_boundary", category="claims", label="Claim boundary present", status="passed", summary="Claim boundary found in all scanned loop reports.")
        else:
            _check(checks, check_id="claim_boundary", category="claims", label="Claim boundary present", status="warning", summary="Some loop reports are missing claim boundary text.", details=list(dict.fromkeys(all_boundary_missing)))

        if all_prohibited:
            _check(checks, check_id="prohibited_language", category="claims", label="No prohibited certification language", status="failed", summary=f"Found {len(all_prohibited)} prohibited phrase(s).", details=list(dict.fromkeys(all_prohibited)), next_action="Remove certification language from loop reports.")
        else:
            _check(checks, check_id="prohibited_language", category="claims", label="No prohibited certification language", status="passed", summary="No prohibited certification language detected.")
    else:
        _check(checks, check_id="claim_boundary", category="claims", label="Claim boundary present", status="skipped", summary="No loop reports available to scan.")
        _check(checks, check_id="prohibited_language", category="claims", label="No prohibited certification language", status="skipped", summary="No loop reports available to scan.")

    # --- 8. Loop readiness --------------------------------------------------
    loop_count = len(loops)
    if loop_count == 0:
        _check(checks, check_id="loop_count", category="loops", label="Copilot loops", status="warning", summary="No Copilot loops yet.", next_action="Start first Copilot Loop.")
    elif loop_count == 1:
        _check(checks, check_id="loop_count", category="loops", label="Copilot loops", status="passed", summary="1 loop exists.", next_action="Run another loop to enable comparison.")
    else:
        _check(checks, check_id="loop_count", category="loops", label="Copilot loops", status="passed", summary=f"{loop_count} loops exist (comparison-ready).", next_action="Compare loops side-by-side.")

    reports_for_loops = sum(1 for s in loops if s.get("report_path"))
    if loop_count > 0 and reports_for_loops < loop_count:
        _check(checks, check_id="loop_reports", category="loops", label="Loop reports generated", status="warning", summary=f"{reports_for_loops}/{loop_count} loop(s) have reports.", next_action="Advance loops to report generation.")
    elif loop_count > 0:
        _check(checks, check_id="loop_reports", category="loops", label="Loop reports generated", status="passed", summary=f"All {loop_count} loop(s) have reports.")
    else:
        _check(checks, check_id="loop_reports", category="loops", label="Loop reports generated", status="skipped", summary="No loops to check.")

    # --- 9. Demo metadata ---------------------------------------------------
    if project.get("demo") or project.get("demo_copilot_loop"):
        notice = project.get("demo_notice") or "Demo fixture data."
        _check(checks, check_id="demo_metadata", category="demo", label="Demo metadata", status="passed", summary=f"This is deterministic demo fixture data. {notice}")
    else:
        _check(checks, check_id="demo_metadata", category="demo", label="Demo metadata", status="passed", summary="This is a regular user project, not a demo fixture.")

    # --- Readiness calculation ----------------------------------------------
    failed_ids = {c["id"] for c in checks if c["status"] == "failed"}
    warning_ids = {c["id"] for c in checks if c["status"] == "warning"}

    if "package_file" in failed_ids or "package_readable" in failed_ids or "manifest" in failed_ids:
        readiness = "not_ready"
    elif warning_ids:
        readiness = "partial"
    else:
        readiness = "ready"

    # --- Recommended actions ------------------------------------------------
    recommended_actions = _build_recommended_actions(checks)
    overall_next_action = _build_overall_next_action(readiness, recommended_actions)

    # --- Mutation guard -----------------------------------------------------
    after_digest = _package_digest(package_path)
    if after_digest != before_digest:
        warnings.append("Package digest changed during health check — this should not happen for a read-only operation.")

    return _build_response(
        project_id=project_id,
        readiness=readiness,
        checks=checks,
        warnings=warnings,
        limitations=limitations,
        project_name=project_name,
        package_path=str(package_path),
        recommended_actions=recommended_actions,
        overall_next_action=overall_next_action,
    )


def _build_recommended_actions(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate deterministic, read-only recommended actions from health checks."""
    actions: list[dict[str, Any]] = []
    check_map = {c["id"]: c for c in checks}

    # 1. Package / manifest (highest priority)
    if check_map.get("package_file", {}).get("status") == "failed" or check_map.get("package_path", {}).get("status") == "failed":
        actions.append(
            _action(
                "upload_package",
                "high",
                "manual",
                "Create or upload a valid .aieng package",
                "The project has no readable .aieng package. Import a package before running Copilot Loop.",
                ["package_file"] if check_map.get("package_file", {}).get("status") == "failed" else ["package_path"],
            )
        )

    if check_map.get("package_readable", {}).get("status") == "failed":
        actions.append(
            _action(
                "fix_package",
                "high",
                "manual",
                "Fix corrupted .aieng package",
                "The package is not a valid ZIP file. Re-create or re-import it.",
                ["package_readable"],
            )
        )

    if check_map.get("manifest", {}).get("status") == "failed":
        actions.append(
            _action(
                "fix_manifest",
                "high",
                "manual",
                "Fix package manifest before running Copilot Loop",
                "manifest.json is missing or unreadable. Validate and re-export the package.",
                ["manifest"],
            )
        )

    # 2. Evidence / stale
    if check_map.get("stale_evidence", {}).get("status") == "warning":
        actions.append(
            _action(
                "review_stale",
                "high",
                "navigate",
                "Review stale evidence before trusting old results",
                "Some artifacts are marked stale. Re-run affected simulations or refresh summaries before making decisions.",
                ["stale_evidence"],
                target={"tab": "copilot_loop", "section": "stale_evidence", "intent": "navigation"},
            )
        )

    # 3. CAD / CAE / targets
    if check_map.get("cad_context", {}).get("status") == "warning":
        actions.append(
            _action(
                "inspect_cad_features",
                "medium",
                "navigate",
                "Inspect CAD features (read-only) to produce feature/parameter evidence",
                "No CAD feature/parameter evidence found. Run a read-only CAD feature inspection to write parsed_features.json and feature_graph.json.",
                ["cad_context"],
                target={"tab": "copilot_loop", "section": "geometry_inspection", "intent": "navigation"},
            )
        )
    if check_map.get("editable_parameters", {}).get("status") == "warning":
        actions.append(
            _action(
                "add_editable_params",
                "medium",
                "navigate",
                "Add or expose editable CAD parameters before CAD modification proposals",
                "No editable parameters detected. Ensure CAD features carry parameter metadata; running read-only CAD feature inspection may surface them.",
                ["editable_parameters"],
                target={"tab": "copilot_loop", "section": "geometry_inspection", "intent": "navigation"},
            )
        )

    if check_map.get("design_targets", {}).get("status") == "warning":
        actions.append(
            _action(
                "add_design_targets",
                "high",
                "navigate",
                "Add measurable design targets",
                "No design targets found. Add task/design_targets.yaml to enable target comparison.",
                ["design_targets"],
                target={"tab": "copilot_loop", "section": "design_targets", "intent": "navigation"},
            )
        )

    if check_map.get("computed_metrics", {}).get("status") == "warning":
        actions.append(
            _action(
                "import_computed_metrics",
                "medium",
                "navigate",
                "Import computed metrics or run postprocessing before comparing targets",
                "No computed metrics found. Import metrics or run postprocessing before comparing against design targets.",
                ["computed_metrics"],
                target={"tab": "copilot_loop", "section": "computed_metrics", "intent": "navigation"},
            )
        )

    if check_map.get("cae_artifacts", {}).get("status") == "warning":
        # Only add if computed_metrics is not already flagged (avoid duplication)
        if check_map.get("computed_metrics", {}).get("status") != "warning":
            actions.append(
                _action(
                    "import_cae_artifacts",
                    "medium",
                    "manual",
                    "Import CAE artifacts or run solver before evaluation",
                    "No CAE solver artifacts found. Import solver input or run a solver to produce results.",
                    ["cae_artifacts"],
                )
            )

    # 4. Loops / reports / export
    loop_check = check_map.get("loop_count")
    if loop_check and loop_check.get("status") == "warning":
        actions.append(
            _action(
                "start_loop",
                "medium",
                "navigate",
                "Start the first Copilot Loop after required package inputs are ready",
                "No Copilot loops exist yet. Start a loop once the package has the required inputs.",
                ["loop_count"],
                target={"tab": "copilot_loop", "section": "copilot_stepper", "intent": "navigation"},
            )
        )
    elif loop_check and "1 loop exists" in (loop_check.get("summary") or ""):
        actions.append(
            _action(
                "run_another_loop",
                "low",
                "navigate",
                "Run another Copilot Loop to enable comparison",
                "Only one loop exists. Run another loop to enable side-by-side comparison.",
                ["loop_count"],
                target={"tab": "copilot_loop", "section": "copilot_stepper", "intent": "navigation"},
            )
        )

    if check_map.get("loop_reports", {}).get("status") == "warning":
        actions.append(
            _action(
                "generate_reports",
                "medium",
                "navigate",
                "Generate loop reports before comparing or exporting review",
                "Some loops are missing reports. Advance loops to report generation before exporting.",
                ["loop_reports"],
                target={"tab": "copilot_loop", "section": "loop_history", "intent": "navigation"},
            )
        )

    if check_map.get("claim_boundary", {}).get("status") == "warning":
        actions.append(
            _action(
                "regenerate_claim_boundary",
                "high",
                "manual",
                "Regenerate reports with claim-boundary text before sharing",
                "Some loop reports are missing the claim boundary. Regenerate reports before sharing.",
                ["claim_boundary"],
            )
        )

    if check_map.get("prohibited_language", {}).get("status") == "failed":
        actions.append(
            _action(
                "remove_certification_language",
                "high",
                "manual",
                "Remove prohibited certification language from reports",
                "Prohibited certification phrases detected in loop reports. Remove them before sharing.",
                ["prohibited_language"],
            )
        )

    # 5. Demo
    demo_check = check_map.get("demo_metadata")
    if demo_check and demo_check.get("status") == "passed" and "deterministic demo fixture" in (demo_check.get("summary") or ""):
        actions.append(
            _action(
                "demo_notice",
                "low",
                "manual",
                "Use this demo to learn the workflow, but do not treat fixture metrics as real simulation evidence",
                "This is deterministic demo fixture data. Learn the workflow, but do not use these metrics for real engineering decisions.",
                ["demo_metadata"],
            )
        )

    # Deduplicate by id
    seen: set[str] = set()
    unique_actions: list[dict[str, Any]] = []
    for a in actions:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique_actions.append(a)

    # Sort by priority (high → medium → low), then by original dependency order
    priority_order = {"high": 0, "medium": 1, "low": 2}
    unique_actions.sort(key=lambda a: (priority_order.get(a["priority"], 99), actions.index(a)))

    return unique_actions


def _build_overall_next_action(readiness: str, actions: list[dict[str, Any]]) -> str | None:
    if readiness == "ready":
        return "This project appears ready for the current Copilot Loop review workflow."
    if not actions:
        return None
    # Return the label of the highest-priority action as the overall guidance
    return actions[0]["label"] if actions else None


def _build_response(
    project_id: str,
    readiness: str,
    checks: list[dict[str, Any]],
    warnings: list[str],
    limitations: list[str],
    project_name: str | None,
    package_path: str | None,
    recommended_actions: list[dict[str, Any]] | None = None,
    overall_next_action: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": readiness in ("ready", "partial"),
        "readiness": readiness,
        "project_id": project_id,
        "project_name": project_name,
        "package_path": package_path,
        "checks": checks,
        "warnings": warnings,
        "limitations": limitations,
        "claim_boundary": _CLAIM_BOUNDARY_EXPORT_NOTE,
        "recommended_actions": recommended_actions or [],
        "overall_next_action": overall_next_action,
    }
