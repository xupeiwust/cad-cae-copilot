"""Evidence reference resolution for .aieng packages.

Pure function with no I/O. The caller supplies already-read package metadata
(member paths, evidence index entries, revalidation status); this module
classifies the reference and assembles the resolution response.
"""

from __future__ import annotations

from typing import Any, Iterable

from .package_manifest import FRESHNESS_CATEGORIES, classify_artifact_path

__all__ = [
    "STALE_EVIDENCE_CATEGORIES",
    "resolve_evidence_reference",
]

# Evidence categories that are flagged as stale when requires_revalidation=True.
# Identical to FRESHNESS_CATEGORIES in package_manifest — same set, separate name
# here to make the stale-warning semantics explicit at the call site.
STALE_EVIDENCE_CATEGORIES: frozenset[str] = FRESHNESS_CATEGORIES


def resolve_evidence_reference(
    *,
    path: str,
    package_paths: Iterable[str],
    evidence_entries: Iterable[dict[str, Any]] | None = None,
    revalidation_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a single evidence reference path against current package state.

    Pure function — accepts already-read package metadata. Does not open any
    ZIP, does not mutate any artifact, and never creates or advances claim maps.

    Args:
        path: The artifact path inside the package to resolve.
        package_paths: All member paths present in the package (namelist).
        evidence_entries: Parsed ``entries`` list from ``results/evidence_index.json``,
            or ``None`` / empty when the evidence index is absent or unreadable.
        revalidation_status: Parsed contents of ``state/revalidation_status.json``,
            or ``None`` when absent.

    Returns:
        A stable dict with the following fields:

        ``schema_version``, ``path``, ``exists``, ``in_evidence_index``,
        ``evidence_index_entry``, ``manifest_category``, ``manifest_kind``,
        ``evidence_role``, ``requires_revalidation``,
        ``current_geometry_revision``, ``last_validated_geometry_revision``,
        ``usable_for_claim_proposal``, ``warnings``, ``claim_advancement``.

    Stale behavior:
        When ``requires_revalidation`` is ``True`` and the artifact category is
        in ``STALE_EVIDENCE_CATEGORIES``, the warning
        ``"evidence_from_stale_geometry_state"`` is appended. Stale evidence
        remains ``usable_for_claim_proposal`` because proposals are draft
        artifacts that require explicit acceptance.

    Missing behavior:
        When a path is absent from both the package and the evidence index, the
        warning ``"path_not_found_in_package_or_evidence_index"`` is appended and
        ``usable_for_claim_proposal`` is ``False``.
    """
    pkg_set: set[str] = set(package_paths)
    entries: list[dict[str, Any]] = list(evidence_entries or [])

    exists: bool = path in pkg_set

    ei_entry: dict[str, Any] | None = next(
        (e for e in entries if e.get("path") == path), None
    )
    in_evidence_index: bool = ei_entry is not None

    kind, category, _producer, evidence_role = classify_artifact_path(path)

    rs = revalidation_status or {}
    requires_reval: bool = bool(rs.get("requires_revalidation", False))
    current_rev: int | None = rs.get("current_geometry_revision")
    last_validated_rev: int | None = rs.get("last_validated_geometry_revision")

    warnings: list[str] = []
    if not exists and not in_evidence_index:
        warnings.append("path_not_found_in_package_or_evidence_index")
    if requires_reval and category in STALE_EVIDENCE_CATEGORIES:
        warnings.append("evidence_from_stale_geometry_state")

    usable: bool = exists or in_evidence_index

    return {
        "schema_version": "0.1",
        "path": path,
        "exists": exists,
        "in_evidence_index": in_evidence_index,
        "evidence_index_entry": ei_entry,
        "manifest_category": category,
        "manifest_kind": kind,
        "evidence_role": evidence_role,
        "requires_revalidation": requires_reval,
        "current_geometry_revision": current_rev,
        "last_validated_geometry_revision": last_validated_rev,
        "usable_for_claim_proposal": usable,
        "warnings": warnings,
        "claim_advancement": "none",
    }
