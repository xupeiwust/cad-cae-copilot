""".aieng bridge: internal helpers for evidence, provenance, context, guards, and persistence."""

from freecad_mcp.aieng_bridge.feature_inspector import (
    SUPPORTED_EXTENSIONS,
    inspect_features,
)
from freecad_mcp.aieng_bridge.claims import (
    ClaimDecisionCriterion,
    ClaimUpdateRequest,
    ClaimUpdateSummary,
    CriterionResult,
    evaluate_claim_criteria,
    find_claim,
    find_evidence,
    load_claim_map,
    load_evidence_index,
    update_claim_status,
)
from freecad_mcp.aieng_bridge.references import (
    CaeTargetReference,
    GeometryReference,
    ReferenceMap,
    build_reference_map,
    load_reference_map,
    mark_references_needing_review,
    write_reference_map,
)
from freecad_mcp.aieng_bridge.context import AiengPackageContext, load_aieng_context
from freecad_mcp.aieng_bridge.evidence import build_evidence_entry
from freecad_mcp.aieng_bridge.guards import GuardResult, check_operation_allowed
from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    append_evidence_entry,
    append_trace_entry,
    persist_standard_result_to_aieng,
)
from freecad_mcp.aieng_bridge.postprocessing import (
    PostprocessArtifact,
    PostprocessRequest,
    PostprocessSummary,
    ResultMetric,
    postprocess_results,
)
from freecad_mcp.aieng_bridge.trace import build_trace_entry

__all__ = [
    "inspect_features",
    "SUPPORTED_EXTENSIONS",
    "AiengPackageContext",
    "load_aieng_context",
    "build_evidence_entry",
    "build_trace_entry",
    "GuardResult",
    "check_operation_allowed",
    "PersistenceError",
    "append_evidence_entry",
    "append_trace_entry",
    "persist_standard_result_to_aieng",
    "PostprocessRequest",
    "PostprocessSummary",
    "ResultMetric",
    "PostprocessArtifact",
    "postprocess_results",
    "ClaimUpdateRequest",
    "ClaimUpdateSummary",
    "ClaimDecisionCriterion",
    "CriterionResult",
    "update_claim_status",
    "evaluate_claim_criteria",
    "load_claim_map",
    "load_evidence_index",
    "find_claim",
    "find_evidence",
    "GeometryReference",
    "CaeTargetReference",
    "ReferenceMap",
    "build_reference_map",
    "load_reference_map",
    "write_reference_map",
    "mark_references_needing_review",
]
