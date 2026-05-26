from __future__ import annotations

import sys

from .config import WORKSPACE_ROOT

# Boundary contract:
# - aieng core owns package semantics: artifact classification, evidence
#   resolution, consistency diagnostics, review readiness, claim proposals,
#   audit event shape, and revalidation transition semantics.
# - this reference runtime owns ZIP/project I/O, HTTP endpoints, filesystem
#   interaction, and tool orchestration.
# Inject aieng source path once so core package-semantics modules are importable.
_aieng_src_for_manifest = str(WORKSPACE_ROOT / "aieng" / "src")
if _aieng_src_for_manifest not in sys.path:
    sys.path.insert(0, _aieng_src_for_manifest)

from aieng.package_manifest import (  # noqa: E402
    classify_artifact_path as _classify_artifact_path,
    generate_artifact_manifest as _core_generate_artifact_manifest,
)
from aieng.evidence_resolver import (  # noqa: E402
    resolve_evidence_reference as _core_resolve_evidence_reference,
    STALE_EVIDENCE_CATEGORIES as _STALE_EVIDENCE_CATEGORIES,
)
from aieng.package_consistency import (  # noqa: E402
    is_internal_package_path,
    rollup_check_status,
    check_claim_proposals,
    run_package_consistency_checks as _core_run_package_consistency_checks,
)
from aieng.review_readiness import (  # noqa: E402
    build_review_readiness as _build_review_readiness,
)
from aieng.support_packet import (  # noqa: E402
    build_claim_support_packet as _core_build_claim_support_packet,
)
from aieng.claim_proposal import (  # noqa: E402
    CLAIM_PROPOSAL_ARTIFACT_PREFIX,
    CLAIM_PROPOSAL_STATUSES,
    build_claim_proposal as _build_claim_proposal,
    validate_claim_proposal_request as _validate_claim_proposal_request,
)
from aieng.audit_event import (  # noqa: E402
    AUDIT_EVENTS_PATH as _CORE_AUDIT_EVENTS_PATH,
    build_audit_event as _build_audit_event,
    parse_audit_events_jsonl as _parse_audit_events_jsonl,
    serialize_audit_events_jsonl as _serialize_audit_events_jsonl,
)
from aieng.revalidation_status import (  # noqa: E402
    REVALIDATION_STATUS_PATH as _CORE_REVALIDATION_STATUS_PATH,
    build_revalidation_response as _core_build_revalidation_response,
    record_geometry_edit_status as _core_record_geometry_edit_status,
    record_solver_validation_status as _core_record_solver_validation_status,
)

# Re-export aliases expected by test_api.py imports
_is_internal_package_path = is_internal_package_path
_rollup_check_status = rollup_check_status
_check_claim_proposals = check_claim_proposals
