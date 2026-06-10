"""Optimization study summary report (#43).

A single, reproducible report that aggregates the whole Phase-1 optimization
study from artifacts already present in the ``.aieng`` package — problem
definition, variables / objective / constraints, all candidates with their
metrics, the ranking, failed candidates, and the advisory recommendation /
acceptance state.

It is a pure READ + AGGREGATE step: it reads existing artifacts and writes
``diagnostics/optimization_report.json``. It never executes/evaluates/ranks
candidates, never runs CAE, and never modifies the baseline. Because it derives
solely from on-disk artifacts, the report is reconstructable at any time.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION

# Source artifacts (all optional — the report records what is present vs missing)
DESIGN_STUDY_PROBLEM_PATH = "analysis/design_study_problem.json"
OPTIMIZATION_STUDY_PATH = "analysis/optimization_study.json"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"
OPTIMIZATION_OBJECTIVES_PATH = "analysis/optimization_objectives.json"
OPTIMIZATION_CONSTRAINTS_PATH = "analysis/optimization_constraints.json"
OPTIMIZATION_DECISION_LOG_PATH = "analysis/optimization_decision_log.json"
DESIGN_STUDY_ITERATIONS_PATH = "analysis/design_study_iterations.json"
DESIGN_STUDY_RANKING_PATH = "analysis/design_study_candidate_ranking.json"
DESIGN_STUDY_SCORING_REPORT_PATH = "diagnostics/design_study_scoring_report.json"
OPTIMIZATION_RECOMMENDATION_PATH = "analysis/optimization_recommendation.json"
DESIGN_STUDY_ACCEPTANCE_PATH = "analysis/design_study_acceptance.json"
CANDIDATE_WORKSPACE_ROOT = "candidates/"
CANDIDATE_EVALUATION_REL = "analysis/evaluation.json"

OPTIMIZATION_REPORT_PATH = "diagnostics/optimization_report.json"
OPTIMIZATION_REPORT_FORMAT = "aieng.optimization_report"


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:  # noqa: BLE001
            return None
    return None


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".optreport.tmp.aieng")
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


def _sanitize_cid(cid: str) -> str:
    return str(cid or "").replace("..", "").strip("/")


def _candidate_rows(
    zf: zipfile.ZipFile,
    names: set[str],
    iterations: list[dict[str, Any]],
    ranking_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build per-candidate summary rows and the failed-candidate subset.

    Candidate ids are the union of those seen in iterations, in the ranking, and
    as on-disk workspaces — so nothing is dropped if one source lags another.
    """
    ids: list[str] = []
    seen: set[str] = set()

    def _add(cid: str) -> None:
        cid = _sanitize_cid(cid)
        if cid and cid not in seen:
            seen.add(cid)
            ids.append(cid)

    iter_by_id: dict[str, dict[str, Any]] = {}
    for it in iterations:
        cid = _sanitize_cid(it.get("candidate_id", ""))
        if cid:
            iter_by_id[cid] = it
            _add(cid)
    for cid in ranking_by_id:
        _add(cid)
    for name in names:
        if name.startswith(CANDIDATE_WORKSPACE_ROOT) and name != CANDIDATE_WORKSPACE_ROOT:
            _add(name[len(CANDIDATE_WORKSPACE_ROOT):].split("/", 1)[0])

    rows: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for cid in ids:
        ranked = ranking_by_id.get(cid) or {}
        it = iter_by_id.get(cid) or {}
        ev = _read_json(zf, f"{CANDIDATE_WORKSPACE_ROOT}{cid}/{CANDIDATE_EVALUATION_REL}", names)
        ev = ev if isinstance(ev, dict) else {}
        metrics = ev.get("metrics") if isinstance(ev.get("metrics"), dict) else {}
        execution_status = it.get("execution_status")
        feasibility = ranked.get("feasibility") or ev.get("feasibility")
        row = {
            "candidate_id": cid,
            "rank": ranked.get("rank"),
            "execution_status": execution_status,
            "evaluation_status": ev.get("evaluation_status"),
            "feasibility": feasibility,
            "confidence": ranked.get("confidence") or ev.get("confidence"),
            "score": ranked.get("score"),
            "recommendation": ranked.get("recommendation") or it.get("recommendation"),
            "metrics": metrics,
            "constraint_violations": ranked.get("constraint_violations") or [],
            "objective_delta": ranked.get("objective_delta"),
        }
        rows.append(row)
        if feasibility == "failed" or execution_status in ("compile_failed", "failed"):
            failed.append(
                {
                    "candidate_id": cid,
                    "execution_status": execution_status,
                    "feasibility": feasibility,
                    "reasons": ranked.get("reasons") or [],
                }
            )
    return rows, failed


def build_optimization_report(package_path: str | Path) -> dict[str, Any]:
    """Aggregate the optimization study into diagnostics/optimization_report.json.

    Returns a summary dict. The full report artifact is written to the package.
    Read-only with respect to engineering state — no candidate is executed,
    evaluated, ranked, or accepted, and the baseline is never modified.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {"status": "error", "code": "package_not_found", "message": "package not found",
                "baseline_modified": False}

    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            problem = _read_json(zf, DESIGN_STUDY_PROBLEM_PATH, names)
            study = _read_json(zf, OPTIMIZATION_STUDY_PATH, names)
            variables = _read_json(zf, OPTIMIZATION_VARIABLES_PATH, names)
            objectives = _read_json(zf, OPTIMIZATION_OBJECTIVES_PATH, names)
            constraints = _read_json(zf, OPTIMIZATION_CONSTRAINTS_PATH, names)
            decision_log = _read_json(zf, OPTIMIZATION_DECISION_LOG_PATH, names)
            iterations_doc = _read_json(zf, DESIGN_STUDY_ITERATIONS_PATH, names)
            ranking = _read_json(zf, DESIGN_STUDY_RANKING_PATH, names)
            scoring = _read_json(zf, DESIGN_STUDY_SCORING_REPORT_PATH, names)
            recommendation = _read_json(zf, OPTIMIZATION_RECOMMENDATION_PATH, names)
            acceptance = _read_json(zf, DESIGN_STUDY_ACCEPTANCE_PATH, names)

            iterations = (
                [i for i in (iterations_doc.get("iterations") or []) if isinstance(i, dict)]
                if isinstance(iterations_doc, dict) else []
            )
            ranking_candidates = (
                [c for c in (ranking.get("candidates") or []) if isinstance(c, dict)]
                if isinstance(ranking, dict) else []
            )
            ranking_by_id = {
                _sanitize_cid(c.get("candidate_id", "")): c
                for c in ranking_candidates if c.get("candidate_id")
            }
            candidate_rows, failed = _candidate_rows(zf, names, iterations, ranking_by_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "read_failed",
                "message": f"{type(exc).__name__}: {exc}", "baseline_modified": False}

    # Which expected stages produced an artifact (transparency, not a gate).
    sources_present = {
        "problem": isinstance(problem, dict),
        "optimization_study": isinstance(study, dict),
        "variables": isinstance(variables, dict),
        "objectives": isinstance(objectives, dict),
        "constraints": isinstance(constraints, dict),
        "decision_log": isinstance(decision_log, dict),
        "iterations": bool(iterations),
        "ranking": isinstance(ranking, dict),
        "scoring_report": isinstance(scoring, dict),
        "recommendation": isinstance(recommendation, dict),
        "acceptance": isinstance(acceptance, dict),
    }
    missing_stages = [k for k, v in sources_present.items() if not v]

    if not isinstance(problem, dict) and not candidate_rows:
        return {
            "status": "insufficient_data",
            "code": "no_study",
            "message": "no design-study problem or candidates found to report on",
            "baseline_modified": False,
        }

    # feasibility / status tallies
    feasibility_tally: dict[str, int] = {}
    for row in candidate_rows:
        key = row.get("feasibility") or "unrated"
        feasibility_tally[key] = feasibility_tally.get(key, 0) + 1

    objective = None
    if isinstance(ranking, dict):
        objective = ranking.get("objective")
    if objective is None and isinstance(problem, dict):
        objective = problem.get("objective")

    decision_entries = (
        decision_log.get("entries") if isinstance(decision_log, dict) else None
    ) or []

    report = {
        "format": OPTIMIZATION_REPORT_FORMAT,
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "status": "ok",
        "problem": {
            "id": problem.get("id") if isinstance(problem, dict) else None,
            "objective": objective,
            "constraints": problem.get("constraints") if isinstance(problem, dict) else None,
            "variable_count": (
                len(problem.get("variables") or []) if isinstance(problem, dict) else None
            ),
        },
        "variables": (variables or {}).get("variables") if isinstance(variables, dict) else None,
        "objectives": (objectives or {}).get("objectives") if isinstance(objectives, dict) else None,
        "constraints": (constraints or {}).get("constraints") if isinstance(constraints, dict) else None,
        "candidate_count": len(candidate_rows),
        "candidates": candidate_rows,
        "failed_candidates": failed,
        "feasibility_summary": feasibility_tally,
        "ranking": {
            "best_candidate_id": ranking.get("best_candidate_id") if isinstance(ranking, dict) else None,
            "safe_to_accept": ranking.get("safe_to_accept") if isinstance(ranking, dict) else None,
            "next_action": ranking.get("next_action") if isinstance(ranking, dict) else None,
        },
        "recommendation": {
            "headline": recommendation.get("headline") if isinstance(recommendation, dict) else None,
            "recommended_candidate_id": (
                recommendation.get("recommended_candidate_id") if isinstance(recommendation, dict) else None
            ),
            "reason_codes": recommendation.get("reason_codes") if isinstance(recommendation, dict) else None,
            "advisory_only": True,
        },
        "acceptance": {
            "status": acceptance.get("status") if isinstance(acceptance, dict) else None,
            "accepted_candidate_id": (
                acceptance.get("accepted_candidate_id") if isinstance(acceptance, dict) else None
            ),
            "promotion_mode": acceptance.get("promotion_mode") if isinstance(acceptance, dict) else None,
        },
        "decision_log_entries": decision_entries,
        "sources_present": sources_present,
        "missing_stages": missing_stages,
        "honesty": {
            "advisory_only": True,
            "production_sign_off": False,
            "baseline_modified": False,
            "report_is_reconstructable_from_artifacts": True,
        },
        "baseline_modified": False,
        "claim_advancement": "none",
    }

    _replace_members(pkg, {OPTIMIZATION_REPORT_PATH: _dumps(report)})

    return {
        "status": "ok",
        "candidate_count": len(candidate_rows),
        "failed_candidate_count": len(failed),
        "best_candidate_id": report["ranking"]["best_candidate_id"],
        "accepted_candidate_id": report["acceptance"]["accepted_candidate_id"],
        "missing_stages": missing_stages,
        "baseline_modified": False,
        "artifacts": [OPTIMIZATION_REPORT_PATH],
    }
