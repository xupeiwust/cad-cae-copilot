"""Design-study candidate CAE evaluation request v0.

Explicit, candidate-local evaluation layer that connects design-study candidates to
solver-neutral CAE contracts. It is NOT an optimizer, does NOT auto-generate candidates,
does NOT auto-accept, and does NOT overwrite baseline geometry or CAE artifacts.

Modes:
  prepare_only       — derive candidate-local CAE setup, write diagnostics, stop.
  normalize_existing — prepare + normalize candidate-local neutral metrics into evaluation.json.
  run_if_available   — normalize + best-effort solver execution when explicitly allowed.

Hard safety contract:
  - Baseline geometry/CAE artifacts are NEVER overwritten.
  - All outputs are candidate-local under candidates/<candidate_id>/.
  - Solver execution is disabled by default and only runs when explicitly requested + available.
  - Ranking refresh is explicit and optional; acceptance is never triggered.
"""
from __future__ import annotations

import copy
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.design_study import DESIGN_STUDY_PROBLEM_PATH
from aieng.converters.design_study_evaluation import evaluate_design_study_candidate
from aieng.converters.design_study_execution import CANDIDATE_WORKSPACE_ROOT
from aieng.converters.design_study_ranking import rank_design_study_candidates

CANDIDATE_CAE_EVALUATION_REQUEST_REL = "analysis/cae_evaluation_request.json"
CANDIDATE_CAE_DIAGNOSTICS_REL = "diagnostics/cae_evaluation_request.json"
CANDIDATE_CAE_SETUP_REL = "simulation/setup.yaml"
CANDIDATE_CAE_MAPPING_REL = "simulation/cae_mapping.json"
CANDIDATE_CAE_EXECUTION_DIAG_REL = "diagnostics/cae_execution.json"
CANDIDATE_SOLVER_INPUT_REL = "simulation/candidate_solver_input.inp"

# Baseline CAE paths that may be copied/adapted
BASELINE_SETUP_PATH = "simulation/setup.yaml"
BASELINE_CAE_MAPPING_PATH = "simulation/cae_mapping.json"
BASELINE_STEP_PATHS = ("geometry/generated.step", "geometry/model.step", "geometry/part.step")


# ── helpers ───────────────────────────────────────────────────────────────────


def _sanitize_id(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "candidate"))
    return s.strip("._") or "candidate"


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    try:
        return json.loads(zf.read(name).decode("utf-8"))
    except Exception:
        return None


def _read_text(zf: zipfile.ZipFile, name: str, names: set[str]) -> str | None:
    if name not in names:
        return None
    try:
        return zf.read(name).decode("utf-8")
    except Exception:
        return None


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".dscae.tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename not in members:
                    dst.writestr(item, src.read(item.filename))
            for name, data in members.items():
                dst.writestr(name, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── setup derivation ──────────────────────────────────────────────────────────


def _derive_candidate_cae_setup(
    package_path: Path,
    sid: str,
    names: set[str],
    zf: zipfile.ZipFile,
) -> tuple[dict[str, Any], dict[str, bytes], list[str]]:
    """Copy baseline CAE setup into candidate-local paths where safe.

    Returns (diagnostics, members_to_write, warnings).
    """
    ws = f"{CANDIDATE_WORKSPACE_ROOT}{sid}/"
    warnings: list[str] = []
    members: dict[str, bytes] = {}

    setup_text = _read_text(zf, BASELINE_SETUP_PATH, names)
    mapping_text = _read_text(zf, BASELINE_CAE_MAPPING_PATH, names)

    if setup_text is None:
        return {
            "status": "needs_user_input",
            "reason": f"baseline {BASELINE_SETUP_PATH} not found — cannot derive candidate-local CAE setup",
            "setup_derived": False,
        }, members, warnings

    # Copy setup to candidate-local path
    members[f"{ws}{CANDIDATE_CAE_SETUP_REL}"] = setup_text.encode()

    if mapping_text is not None:
        members[f"{ws}{CANDIDATE_CAE_MAPPING_REL}"] = mapping_text.encode()
    else:
        warnings.append("baseline simulation/cae_mapping.json not found — candidate-local mapping absent")

    # Warn about topology refs since candidate geometry may differ from baseline
    warnings.append(
        "candidate geometry may differ from baseline — topology refs / face IDs in CAE mapping "
        "should be re-verified before solver execution"
    )

    diagnostics = {
        "status": "derived",
        "setup_derived": True,
        "mapping_derived": mapping_text is not None,
        "source_setup": BASELINE_SETUP_PATH,
        "source_mapping": BASELINE_CAE_MAPPING_PATH,
        "candidate_setup": f"{ws}{CANDIDATE_CAE_SETUP_REL}",
        "candidate_mapping": f"{ws}{CANDIDATE_CAE_MAPPING_REL}" if mapping_text else None,
        "warnings": warnings,
    }
    return diagnostics, members, warnings


# ── solver execution (best-effort, conservative) ──────────────────────────────


def _try_run_candidate_solver(
    package_path: Path,
    sid: str,
    names: set[str],
    zf: zipfile.ZipFile,
    allow_solver_execution: bool,
) -> tuple[dict[str, Any], dict[str, bytes], list[str]]:
    """Best-effort solver run for candidate geometry.

    v0 is intentionally conservative: solver execution is skipped by default.
    If allow_solver_execution is True but the runner is unavailable, honest
    skipped diagnostics are returned.
    """
    ws = f"{CANDIDATE_WORKSPACE_ROOT}{sid}/"
    warnings: list[str] = []
    members: dict[str, bytes] = {}

    if not allow_solver_execution:
        warnings.append("allow_solver_execution is false (default) — solver execution disabled")
        return {
            "status": "skipped",
            "reason": "allow_solver_execution is false (default) — solver execution disabled",
            "solver_executed": False,
        }, members, warnings

    # Check candidate workspace has derived geometry
    candidate_shape_ir = _read_json(zf, f"{ws}geometry/shape_ir.json", names)
    if candidate_shape_ir is None:
        warnings.append("candidate Shape IR not found — cannot compile geometry for solver")
        return {
            "status": "skipped",
            "reason": "candidate Shape IR not found — cannot compile geometry for solver",
            "solver_executed": False,
        }, members, warnings

    # Check candidate-local setup exists (must have been derived first)
    candidate_setup = _read_text(zf, f"{ws}{CANDIDATE_CAE_SETUP_REL}", names)
    if candidate_setup is None:
        warnings.append("candidate-local CAE setup not found — run prepare_only first")
        return {
            "status": "skipped",
            "reason": "candidate-local CAE setup not found — run prepare_only first",
            "solver_executed": False,
        }, members, warnings

    # v0: honest skipped — full solver integration would require:
    #   1. Compile candidate Shape IR to STEP in a throwaway copy
    #   2. Generate mesh + solver deck for candidate geometry
    #   3. Run solver
    #   4. Normalize results back to candidate-local paths
    # This is future work; v0 records the intent and skips safely.
    warnings.append(
        "run_if_available mode requested solver execution, but v0 solver integration "
        "is best-effort/skipped. Candidate-local setup is prepared; solver execution "
        "requires explicit v1 integration with the mesh+deck+run pipeline."
    )
    return {
        "status": "skipped",
        "reason": "v0 solver integration is best-effort — candidate-local setup prepared, solver not run",
        "solver_executed": False,
        "capabilities_needed": [
            "compile candidate Shape IR to STEP",
            "generate candidate-local mesh and solver deck",
            "run solver on candidate geometry",
            "normalize candidate-local solver outputs",
        ],
    }, members, warnings


# ── main entry ────────────────────────────────────────────────────────────────


def request_design_study_candidate_cae_evaluation(
    package_path: str | Path,
    candidate_id: str,
    *,
    mode: str = "prepare_only",
    allow_solver_execution: bool = False,
    allow_solver_deck_generation: bool = True,
    allow_ranking_refresh: bool = False,
    requested_by: str = "agent",
    load_case_ids: list[str] | None = None,
    constraints_to_evaluate: list[str] | None = None,
) -> dict[str, Any]:
    """Explicitly request CAE evaluation for one design-study candidate.

    Writes candidate-local artifacts only; baseline geometry and CAE setup are never
    overwritten. Solver execution is disabled by default.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "failed", "reason": "package not found"}

    sid = _sanitize_id(candidate_id)
    ws = f"{CANDIDATE_WORKSPACE_ROOT}{sid}/"
    request_path = f"{ws}{CANDIDATE_CAE_EVALUATION_REQUEST_REL}"
    diag_path = f"{ws}{CANDIDATE_CAE_DIAGNOSTICS_REL}"

    # ── load package state ─────────────────────────────────────────────────────
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            candidate_exists = any(n.startswith(ws) for n in names)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    if not candidate_exists:
        request_doc = _build_request_doc(
            sid, requested_by, mode, allow_solver_execution, allow_solver_deck_generation,
            allow_ranking_refresh, load_case_ids, constraints_to_evaluate,
            status="failed", reason="candidate workspace not found",
        )
        diag_doc = _build_diag_doc(
            sid, request_doc, setup_status="failed", deck_status="skipped",
            solver_status="skipped", normalization_status="failed",
            evaluation_status="failed", ranking_refresh_status="skipped",
            warnings=[], reason="candidate workspace not found",
        )
        _replace_members(package_path, {
            request_path: _dumps(request_doc),
            diag_path: _dumps(diag_doc),
        })
        return {
            "status": "failed",
            "candidate_id": sid,
            "reason": f"candidate workspace not found at {ws}",
            "baseline_modified": False,
        }

    # ── build request artifact ─────────────────────────────────────────────────
    request_doc = _build_request_doc(
        sid, requested_by, mode, allow_solver_execution, allow_solver_deck_generation,
        allow_ranking_refresh, load_case_ids, constraints_to_evaluate,
        status="ok", reason="request accepted",
    )
    members: dict[str, bytes] = {request_path: _dumps(request_doc)}

    # ── Part C: derive candidate-local CAE setup ───────────────────────────────
    with zipfile.ZipFile(package_path, "r") as zf:
        setup_diag, setup_members, setup_warnings = _derive_candidate_cae_setup(
            package_path, sid, names, zf
        )
    members.update(setup_members)

    setup_status = setup_diag["status"]
    if setup_status == "needs_user_input":
        request_doc["status"] = "needs_user_input"
        diag_doc = _build_diag_doc(
            sid, request_doc, setup_status=setup_status, deck_status="skipped",
            solver_status="skipped", normalization_status="skipped",
            evaluation_status="skipped", ranking_refresh_status="skipped",
            warnings=setup_warnings, reason=setup_diag["reason"],
        )
        members[request_path] = _dumps(request_doc)
        members[diag_path] = _dumps(diag_doc)
        _replace_members(package_path, members)
        return {
            "status": "needs_user_input",
            "candidate_id": sid,
            "setup_status": setup_status,
            "reason": setup_diag["reason"],
            "baseline_modified": False,
            "artifacts": [request_path, diag_path],
        }

    # ── Part E/F: optional solver execution (best-effort) ──────────────────────
    solver_diag: dict[str, Any] = {"status": "skipped", "solver_executed": False}
    solver_members: dict[str, bytes] = {}
    solver_warnings: list[str] = []

    if mode in ("normalize_existing", "run_if_available"):
        with zipfile.ZipFile(package_path, "r") as zf:
            solver_diag, solver_members, solver_warnings = _try_run_candidate_solver(
                package_path, sid, names, zf, allow_solver_execution
            )
        members.update(solver_members)

    deck_status = "skipped"
    if allow_solver_deck_generation and mode == "run_if_available":
        deck_status = "skipped"
        solver_warnings.append(
            "solver deck generation is best-effort in v0 — skipped pending v1 integration"
        )

    # ── Part D/G: normalize existing candidate-local results + build evaluation ─
    eval_result = evaluate_design_study_candidate(package_path, sid)
    normalization_status = eval_result.get("status", "failed")
    evaluation_status = eval_result.get("evaluation_status", "unknown")

    # If the evaluation found proxy/assembly evidence, note it
    all_warnings = setup_warnings + solver_warnings
    if eval_result.get("confidence") == "low":
        all_warnings.append("candidate evaluation confidence is low — review metrics before trusting")

    # ── Part G: optional ranking refresh ───────────────────────────────────────
    ranking_refresh_status = "skipped"
    if allow_ranking_refresh:
        rank_result = rank_design_study_candidates(package_path)
        ranking_refresh_status = rank_result.get("status", "failed")

    # ── Part I: write diagnostics ──────────────────────────────────────────────
    diag_doc = _build_diag_doc(
        sid, request_doc, setup_status=setup_status, deck_status=deck_status,
        solver_status=solver_diag.get("status", "skipped"),
        normalization_status=normalization_status,
        evaluation_status=evaluation_status,
        ranking_refresh_status=ranking_refresh_status,
        warnings=all_warnings,
        reason="candidate-local CAE evaluation request completed",
    )
    members[request_path] = _dumps(request_doc)
    members[diag_path] = _dumps(diag_doc)

    # Ensure evaluation/report artifacts are listed
    artifacts = [request_path, diag_path]
    if eval_result.get("artifacts"):
        artifacts.extend(eval_result["artifacts"])

    _replace_members(package_path, members)

    return {
        "status": "ok",
        "candidate_id": sid,
        "mode": mode,
        "setup_status": setup_status,
        "deck_status": deck_status,
        "solver_status": solver_diag.get("status", "skipped"),
        "normalization_status": normalization_status,
        "evaluation_status": evaluation_status,
        "ranking_refresh_status": ranking_refresh_status,
        "baseline_modified": False,
        "artifacts": artifacts,
        "warnings": all_warnings,
    }


# ── artifact builders ─────────────────────────────────────────────────────────


def _build_request_doc(
    candidate_id: str,
    requested_by: str,
    mode: str,
    allow_solver_execution: bool,
    allow_solver_deck_generation: bool,
    allow_ranking_refresh: bool,
    load_case_ids: list[str] | None,
    constraints_to_evaluate: list[str] | None,
    status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "format": "aieng.design_study.candidate_cae_evaluation_request.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "candidate_id": candidate_id,
        "requested_by": requested_by,
        "mode": mode,
        "source_problem": DESIGN_STUDY_PROBLEM_PATH,
        "source_candidate": f"patches/design_candidates/{candidate_id}.json",
        "candidate_geometry": f"{CANDIDATE_WORKSPACE_ROOT}{candidate_id}/geometry/shape_ir.json",
        "load_case_ids": load_case_ids or [],
        "constraints_to_evaluate": constraints_to_evaluate or [],
        "allow_solver_execution": allow_solver_execution,
        "allow_solver_deck_generation": allow_solver_deck_generation,
        "allow_ranking_refresh": allow_ranking_refresh,
        "status": status,
        "reason": reason,
        "limitations": [
            "v0 is candidate-local only — baseline artifacts are never overwritten.",
            "Solver execution is disabled by default and best-effort when enabled.",
            "Candidate geometry may differ from baseline — topology refs should be re-verified.",
            "Setup derivation copies baseline configuration; adaptive mapping is future work.",
        ],
        "baseline_modified": False,
    }


def _build_diag_doc(
    candidate_id: str,
    request_doc: dict[str, Any],
    *,
    setup_status: str,
    deck_status: str,
    solver_status: str,
    normalization_status: str,
    evaluation_status: str,
    ranking_refresh_status: str,
    warnings: list[str],
    reason: str,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    ws = f"{CANDIDATE_WORKSPACE_ROOT}{candidate_id}/"
    return {
        "format": "aieng.design_study.candidate_cae_evaluation_diagnostics",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "candidate_id": candidate_id,
        "request_summary": {
            "mode": request_doc.get("mode"),
            "allow_solver_execution": request_doc.get("allow_solver_execution"),
            "allow_solver_deck_generation": request_doc.get("allow_solver_deck_generation"),
            "allow_ranking_refresh": request_doc.get("allow_ranking_refresh"),
        },
        "artifact_paths_checked": [
            DESIGN_STUDY_PROBLEM_PATH,
            f"{ws}geometry/shape_ir.json",
            BASELINE_SETUP_PATH,
            BASELINE_CAE_MAPPING_PATH,
        ],
        "setup_derivation_status": setup_status,
        "deck_generation_status": deck_status,
        "solver_execution_status": solver_status,
        "normalization_status": normalization_status,
        "evaluation_status": evaluation_status,
        "ranking_refresh_status": ranking_refresh_status,
        "candidate_local_only": True,
        "baseline_modified": False,
        "warnings": warnings,
        "errors": errors or [],
        "reason": reason,
        "limitations": [
            "Diagnostics are evidence-only; they do not certify physical correctness.",
            "Solver execution skipped in v0 unless future integration is enabled.",
        ],
    }
