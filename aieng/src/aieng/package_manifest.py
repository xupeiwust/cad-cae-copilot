"""Artifact manifest classification and generation for .aieng packages.

Pure functions with no I/O or ZIP handling. The caller supplies the list of
artifact paths present in the package; this module classifies them and
assembles the manifest response.
"""

from __future__ import annotations

import fnmatch
from datetime import datetime, timezone
from typing import Any, Iterable

__all__ = [
    "ARTIFACT_MANIFEST_PATH",
    "FRESHNESS_CATEGORIES",
    "classify_artifact_path",
    "generate_artifact_manifest",
]

# ── pattern catalog ──────────────────────────────────────────────────────────
# Each entry: (glob_pattern, kind, category, producer_tool, evidence_role).
# First match wins. More specific patterns must come before broader ones.

_ARTIFACT_PATTERN_CATALOG: list[tuple[str, str, str, str | None, str | None]] = [
    ("state/revalidation_status.json",           "state",               "state",          "cad.edit_parameter",              None),
    ("audit/events.jsonl",                       "audit_log",           "audit",          None,                              None),
    ("analysis/optimization_study.json",         "optimization_study",  "analysis",       "opt.create_study",               None),
    ("analysis/optimization_variables.json",     "optimization_input",  "analysis",       "opt.define_variables",           None),
    ("analysis/optimization_objectives.json",    "optimization_input",  "analysis",       "opt.define_objectives",          None),
    ("analysis/optimization_constraints.json",   "optimization_input",  "analysis",       "opt.define_constraints",         None),
    ("analysis/optimization_decision_log.json",  "decision_log",        "audit",          None,                              None),
    ("results/result_summary.json",              "cae_result_summary",  "summary",        "postprocess.refresh_cae_summary", "llm_readable_postprocessing_summary"),
    ("results/evidence_index.json",              "evidence_index",      "evidence_index", "postprocess.refresh_cae_summary", "cae_evidence_catalog"),
    ("results/postprocessing_summary.md",        "markdown_summary",    "summary",        "postprocess.refresh_cae_summary", "human_llm_readable_summary"),
    ("results/fields/displacement.summary.json", "field",               "field_summary",  "postprocess.refresh_cae_summary", "displacement_extrema"),
    ("results/fields/stress.summary.json",       "field",               "field_summary",  "postprocess.refresh_cae_summary", "stress_extrema"),
    ("results/computed_metrics.json",            "result",              "solver_output",  "cae.run_solver",                  "computed_extrema"),
    ("simulation/mesh/mesh_metadata.json",       "mesh_metadata",       "mesh",           "cae.generate_mesh",               None),
    ("simulation/mesh/*.inp",                    "mesh",                "mesh",           "cae.generate_mesh",               None),
    ("simulation/runs/*/solver_run.json",        "solver_run_metadata", "solver_output",  "cae.run_solver",                  "solver_execution_evidence"),
    ("simulation/runs/*/outputs/*.frd",          "solver_raw_output",   "solver_output",  "cae.run_solver",                  "solver_raw_output"),
    ("geometry/*.step",                          "geometry",            "geometry",       None,                              None),
    ("geometry/*.stp",                           "geometry",            "geometry",       None,                              None),
    ("geometry/*.iges",                          "geometry",            "geometry",       None,                              None),
    ("claims/proposals/*.json",                  "claim_proposal",      "claim_proposal", "claims.propose_update",           None),
    ("manifest.json",                            "package_manifest",    "package",        None,                              None),
    ("metadata.json",                            "package_metadata",    "package",        None,                              None),
]

# Categories whose artifacts are annotated with revalidation/freshness context.
FRESHNESS_CATEGORIES: frozenset[str] = frozenset({
    "solver_output", "summary", "field_summary", "evidence_index",
})

# Path constant reserved for future use (manifest written into the package).
ARTIFACT_MANIFEST_PATH = "manifest/artifacts.json"


def classify_artifact_path(path: str) -> tuple[str, str, str | None, str | None]:
    """Return (kind, category, producer_tool, evidence_role) for an artifact path.

    First matching entry in the pattern catalog wins. Returns
    ``("unknown", "unknown", None, None)`` for unrecognised paths.
    """
    for pattern, kind, category, producer_tool, evidence_role in _ARTIFACT_PATTERN_CATALOG:
        if fnmatch.fnmatch(path, pattern):
            return kind, category, producer_tool, evidence_role
    return "unknown", "unknown", None, None


def generate_artifact_manifest(
    paths: Iterable[str],
    *,
    revalidation_status: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Generate an artifact manifest from a list of package member paths.

    All supplied paths are treated as existing (``exists: True``). The caller
    is responsible for filtering out ZIP directory entries (paths ending with
    ``/``) before passing them in.

    Args:
        paths: Artifact paths present in the package.
        revalidation_status: Parsed contents of ``state/revalidation_status.json``
            from the same package, or ``None`` when absent.
        generated_at: ISO 8601 timestamp string; defaults to current UTC time.

    Returns:
        Manifest dict with ``schema_version``, ``generated_at``,
        ``claim_advancement: "none"``, ``requires_revalidation``,
        ``current_geometry_revision``, ``artifact_count``, and ``artifacts``.
        Each artifact entry has ``path``, ``kind``, ``category``, ``exists``,
        ``claim_advancement``, and optionally ``producer_tool``,
        ``evidence_role``, ``requires_revalidation``, ``geometry_revision``.
    """
    rs = revalidation_status or {}
    requires_reval: bool = bool(rs.get("requires_revalidation", False))
    current_rev: int = int(rs.get("current_geometry_revision") or 0)
    ts = generated_at or datetime.now(timezone.utc).isoformat()

    artifacts: list[dict[str, Any]] = []
    for name in paths:
        if name == ARTIFACT_MANIFEST_PATH:
            continue
        kind, category, producer_tool, evidence_role = classify_artifact_path(name)
        entry: dict[str, Any] = {
            "path": name,
            "kind": kind,
            "category": category,
            "exists": True,
            "claim_advancement": "none",
        }
        if producer_tool is not None:
            entry["producer_tool"] = producer_tool
        if evidence_role is not None:
            entry["evidence_role"] = evidence_role
        if category in FRESHNESS_CATEGORIES:
            entry["requires_revalidation"] = requires_reval
            entry["geometry_revision"] = current_rev
        artifacts.append(entry)

    return {
        "schema_version": "0.1",
        "generated_at": ts,
        "claim_advancement": "none",
        "requires_revalidation": requires_reval,
        "current_geometry_revision": current_rev,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
