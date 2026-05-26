"""In-memory cookbook for composing .aieng package semantics.

This example is intentionally dependency-light: it does not open ZIP files,
run FreeCAD, run CalculiX, call aieng-ui, or use the network. A downstream
runtime can use the same direct submodule imports after it has already read
package members and JSON artifacts from its own storage layer.
"""

from __future__ import annotations

import json
from typing import Any

from aieng.audit_event import build_audit_event, serialize_audit_events_jsonl
from aieng.claim_proposal import build_claim_proposal, claim_proposal_path
from aieng.evidence_resolver import resolve_evidence_reference
from aieng.package_consistency import rollup_check_status, run_package_consistency_checks
from aieng.package_manifest import generate_artifact_manifest
from aieng.revalidation_status import (
    default_revalidation_status,
    record_geometry_edit_status,
    record_solver_validation_status,
)
from aieng.review_readiness import build_review_readiness

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def build_cookbook_outputs() -> dict[str, Any]:
    """Return a compact in-memory package-semantics walkthrough."""
    package_paths = [
        "manifest.json",
        "metadata.json",
        "geometry/source.step",
        "simulation/runs/run_001/outputs/result.frd",
        "results/computed_metrics.json",
        "results/evidence_index.json",
        "results/fields/displacement.summary.json",
        "state/revalidation_status.json",
    ]

    evidence_entries = [
        {
            "id": "displacement_summary",
            "path": "results/fields/displacement.summary.json",
            "kind": "field",
            "role": "displacement_extrema",
            "exists": True,
            "supports": ["claim_proposal_review"],
        }
    ]
    evidence_index = {
        "schema_version": "0.1",
        "evidence_type": "cae_artifacts",
        "entries": evidence_entries,
    }

    # Freshness is not validation: this records revision freshness only. It
    # does not certify numerical correctness or engineering adequacy.
    default_status = default_revalidation_status()
    stale_status = record_geometry_edit_status(
        default_status,
        affected_artifacts=["geometry/source.step"],
        timestamp=FIXED_TIME,
    )
    validated_status = record_solver_validation_status(
        stale_status,
        run_id="run_001",
        timestamp=FIXED_TIME,
    )

    artifact_manifest = generate_artifact_manifest(
        package_paths,
        revalidation_status=validated_status,
        generated_at=FIXED_TIME,
    )

    # Evidence is not claim: resolving evidence says whether an artifact is
    # present/fresh enough to inspect, not whether a claim is true.
    resolved_evidence = resolve_evidence_reference(
        path="results/fields/displacement.summary.json",
        package_paths=package_paths,
        evidence_entries=evidence_entries,
        revalidation_status=validated_status,
    )

    proposal = build_claim_proposal(
        claim_id="claim_bracket_displacement_ok",
        proposed_status="supported",
        supporting_evidence=["results/fields/displacement.summary.json"],
        rationale="Displacement summary is present for human/agent review.",
        proposal_id="proposal-001",
        created_at=FIXED_TIME,
    )
    proposal_path = claim_proposal_path(proposal["proposal_id"])
    package_paths_with_proposal = [*package_paths, proposal_path, "audit/events.jsonl"]

    # Proposal is not acceptance: this artifact only proposes a status for
    # review. No claim map is created and claim_advancement remains "none".
    review_readiness = build_review_readiness(
        ev_paths=proposal["supporting_evidence"],
        missing_count=0 if resolved_evidence["usable_for_claim_proposal"] else 1,
        stale_count=1 if "evidence_from_stale_geometry_state" in resolved_evidence["warnings"] else 0,
        proposal_status=proposal["status"],
        pkg_names=set(package_paths_with_proposal),
    )

    audit_event = build_audit_event(
        tool="claims.propose_update",
        event_type="claim_proposal_created",
        status="completed",
        artifacts_written=[proposal_path],
        evidence_created=[],
        state_changes={
            "claim_id": proposal["claim_id"],
            "proposed_status": proposal["proposed_status"],
        },
        geometry_revision=validated_status["current_geometry_revision"],
        revalidation_status="fresh",
        event_id="event-001",
        timestamp=FIXED_TIME,
    )

    consistency_checks = run_package_consistency_checks(
        package_paths=package_paths_with_proposal,
        evidence_raw=json.dumps(evidence_index).encode("utf-8"),
        audit_raw=serialize_audit_events_jsonl([audit_event]).encode("utf-8"),
        revalidation_status=validated_status,
        claim_proposals=[(proposal_path, json.dumps(proposal).encode("utf-8"))],
    )

    # Diagnostics are not certification: consistency/readiness checks make
    # package state reviewable, but they do not validate engineering claims.
    return {
        "artifact_manifest": artifact_manifest,
        "resolved_evidence": resolved_evidence,
        "package_consistency": {
            "rollup": rollup_check_status(consistency_checks),
            "checks": consistency_checks,
        },
        "claim_proposal": proposal,
        "review_readiness": review_readiness,
        "revalidation_transitions": {
            "default": default_status,
            "after_geometry_edit": stale_status,
            "after_solver_validation": validated_status,
        },
        "audit_event": audit_event,
        "claim_advancement": "none",
    }


def main() -> None:
    """Print the cookbook outputs as deterministic JSON."""
    print(json.dumps(build_cookbook_outputs(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
