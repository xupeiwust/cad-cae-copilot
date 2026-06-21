"""Design study candidate ACCEPTANCE v0 (PR4).

Explicitly accepts a ranked design-study candidate into a derived accepted workspace.
Does NOT overwrite baseline geometry. Does NOT auto-promote. Acceptance is advisory only.

Hard safety contract:
  - Baseline geometry is NEVER overwritten.
  - No candidate is auto-accepted.
  - Acceptance is explicit and gated by eligibility checks.
  - Unsafe candidates are rejected unless override_unsafe is explicitly set.
  - Production approval is NOT claimed.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.design_study import DESIGN_STUDY_PROBLEM_PATH
from aieng.converters.design_study_execution import (
    CANDIDATE_WORKSPACE_ROOT,
    DESIGN_STUDY_ITERATIONS_PATH,
)
from aieng.converters.design_study_ranking import (
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    FEAS_FAILED,
    FEAS_INFEASIBLE,
    FEAS_UNKNOWN,
)

DESIGN_STUDY_ACCEPTANCE_PATH = "analysis/design_study_acceptance.json"
DESIGN_STUDY_ACCEPTANCE_REPORT_PATH = "diagnostics/design_study_acceptance_report.json"
ACCEPTED_WORKSPACE_ROOT = "accepted/"

# acceptance status
ACC_ACCEPTED = "accepted"
ACC_REJECTED = "rejected"
ACC_NEEDS_INPUT = "needs_user_input"
ACC_FAILED = "failed"


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:
            return None
    return None


def _sanitize_cid(candidate_id: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(candidate_id or "candidate"))
    return s.strip("._") or "candidate"


# ── eligibility checks ────────────────────────────────────────────────────────

def _check_eligibility(
    ranking: dict[str, Any] | None,
    candidate_id: str,
    iteration: dict[str, Any] | None,
    override_unsafe: bool,
) -> dict[str, Any]:
    """Check whether a candidate is eligible for acceptance.

    Returns a dict with:
      - eligible: bool
      - status: accepted | rejected | needs_user_input
      - reasons: list[str]
      - warnings: list[str]
    """
    reasons: list[str] = []
    warnings: list[str] = []

    if ranking is None:
        reasons.append("ranking artifact not found — run design-study ranking first")
        return {
            "eligible": False,
            "status": ACC_NEEDS_INPUT,
            "reasons": reasons,
            "warnings": warnings,
        }

    candidates = ranking.get("candidates") or []
    by_id = {c["candidate_id"]: c for c in candidates if isinstance(c, dict)}
    ranked_cand = by_id.get(candidate_id)

    if ranked_cand is None:
        reasons.append(f"candidate '{candidate_id}' not found in ranking")
        return {
            "eligible": False,
            "status": ACC_REJECTED,
            "reasons": reasons,
            "warnings": warnings,
        }

    feasibility = ranked_cand.get("feasibility")
    if feasibility in (FEAS_FAILED, FEAS_INFEASIBLE, FEAS_UNKNOWN):
        reasons.append(f"candidate feasibility is '{feasibility}' — cannot accept")
        return {
            "eligible": False,
            "status": ACC_REJECTED,
            "reasons": reasons,
            "warnings": warnings,
        }

    safe_to_accept = ranking.get("safe_to_accept", False)
    best_id = ranking.get("best_candidate_id")
    is_best = best_id == candidate_id

    # Rule: only the best candidate can be accepted by default.
    # Non-best candidates always require override_unsafe.
    if not is_best and not override_unsafe:
        reasons.append(
            f"candidate is not best_candidate_id (best={best_id}) — "
            f"use override_unsafe=true to force"
        )
        return {
            "eligible": False,
            "status": ACC_NEEDS_INPUT,
            "reasons": reasons,
            "warnings": warnings,
        }

    if not is_best and override_unsafe:
        warnings.append(
            "override_unsafe enabled — accepting candidate that is not best_candidate_id"
        )

    # Best candidate must also be safe_to_accept, unless overridden
    if is_best and not safe_to_accept and not override_unsafe:
        reasons.append(
            f"candidate is best_candidate_id but safe_to_accept=false — "
            f"requires override_unsafe=true or more evaluation"
        )
        return {
            "eligible": False,
            "status": ACC_NEEDS_INPUT,
            "reasons": reasons,
            "warnings": warnings,
        }

    if is_best and not safe_to_accept and override_unsafe:
        warnings.append(
            "override_unsafe enabled — accepting best_candidate_id that is not safe_to_accept"
        )

    # Check iteration record exists
    if iteration is None:
        reasons.append(f"candidate '{candidate_id}' has no iteration record")
        return {
            "eligible": False,
            "status": ACC_REJECTED,
            "reasons": reasons,
            "warnings": warnings,
        }

    reasons.append("candidate is eligible for acceptance")
    return {
        "eligible": True,
        "status": ACC_ACCEPTED,
        "reasons": reasons,
        "warnings": warnings,
    }


# ── artifact builders ─────────────────────────────────────────────────────────

def _build_acceptance_artifact(
    candidate_id: str,
    accepted_by: str,
    reasoning: str | None,
    ranking: dict[str, Any] | None,
    problem: dict[str, Any] | None,
    accepted_artifacts: list[str],
) -> dict[str, Any]:
    return {
        "format": "aieng.design_study.acceptance.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": ACC_ACCEPTED,
        "accepted_candidate_id": candidate_id,
        "accepted_by": accepted_by,
        "reasoning": reasoning or "explicit acceptance via design_study_acceptance",
        "source_ranking": DESIGN_STUDY_CANDIDATE_RANKING_PATH,
        "source_problem": DESIGN_STUDY_PROBLEM_PATH,
        "source_candidate": f"patches/design_candidates/{candidate_id}.json",
        "accepted_artifacts": accepted_artifacts,
        "baseline_modified": False,
        "promotion_mode": "derived_only",
        "limitations": [
            "Acceptance is advisory — not production certification.",
            "Baseline geometry is never overwritten.",
            "Accepted candidate is a derived design artifact only.",
            "Human/agent review is still required before manufacturing.",
        ],
    }


def _build_rejection_artifact(
    candidate_id: str,
    accepted_by: str,
    reasoning: str | None,
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    return {
        "format": "aieng.design_study.acceptance.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": eligibility["status"],
        "accepted_candidate_id": None,
        "accepted_by": accepted_by,
        "reasoning": reasoning or "acceptance rejected by eligibility checks",
        "source_ranking": DESIGN_STUDY_CANDIDATE_RANKING_PATH,
        "source_problem": DESIGN_STUDY_PROBLEM_PATH,
        "source_candidate": f"patches/design_candidates/{candidate_id}.json",
        "accepted_artifacts": [],
        "baseline_modified": False,
        "promotion_mode": "derived_only",
        "limitations": [
            "Acceptance is advisory — not production certification.",
            "Candidate was not accepted; baseline remains unchanged.",
        ],
        "errors": eligibility.get("reasons", []),
        "warnings": eligibility.get("warnings", []),
    }


def _build_acceptance_report(
    candidate_id: str,
    eligibility: dict[str, Any],
    ranking: dict[str, Any] | None,
    ranked_cand: dict[str, Any] | None,
    iteration: dict[str, Any] | None,
    artifact_checks: dict[str, bool],
    accepted: bool,
) -> dict[str, Any]:
    return {
        "format": "aieng.design_study_acceptance_report",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "candidate_id": candidate_id,
        "eligibility_checks": {
            "ranking_exists": ranking is not None,
            "candidate_in_ranking": ranked_cand is not None,
            "feasibility": ranked_cand.get("feasibility") if ranked_cand else None,
            "safe_to_accept": ranking.get("safe_to_accept") if ranking else None,
            "is_best_candidate": (
                ranking.get("best_candidate_id") == candidate_id if ranking else False
            ),
            "iteration_exists": iteration is not None,
            "eligible": eligibility["eligible"],
        },
        "ranking_status": ranking.get("status") if ranking else None,
        "candidate_feasibility": ranked_cand.get("feasibility") if ranked_cand else None,
        "candidate_confidence": ranked_cand.get("confidence") if ranked_cand else None,
        "candidate_score": ranked_cand.get("score") if ranked_cand else None,
        "artifact_existence_checks": artifact_checks,
        "acceptance_status": eligibility["status"],
        "accepted": accepted,
        "errors": eligibility.get("reasons", []),
        "warnings": eligibility.get("warnings", []),
        "provenance": {
            "created_by": "aieng.design_study_acceptance",
            "baseline_modified": False,
        },
    }


# ── package I/O ───────────────────────────────────────────────────────────────

def _rewrite_package_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".dsaccept.tmp.aieng")
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


# ── main entry ────────────────────────────────────────────────────────────────

def accept_design_study_candidate(
    package_path: str | Path,
    candidate_id: str,
    *,
    accepted_by: str = "agent",
    reasoning: str | None = None,
    override_unsafe: bool = False,
) -> dict[str, Any]:
    """Explicitly accept ONE ranked design-study candidate into a derived workspace.

    Reads the ranking artifact and candidate workspace, copies the candidate's derived
    geometry into ``accepted/<candidate_id>/``, and writes acceptance + diagnostics.

    Does NOT overwrite baseline geometry. Does NOT auto-promote. Does NOT recompile.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": "failed", "reason": "package not found"}

    sid = _sanitize_cid(candidate_id)
    ws = f"{ACCEPTED_WORKSPACE_ROOT}{sid}/"

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            ranking = _read_json(zf, DESIGN_STUDY_CANDIDATE_RANKING_PATH, names)
            if not isinstance(ranking, dict):
                ranking = None
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            if not isinstance(problem, dict):
                problem = None
            iterations_doc = _read_json(zf, DESIGN_STUDY_ITERATIONS_PATH, names)
            iterations = [i for i in (iterations_doc.get("iterations") or [])
                          if isinstance(i, dict)] if isinstance(iterations_doc, dict) else []
            iteration_by_id = {i.get("candidate_id"): i for i in iterations}
            iteration = iteration_by_id.get(sid)

            # Check candidate workspace artifact existence
            cand_ws = f"{CANDIDATE_WORKSPACE_ROOT}{sid}/"
            artifact_checks = {
                "patch": f"{cand_ws}patch.json" in names,
                "shape_ir": f"{cand_ws}geometry/shape_ir.json" in names,
                "evaluation": f"{cand_ws}analysis/evaluation.json" in names,
            }
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    # Eligibility
    eligibility = _check_eligibility(ranking, sid, iteration, override_unsafe)

    # Also require candidate workspace artifacts to exist
    if eligibility["eligible"]:
        missing_artifacts = [k for k, v in artifact_checks.items() if not v]
        if missing_artifacts:
            eligibility["eligible"] = False
            eligibility["status"] = ACC_REJECTED
            eligibility["reasons"].append(
                f"candidate workspace missing required artifacts: {missing_artifacts}"
            )

    ranked_cand = None
    if ranking:
        candidates = ranking.get("candidates") or []
        by_id = {c["candidate_id"]: c for c in candidates if isinstance(c, dict)}
        ranked_cand = by_id.get(sid)

    if not eligibility["eligible"]:
        acceptance = _build_rejection_artifact(sid, accepted_by, reasoning, eligibility)
        report = _build_acceptance_report(
            sid, eligibility, ranking, ranked_cand, iteration, artifact_checks, accepted=False
        )
        members = {
            DESIGN_STUDY_ACCEPTANCE_PATH: _dumps(acceptance),
            DESIGN_STUDY_ACCEPTANCE_REPORT_PATH: _dumps(report),
        }
        _rewrite_package_members(package_path, members)
        return {
            "status": eligibility["status"],
            "candidate_id": sid,
            "accepted": False,
            "reasons": eligibility.get("reasons", []),
            "warnings": eligibility.get("warnings", []),
            "artifacts": [DESIGN_STUDY_ACCEPTANCE_PATH, DESIGN_STUDY_ACCEPTANCE_REPORT_PATH],
        }

    # ── eligible: copy candidate artifacts into accepted workspace ─────────────
    members: dict[str, bytes] = {}
    accepted_artifacts: list[str] = []

    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            names = set(zf.namelist())
            cand_ws = f"{CANDIDATE_WORKSPACE_ROOT}{sid}/"

            # Copy patch
            patch_path = f"{cand_ws}patch.json"
            if patch_path in names:
                members[f"{ws}patch.json"] = zf.read(patch_path)
                accepted_artifacts.append(f"{ws}patch.json")

            # Copy derived Shape IR
            shape_ir_path = f"{cand_ws}geometry/shape_ir.json"
            if shape_ir_path in names:
                members[f"{ws}geometry/shape_ir.json"] = zf.read(shape_ir_path)
                accepted_artifacts.append(f"{ws}geometry/shape_ir.json")

            # Copy evaluation
            eval_path = f"{cand_ws}analysis/evaluation.json"
            if eval_path in names:
                members[f"{ws}analysis/evaluation.json"] = zf.read(eval_path)
                accepted_artifacts.append(f"{ws}analysis/evaluation.json")

            # Write acceptance provenance
            provenance = {
                "format": "aieng.design_study_acceptance_provenance",
                "format_version": FORMAT_VERSION,
                "accepted_candidate_id": sid,
                "source_ranking": DESIGN_STUDY_CANDIDATE_RANKING_PATH,
                "source_problem": DESIGN_STUDY_PROBLEM_PATH,
                "source_candidate_patch": f"patches/design_candidates/{sid}.json",
                "source_candidate_workspace": cand_ws,
                "accepted_by": accepted_by,
                "reasoning": reasoning or "explicit acceptance via design_study_acceptance",
                "baseline_modified": False,
            }
            members[f"{ws}provenance/acceptance.json"] = _dumps(provenance)
            accepted_artifacts.append(f"{ws}provenance/acceptance.json")
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": f"artifact copy failed: {type(exc).__name__}: {exc}"}

    acceptance = _build_acceptance_artifact(
        sid, accepted_by, reasoning, ranking, problem, accepted_artifacts
    )
    report = _build_acceptance_report(
        sid, eligibility, ranking, ranked_cand, iteration, artifact_checks, accepted=True
    )

    members[DESIGN_STUDY_ACCEPTANCE_PATH] = _dumps(acceptance)
    members[DESIGN_STUDY_ACCEPTANCE_REPORT_PATH] = _dumps(report)

    _rewrite_package_members(package_path, members)

    return {
        "status": "ok",
        "candidate_id": sid,
        "accepted": True,
        "accepted_workspace": ws,
        "baseline_modified": False,
        "artifacts": [DESIGN_STUDY_ACCEPTANCE_PATH, DESIGN_STUDY_ACCEPTANCE_REPORT_PATH] + accepted_artifacts,
    }
