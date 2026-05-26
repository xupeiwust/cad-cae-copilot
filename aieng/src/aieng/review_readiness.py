"""Review-readiness semantics for .aieng claim proposals.

Pure functions with no I/O. The caller supplies already-computed evidence
counts and proposal metadata; this module assembles the readiness diagnostic
response without opening any ZIP, mutating any artifact, or advancing claims.
"""

from __future__ import annotations

from typing import Any

from .package_consistency import check_claim_map_absent

__all__ = [
    "build_review_readiness",
]


def build_review_readiness(
    *,
    ev_paths: list[str],
    missing_count: int,
    stale_count: int,
    proposal_status: str | None,
    pkg_names: set[str],
) -> dict[str, Any]:
    """Compute machine-readable review-readiness diagnostics for a claim proposal.

    Pure function — does not open any ZIP, does not mutate any artifact, and
    never creates or advances claim maps. All inputs are already-computed values
    from the support packet assembly.

    Args:
        ev_paths: List of supporting evidence paths declared in the proposal.
        missing_count: Number of evidence paths that are neither present in the
            package nor resolvable via the evidence index.
        stale_count: Number of evidence paths that carry the
            ``evidence_from_stale_geometry_state`` warning.
        proposal_status: The ``status`` field from the proposal dict, e.g.
            ``"proposed"`` or ``"draft"``.
        pkg_names: Full set of member paths in the package (namelist).  Used
            only for Check E (claim-map-absent); no other interpretation.

    Returns:
        Dict with ``status`` (``"ready"`` / ``"warning"`` / ``"blocked"``),
        ``checks`` (list of check result dicts), and
        ``claim_advancement: "none"``.

    Rollup policy:
        * Any ``blocked`` check → top-level ``status: "blocked"``.
        * Else any ``warning`` check → top-level ``status: "warning"``.
        * Else → top-level ``status: "ready"``.

    Checks emitted (always exactly five, in order):
        ``supporting_evidence_present``, ``no_missing_evidence``,
        ``stale_evidence``, ``proposal_status_reviewable``,
        ``claim_map_not_advanced``.
    """
    checks: list[dict[str, Any]] = []

    # A. supporting_evidence_present
    if not ev_paths:
        checks.append({
            "id": "supporting_evidence_present",
            "status": "blocked",
            "message": "Proposal has no supporting evidence entries.",
        })
    else:
        checks.append({
            "id": "supporting_evidence_present",
            "status": "ok",
            "message": f"{len(ev_paths)} supporting evidence path(s) declared.",
        })

    # B. no_missing_evidence
    if missing_count > 0:
        checks.append({
            "id": "no_missing_evidence",
            "status": "blocked",
            "message": (
                f"{missing_count} evidence path(s) not found in package or evidence index."
            ),
            "details": {"missing_count": missing_count},
        })
    else:
        checks.append({
            "id": "no_missing_evidence",
            "status": "ok",
            "message": "All declared evidence paths are resolvable.",
        })

    # C. stale_evidence
    if stale_count > 0:
        checks.append({
            "id": "stale_evidence",
            "status": "warning",
            "message": f"{stale_count} evidence path(s) are from a stale geometry state.",
            "details": {"stale_count": stale_count},
        })
    else:
        checks.append({
            "id": "stale_evidence",
            "status": "ok",
            "message": "No stale evidence detected.",
        })

    # D. proposal_status_reviewable
    if proposal_status in ("proposed", "draft"):
        checks.append({
            "id": "proposal_status_reviewable",
            "status": "ok",
            "message": f"Proposal status '{proposal_status}' is reviewable.",
        })
    else:
        checks.append({
            "id": "proposal_status_reviewable",
            "status": "warning",
            "message": (
                f"Unexpected proposal status {proposal_status!r}; "
                "expected 'proposed' or 'draft'."
            ),
        })

    # E. claim_map_not_advanced — reuse consistency check; rename id for readiness context.
    cm = check_claim_map_absent(pkg_names)
    checks.append({**cm, "id": "claim_map_not_advanced"})

    # Rollup: blocked > warning > ready.
    _PRIORITY: dict[str, int] = {"blocked": 2, "warning": 1, "ok": 0}
    worst = max((_PRIORITY.get(c.get("status", "ok"), 0) for c in checks), default=0)
    status = "blocked" if worst == 2 else ("warning" if worst == 1 else "ready")

    return {
        "status": status,
        "checks": checks,
        "claim_advancement": "none",
    }
