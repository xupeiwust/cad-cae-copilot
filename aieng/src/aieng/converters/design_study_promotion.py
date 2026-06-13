"""Design-history branching + governed baseline promotion (v0, #202).

Makes design-study lineage first-class: explicit branches with parent/provenance,
an APPROVAL-GATED promotion that records who/why/what changed, and a rollback path.

Governance only — deterministic metadata. It never overwrites baseline geometry:
a "promotion" moves the governed ``current_baseline`` *pointer* to a derived
branch (whose geometry lives under ``accepted/<id>/``) and preserves the previous
baseline for rollback. Physical geometry swap is intentionally out of scope; the
baseline `.aieng` geometry artifacts are never mutated here.

Honesty boundary: acceptance stays advisory until a separately approved promotion
occurs; promotion is governance, **not** production certification.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from aieng import FORMAT_VERSION
from aieng.converters.design_study_acceptance import (
    ACC_ACCEPTED,
    DESIGN_STUDY_ACCEPTANCE_PATH,
)

DESIGN_HISTORY_PATH = "analysis/design_history.json"
BASELINE_BRANCH_ID = "baseline"

# operation status
OK = "ok"
NEEDS_INPUT = "needs_user_input"
REFUSED = "refused"


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name not in names:
        return None
    try:
        return json.loads(zf.read(name).decode("utf-8"))
    except Exception:
        return None


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".promo.tmp.aieng")
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


def _empty_history() -> dict[str, Any]:
    return {
        "format": "aieng.design_study.history.v0",
        "format_version": FORMAT_VERSION,
        "schema_version": "0.1",
        "current_baseline": {"branch_id": BASELINE_BRANCH_ID, "candidate_id": None},
        "branches": [],
        "promotions": [],
        "rollbacks": [],
        "honesty": {
            "baseline_geometry_overwritten": False,
            "acceptance_is_advisory": True,
            "promotion_is_certification": False,
            "note": "Branches/promotions are governance metadata; baseline `.aieng` geometry "
                    "is never overwritten. Acceptance is advisory until an approved promotion; "
                    "promotion is not production certification.",
        },
    }


def _load_history(package_path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None, set[str]]:
    """Return (history-or-None, acceptance-or-None, member_names). history defaults to empty."""
    with zipfile.ZipFile(package_path, "r") as zf:
        names = set(zf.namelist())
        history = _read_json(zf, DESIGN_HISTORY_PATH, names) or _empty_history()
        acceptance = _read_json(zf, DESIGN_STUDY_ACCEPTANCE_PATH, names)
    return history, acceptance, names


def _branch_by_id(history: dict[str, Any], branch_id: str) -> dict[str, Any] | None:
    for b in history.get("branches", []):
        if isinstance(b, dict) and b.get("branch_id") == branch_id:
            return b
    return None


def _candidate_is_accepted(acceptance: dict[str, Any] | None, candidate_id: str) -> bool:
    return bool(
        isinstance(acceptance, dict)
        and acceptance.get("status") == ACC_ACCEPTED
        and str(acceptance.get("accepted_candidate_id")) == str(candidate_id)
    )


def record_design_branch(
    package_path: str | Path,
    *,
    candidate_id: str,
    created_by: str,
    rationale: str,
    parent: str | None = None,
) -> dict[str, Any]:
    """Record an explicit design branch for an ACCEPTED candidate (parent/provenance).

    Refuses (no history change) if the candidate is not accepted — a branch must
    have a real derived artifact behind it.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": REFUSED, "reason": "package not found"}
    history, acceptance, _ = _load_history(package_path)

    if not _candidate_is_accepted(acceptance, candidate_id):
        return {"status": NEEDS_INPUT, "reason": "candidate_not_accepted",
                "detail": "record a branch only for a candidate accepted via design_study_acceptance",
                "candidate_id": candidate_id, "baseline_modified": False}

    branch_id = f"branch_{candidate_id}"
    parent_id = parent or history.get("current_baseline", {}).get("branch_id") or BASELINE_BRANCH_ID
    existing = _branch_by_id(history, branch_id)
    branch = {
        "branch_id": branch_id,
        "parent": parent_id,
        "candidate_id": candidate_id,
        "created_by": created_by,
        "rationale": rationale,
        "status": "derived",
        "provenance": {
            "source_acceptance": DESIGN_STUDY_ACCEPTANCE_PATH,
            "accepted_artifacts": acceptance.get("accepted_artifacts", []),
            "accepted_by": acceptance.get("accepted_by"),
        },
    }
    if existing:
        history["branches"] = [branch if b is existing else b for b in history["branches"]]
    else:
        history["branches"].append(branch)
    _replace_members(package_path, {DESIGN_HISTORY_PATH: _dumps(history)})
    return {"status": OK, "branch_id": branch_id, "parent": parent_id,
            "candidate_id": candidate_id, "baseline_modified": False}


def promote_design_branch(
    package_path: str | Path,
    *,
    candidate_id: str,
    approved_by: str,
    approval: bool,
    rationale: str,
    changed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Governed promotion of an accepted candidate's branch to current baseline.

    Requires (1) explicit ``approval=True`` and (2) an existing derived branch for
    an accepted candidate. Without approval, or without a branch, it refuses and
    the governed baseline pointer is unchanged. On success it moves
    ``current_baseline`` to the branch, records who/why/what changed, and keeps the
    previous baseline for rollback. Baseline geometry is never overwritten.
    """
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": REFUSED, "reason": "package not found"}
    history, acceptance, _ = _load_history(package_path)
    branch_id = f"branch_{candidate_id}"

    if not approval:
        return {"status": REFUSED, "reason": "approval_required",
                "detail": "baseline promotion requires explicit approval=true",
                "candidate_id": candidate_id, "baseline_modified": False}
    branch = _branch_by_id(history, branch_id)
    if branch is None:
        return {"status": NEEDS_INPUT, "reason": "no_branch_for_candidate",
                "detail": "record a design branch (record_design_branch) before promotion",
                "candidate_id": candidate_id, "baseline_modified": False}
    if not _candidate_is_accepted(acceptance, candidate_id):
        return {"status": NEEDS_INPUT, "reason": "candidate_not_accepted",
                "candidate_id": candidate_id, "baseline_modified": False}

    prev_baseline = dict(history.get("current_baseline") or {"branch_id": BASELINE_BRANCH_ID, "candidate_id": None})
    promotion = {
        "promotion_id": f"promo_{candidate_id}",
        "branch_id": branch_id,
        "candidate_id": candidate_id,
        "approved": True,
        "approved_by": approved_by,
        "rationale": rationale,
        "changed": changed or {"summary": "see accepted candidate patch", "candidate_id": candidate_id},
        "from_baseline": prev_baseline.get("branch_id"),
        "to_baseline": branch_id,
        "baseline_geometry_overwritten": False,
    }
    history.setdefault("promotions", []).append(promotion)
    branch["status"] = "promoted"
    history["current_baseline"] = {"branch_id": branch_id, "candidate_id": candidate_id,
                                   "promoted_from": prev_baseline.get("branch_id")}
    _replace_members(package_path, {DESIGN_HISTORY_PATH: _dumps(history)})
    return {"status": OK, "promotion_id": promotion["promotion_id"], "branch_id": branch_id,
            "from_baseline": promotion["from_baseline"], "to_baseline": branch_id,
            "baseline_geometry_overwritten": False, "baseline_modified": False}


def rollback_baseline_promotion(
    package_path: str | Path,
    *,
    performed_by: str,
    rationale: str,
) -> dict[str, Any]:
    """Restore the governed baseline pointer to the state before the last promotion."""
    package_path = Path(package_path)
    if not package_path.exists():
        return {"status": REFUSED, "reason": "package not found"}
    history, _acceptance, _ = _load_history(package_path)
    promotions = [p for p in history.get("promotions", []) if isinstance(p, dict)]
    if not promotions:
        return {"status": NEEDS_INPUT, "reason": "no_promotion_to_rollback", "baseline_modified": False}

    last = promotions[-1]
    restored = last.get("from_baseline") or BASELINE_BRANCH_ID
    rollback = {
        "rollback_id": f"rollback_{last.get('promotion_id')}",
        "promotion_id": last.get("promotion_id"),
        "performed_by": performed_by,
        "rationale": rationale,
        "restored_baseline": restored,
        "rolled_back_branch": last.get("to_baseline"),
    }
    history.setdefault("rollbacks", []).append(rollback)
    branch = _branch_by_id(history, last.get("to_baseline"))
    if branch is not None:
        branch["status"] = "rolled_back"
    history["current_baseline"] = {"branch_id": restored, "candidate_id": None, "restored_by_rollback": True}
    _replace_members(package_path, {DESIGN_HISTORY_PATH: _dumps(history)})
    return {"status": OK, "rollback_id": rollback["rollback_id"], "restored_baseline": restored,
            "rolled_back_branch": last.get("to_baseline"), "baseline_modified": False}
