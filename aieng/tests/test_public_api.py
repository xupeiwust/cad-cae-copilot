"""Public API smoke tests for the aieng core package.

Each test imports a stable symbol and performs a minimal sanity check (callable
or isinstance). No heavy runtime behaviour — these tests exist to catch
accidental renames or deletions of public names.
"""

from __future__ import annotations

# ── package_manifest ─────────────────────────────────────────────────────────

def test_import_classify_artifact_path() -> None:
    from aieng.package_manifest import classify_artifact_path
    assert callable(classify_artifact_path)


def test_import_generate_artifact_manifest() -> None:
    from aieng.package_manifest import generate_artifact_manifest
    assert callable(generate_artifact_manifest)


def test_import_artifact_manifest_path() -> None:
    from aieng.package_manifest import ARTIFACT_MANIFEST_PATH
    assert isinstance(ARTIFACT_MANIFEST_PATH, str)


def test_import_freshness_categories() -> None:
    from aieng.package_manifest import FRESHNESS_CATEGORIES
    assert isinstance(FRESHNESS_CATEGORIES, frozenset)


# ── evidence_resolver ────────────────────────────────────────────────────────

def test_import_resolve_evidence_reference() -> None:
    from aieng.evidence_resolver import resolve_evidence_reference
    assert callable(resolve_evidence_reference)


def test_import_stale_evidence_categories() -> None:
    from aieng.evidence_resolver import STALE_EVIDENCE_CATEGORIES
    assert isinstance(STALE_EVIDENCE_CATEGORIES, frozenset)


# ── package_consistency ──────────────────────────────────────────────────────

def test_import_run_package_consistency_checks() -> None:
    from aieng.package_consistency import run_package_consistency_checks
    assert callable(run_package_consistency_checks)


def test_import_is_internal_package_path() -> None:
    from aieng.package_consistency import is_internal_package_path
    assert callable(is_internal_package_path)


def test_import_rollup_check_status() -> None:
    from aieng.package_consistency import rollup_check_status
    assert callable(rollup_check_status)


def test_import_check_claim_proposals() -> None:
    from aieng.package_consistency import check_claim_proposals
    assert callable(check_claim_proposals)



# ── review_readiness ─────────────────────────────────────────────────────────

def test_import_build_review_readiness() -> None:
    from aieng.review_readiness import build_review_readiness
    assert callable(build_review_readiness)


# ── claim_proposal ───────────────────────────────────────────────────────────

def test_import_build_claim_proposal() -> None:
    from aieng.claim_proposal import build_claim_proposal
    assert callable(build_claim_proposal)


def test_import_validate_claim_proposal_artifact() -> None:
    from aieng.claim_proposal import validate_claim_proposal_artifact
    assert callable(validate_claim_proposal_artifact)


def test_import_validate_claim_proposal_request() -> None:
    from aieng.claim_proposal import validate_claim_proposal_request
    assert callable(validate_claim_proposal_request)


def test_import_claim_proposal_statuses() -> None:
    from aieng.claim_proposal import CLAIM_PROPOSAL_STATUSES
    assert isinstance(CLAIM_PROPOSAL_STATUSES, frozenset)
    assert "supported" in CLAIM_PROPOSAL_STATUSES


def test_import_claim_proposal_path() -> None:
    from aieng.claim_proposal import claim_proposal_path
    assert callable(claim_proposal_path)
    assert claim_proposal_path("x") == "claims/proposals/x.json"


# ── audit_event ──────────────────────────────────────────────────────────────

def test_import_build_audit_event() -> None:
    from aieng.audit_event import build_audit_event
    assert callable(build_audit_event)


def test_import_validate_audit_event() -> None:
    from aieng.audit_event import validate_audit_event
    assert callable(validate_audit_event)


def test_import_parse_audit_events_jsonl() -> None:
    from aieng.audit_event import parse_audit_events_jsonl
    assert callable(parse_audit_events_jsonl)


def test_import_serialize_audit_events_jsonl() -> None:
    from aieng.audit_event import serialize_audit_events_jsonl
    assert callable(serialize_audit_events_jsonl)


def test_import_audit_events_path() -> None:
    from aieng.audit_event import AUDIT_EVENTS_PATH
    assert AUDIT_EVENTS_PATH == "audit/events.jsonl"


def test_import_audit_event_types() -> None:
    from aieng.audit_event import AUDIT_EVENT_TYPES
    assert isinstance(AUDIT_EVENT_TYPES, frozenset)


# ── revalidation_status ──────────────────────────────────────────────────────

def test_import_record_geometry_edit_status() -> None:
    from aieng.revalidation_status import record_geometry_edit_status
    assert callable(record_geometry_edit_status)


def test_import_record_solver_validation_status() -> None:
    from aieng.revalidation_status import record_solver_validation_status
    assert callable(record_solver_validation_status)


def test_import_build_revalidation_response() -> None:
    from aieng.revalidation_status import build_revalidation_response
    assert callable(build_revalidation_response)


def test_import_default_revalidation_status() -> None:
    from aieng.revalidation_status import default_revalidation_status
    assert callable(default_revalidation_status)


def test_import_validate_revalidation_status() -> None:
    from aieng.revalidation_status import validate_revalidation_status
    assert callable(validate_revalidation_status)


def test_import_revalidation_status_path() -> None:
    from aieng.revalidation_status import REVALIDATION_STATUS_PATH
    assert REVALIDATION_STATUS_PATH == "state/revalidation_status.json"


# ── cae_result_summary ───────────────────────────────────────────────────────

def test_import_generate_cae_result_summary() -> None:
    from aieng.cae_result_summary import generate_cae_result_summary
    assert callable(generate_cae_result_summary)


def test_import_generate_evidence_index() -> None:
    from aieng.cae_result_summary import generate_evidence_index
    assert callable(generate_evidence_index)


def test_import_generate_postprocessing_markdown() -> None:
    from aieng.cae_result_summary import generate_postprocessing_markdown
    assert callable(generate_postprocessing_markdown)


def test_import_write_cae_result_summary_package() -> None:
    from aieng.cae_result_summary import write_cae_result_summary_package
    assert callable(write_cae_result_summary_package)


def test_import_result_summary_path() -> None:
    from aieng.cae_result_summary import RESULT_SUMMARY_PATH
    assert RESULT_SUMMARY_PATH == "results/result_summary.json"


def test_import_evidence_index_path() -> None:
    from aieng.cae_result_summary import EVIDENCE_INDEX_PATH
    assert EVIDENCE_INDEX_PATH == "results/evidence_index.json"


# ── __all__ declared in each module ──────────────────────────────────────────

def test_all_declared_package_manifest() -> None:
    import aieng.package_manifest as m
    assert hasattr(m, "__all__")
    assert "classify_artifact_path" in m.__all__


def test_all_declared_evidence_resolver() -> None:
    import aieng.evidence_resolver as m
    assert hasattr(m, "__all__")
    assert "resolve_evidence_reference" in m.__all__


def test_all_declared_package_consistency() -> None:
    import aieng.package_consistency as m
    assert hasattr(m, "__all__")
    assert "run_package_consistency_checks" in m.__all__


def test_all_declared_review_readiness() -> None:
    import aieng.review_readiness as m
    assert hasattr(m, "__all__")
    assert "build_review_readiness" in m.__all__


# ---- support_packet ---------------------------------------------------------

def test_import_build_claim_support_packet() -> None:
    from aieng.support_packet import build_claim_support_packet
    assert callable(build_claim_support_packet)


def test_all_declared_support_packet() -> None:
    import aieng.support_packet as m
    assert hasattr(m, "__all__")
    assert "build_claim_support_packet" in m.__all__


def test_all_declared_claim_proposal() -> None:
    import aieng.claim_proposal as m
    assert hasattr(m, "__all__")
    assert "build_claim_proposal" in m.__all__


def test_all_declared_audit_event() -> None:
    import aieng.audit_event as m
    assert hasattr(m, "__all__")
    assert "build_audit_event" in m.__all__


def test_all_declared_revalidation_status() -> None:
    import aieng.revalidation_status as m
    assert hasattr(m, "__all__")
    assert "record_geometry_edit_status" in m.__all__


def test_all_declared_cae_result_summary() -> None:
    import aieng.cae_result_summary as m
    assert hasattr(m, "__all__")
    assert "generate_cae_result_summary" in m.__all__
