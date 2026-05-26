"""Package consistency diagnostics for .aieng packages.

Pure functions with no I/O or ZIP handling. The caller supplies already-read
package content (raw bytes or pre-parsed data); this module classifies issues
and assembles diagnostic check results.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

__all__ = [
    "is_internal_package_path",
    "check_claim_map_absent",
    "rollup_check_status",
    "check_claim_proposals",
    "run_package_consistency_checks",
]


def is_internal_package_path(path: str) -> bool:
    """Return True if path looks like a relative package-internal path.

    Rejects absolute Unix paths (/...), absolute Windows paths (C:\\...),
    and paths containing backslashes so that external filesystem references
    from tool outputs are not mistakenly checked against the package namelist.
    """
    if not path:
        return False
    if path.startswith("/"):
        return False
    if len(path) > 1 and path[1] == ":":
        return False
    if "\\" in path:
        return False
    return True


def _check_evidence_paths(
    pkg_names: set[str],
    evidence_raw: bytes | None,
) -> dict[str, Any]:
    """Check A: evidence index entries marked exists=True are in the package."""
    if evidence_raw is None:
        return {
            "id": "evidence_paths_exist",
            "status": "warning",
            "message": "results/evidence_index.json absent; no evidence catalog to check.",
        }
    try:
        ei = json.loads(evidence_raw)
    except (json.JSONDecodeError, ValueError):
        return {
            "id": "evidence_paths_exist",
            "status": "error",
            "message": "results/evidence_index.json is not valid JSON.",
        }
    entries = ei.get("entries") or []
    present_entries = [e for e in entries if e.get("exists") is True]
    missing = [
        e["path"] for e in present_entries if e.get("path") and e["path"] not in pkg_names
    ]
    if missing:
        return {
            "id": "evidence_paths_exist",
            "status": "warning",
            "message": f"{len(missing)} evidence-indexed path(s) marked exists=True not found in package.",
            "details": {"missing_paths": missing},
        }
    return {
        "id": "evidence_paths_exist",
        "status": "ok",
        "message": f"All {len(present_entries)} evidence-indexed path(s) confirmed present.",
    }


def _check_audit_artifact_references(
    pkg_names: set[str],
    audit_raw: bytes | None,
) -> dict[str, Any]:
    """Check B: internal artifact paths in audit events exist in the package."""
    if audit_raw is None:
        return {
            "id": "audit_artifact_references",
            "status": "ok",
            "message": "No audit log present; no artifact references to check.",
        }
    events: list[dict[str, Any]] = []
    for line in audit_raw.decode("utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                pass
    missing: list[dict[str, Any]] = []
    for event in events:
        for key in ("artifacts_written", "evidence_created"):
            for path in event.get(key) or []:
                if is_internal_package_path(path) and path not in pkg_names:
                    missing.append({"event_id": event.get("event_id"), "path": path})
    if missing:
        return {
            "id": "audit_artifact_references",
            "status": "warning",
            "message": f"{len(missing)} artifact reference(s) in audit log not found in package.",
            "details": {"missing_references": missing[:10]},
        }
    return {
        "id": "audit_artifact_references",
        "status": "ok",
        "message": f"All internal artifact references across {len(events)} audit event(s) confirmed present.",
    }


def _check_field_summary_sources(
    pkg_names: set[str],
    disp_raw: bytes | None,
    stress_raw: bytes | None,
) -> list[dict[str, Any]]:
    """Check C: field summary source artifacts exist when referenced as internal paths."""
    results: list[dict[str, Any]] = []
    for field_name, raw in (("displacement", disp_raw), ("stress", stress_raw)):
        artifact_path = f"results/fields/{field_name}.summary.json"
        if raw is None:
            continue
        try:
            summary = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            results.append({
                "id": f"field_summary_source_{field_name}",
                "status": "error",
                "message": f"{artifact_path} is not valid JSON.",
            })
            continue
        source = summary.get("source") or {}
        candidates = [
            v for v in source.values()
            if isinstance(v, str) and "/" in v and is_internal_package_path(v)
        ]
        if not candidates:
            results.append({
                "id": f"field_summary_source_{field_name}",
                "status": "warning",
                "message": f"{artifact_path} has no traceable internal source path.",
            })
            continue
        missing = [p for p in candidates if p not in pkg_names]
        if missing:
            results.append({
                "id": f"field_summary_source_{field_name}",
                "status": "warning",
                "message": f"{artifact_path} source artifact(s) not found in package.",
                "details": {"missing_sources": missing},
            })
        else:
            results.append({
                "id": f"field_summary_source_{field_name}",
                "status": "ok",
                "message": f"{artifact_path} source artifact(s) present.",
            })
    return results


def _check_revalidation_consistency(rs: dict[str, Any] | None) -> dict[str, Any]:
    """Check D: revalidation status is internally consistent.

    Stale state (requires_revalidation=True) is a warning, not an error.
    Disagreeing revisions when requires_revalidation=False is also a warning.
    """
    if rs is None:
        return {
            "id": "revalidation_status_consistency",
            "status": "ok",
            "message": "No revalidation status present; no geometry edits recorded.",
        }
    requires = rs.get("requires_revalidation", False)
    current = rs.get("current_geometry_revision")
    last_validated = rs.get("last_validated_geometry_revision")
    if requires:
        return {
            "id": "revalidation_status_consistency",
            "status": "warning",
            "message": "Geometry modified; CAE results may be stale. Re-run solver to revalidate.",
            "details": {
                "current_geometry_revision": current,
                "last_validated_geometry_revision": last_validated,
                "requires_revalidation": True,
            },
        }
    if current is not None and last_validated is not None and current != last_validated:
        return {
            "id": "revalidation_status_consistency",
            "status": "warning",
            "message": (
                f"requires_revalidation is false but revisions disagree "
                f"(current={current}, last_validated={last_validated})."
            ),
            "details": {
                "current_geometry_revision": current,
                "last_validated_geometry_revision": last_validated,
            },
        }
    return {
        "id": "revalidation_status_consistency",
        "status": "ok",
        "message": "Revalidation status is consistent.",
        "details": {
            "current_geometry_revision": current,
            "last_validated_geometry_revision": last_validated,
        },
    }


def check_claim_map_absent(pkg_names: set[str]) -> dict[str, Any]:
    """Check E: no claim map files are present in the package."""
    _CLAIM_MAP_PATHS = ("ai/claim_map.json", "results/claim_map.json")
    found = [p for p in _CLAIM_MAP_PATHS if p in pkg_names]
    if found:
        return {
            "id": "claim_map_absent",
            "status": "warning",
            "message": (
                f"Claim map file(s) present: {found}. "
                "Verify no automatic claim advancement occurred."
            ),
            "details": {"found_paths": found},
        }
    return {
        "id": "claim_map_absent",
        "status": "ok",
        "message": "No claim map files present; claim non-advancement contract maintained.",
    }


def rollup_check_status(checks: list[dict[str, Any]]) -> str:
    """Return the highest severity status across checks: 'error' > 'warning' > 'ok'."""
    _PRIORITY: dict[str, int] = {"error": 2, "warning": 1, "ok": 0}
    if not checks:
        return "ok"
    return max(checks, key=lambda c: _PRIORITY.get(c.get("status", "ok"), 0)).get("status", "ok")


def check_claim_proposals(
    pkg_names: set[str],
    proposal_data: list[tuple[str, bytes]],
    evidence_raw: bytes | None,
) -> dict[str, Any]:
    """Check F: claim proposals are well-formed and do not imply accepted claims.

    A proposal with status 'proposed' or 'draft' is fine. Supporting evidence
    paths must be in the package or evidence index. Proposals are not claims —
    their presence is never an error.
    """
    if not proposal_data:
        return {
            "id": "claim_proposals",
            "status": "ok",
            "message": "No claim proposals present.",
        }

    indexed_paths: set[str] = set()
    if evidence_raw:
        try:
            ei = json.loads(evidence_raw)
            for e in (ei.get("entries") or []):
                if e.get("path"):
                    indexed_paths.add(e["path"])
        except (json.JSONDecodeError, ValueError):
            pass

    issues: list[str] = []
    for path, raw in proposal_data:
        try:
            proposal = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            issues.append(f"{path}: not valid JSON")
            continue
        pstatus = proposal.get("status")
        if pstatus not in ("proposed", "draft"):
            issues.append(f"{path}: unexpected status {pstatus!r}")
        if proposal.get("claim_advancement") != "none":
            issues.append(f"{path}: claim_advancement is not 'none'")
        for ev_path in (proposal.get("supporting_evidence") or []):
            if ev_path not in pkg_names and ev_path not in indexed_paths:
                issues.append(f"{path}: supporting evidence {ev_path!r} not found")

    if issues:
        return {
            "id": "claim_proposals",
            "status": "warning",
            "message": f"{len(issues)} issue(s) found in claim proposal(s).",
            "details": {"issues": issues},
        }
    return {
        "id": "claim_proposals",
        "status": "ok",
        "message": f"{len(proposal_data)} claim proposal(s) present; all well-formed.",
        "details": {"proposal_count": len(proposal_data)},
    }


def run_package_consistency_checks(
    *,
    package_paths: Iterable[str],
    evidence_raw: bytes | None = None,
    audit_raw: bytes | None = None,
    revalidation_status: dict[str, Any] | None = None,
    displacement_summary_raw: bytes | None = None,
    stress_summary_raw: bytes | None = None,
    claim_proposals: list[tuple[str, bytes]] | None = None,
) -> list[dict[str, Any]]:
    """Run all consistency checks against pre-read package data.

    Pure function — accepts already-read package content. Does not open any
    ZIP, does not mutate any artifact, and never creates or advances claim maps.

    Args:
        package_paths: All member paths present in the package (namelist).
        evidence_raw: Raw bytes of ``results/evidence_index.json``, or ``None``
            when absent.
        audit_raw: Raw bytes of ``audit/events.jsonl``, or ``None`` when absent.
        revalidation_status: Parsed ``state/revalidation_status.json``, or
            ``None`` when absent.
        displacement_summary_raw: Raw bytes of
            ``results/fields/displacement.summary.json``, or ``None``.
        stress_summary_raw: Raw bytes of
            ``results/fields/stress.summary.json``, or ``None``.
        claim_proposals: List of ``(path, raw_bytes)`` tuples for each proposal
            file found in ``claims/proposals/``, or ``None`` / empty when none.

    Returns:
        List of check result dicts. Each has ``id``, ``status``
        (``"ok"`` / ``"warning"`` / ``"error"``), ``message``, and optional
        ``details``. Use :func:`rollup_check_status` to derive overall status.
    """
    pkg_names: set[str] = set(package_paths)
    return [
        _check_evidence_paths(pkg_names, evidence_raw),
        _check_audit_artifact_references(pkg_names, audit_raw),
        *_check_field_summary_sources(pkg_names, displacement_summary_raw, stress_summary_raw),
        _check_revalidation_consistency(revalidation_status),
        check_claim_map_absent(pkg_names),
        check_claim_proposals(pkg_names, claim_proposals or [], evidence_raw),
    ]
