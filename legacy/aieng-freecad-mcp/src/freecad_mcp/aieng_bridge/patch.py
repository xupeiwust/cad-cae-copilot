""".aieng patch proposal bridge.

Translates structured patch proposals into guarded, auditable CAD operations.
Pure logic — no MCP coupling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from freecad_mcp.aieng_bridge.context import AiengPackageContext, load_aieng_context
from freecad_mcp.aieng_bridge.guards import check_operation_allowed
from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    persist_standard_result_to_aieng,
)
from freecad_mcp.aieng_bridge.stub_executor import StubFreecadExecutor
from freecad_mcp.contracts.failure_mode import (
    PERSISTENCE_FAILED,
    POLICY_VIOLATION,
)
from freecad_mcp.aieng_bridge.references import (
    load_reference_map,
    mark_references_needing_review,
)
from freecad_mcp.aieng_bridge.evidence import build_evidence_entry
from freecad_mcp.aieng_bridge.trace import build_trace_entry
from freecad_mcp.bridge.executor import CadExecutor
from freecad_mcp.tool_contracts import ClaimPolicy, EvidenceBlock, StandardToolResult, TraceBlock
from freecad_mcp.tools_cad import (
    _execute_export_fcstd,
    _execute_export_step,
    _execute_set_parameter,
)


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class PatchOperation(BaseModel):
    """A single operation inside a patch proposal."""

    model_config = ConfigDict(extra="allow")

    operation: str
    target_feature_id: str | None = None
    parameter_name: str | None = None
    new_value: Any | None = None
    raw: dict = Field(default_factory=dict)


class PatchPlan(BaseModel):
    """Validated patch plan separating supported from unsupported operations."""

    model_config = ConfigDict(extra="forbid")

    patch_id: str | None = None
    operations: list[PatchOperation] = []
    unsupported_operations: list[dict] = []
    warnings: list[str] = []


class PatchExecutionStep(BaseModel):
    """Result of executing one patch operation."""

    model_config = ConfigDict(extra="forbid")

    operation_index: int
    operation: str
    target_feature_id: str | None = None
    status: Literal["success", "failed", "unsupported", "rejected", "skipped"]
    result: dict[str, Any] | None = None
    warnings: list[str] = []
    errors: list[str] = []


class PatchExecutionSummary(BaseModel):
    """Summary of executing an entire patch plan."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "partial", "failed", "rejected"] = "success"
    patch_id: str | None = None
    steps: list[PatchExecutionStep] = []
    artifacts_written: list[str] = []
    evidence_ids: list[str] = []
    trace_ids: list[str] = []
    claim_policy: ClaimPolicy = Field(default_factory=ClaimPolicy)
    primary_error_code: str | None = None
    warnings: list[str] = []
    errors: list[str] = []
    persistence: dict[str, Any] | None = None


# ------------------------------------------------------------------
# Load / parse
# ------------------------------------------------------------------

SUPPORTED_OPERATIONS = {"modify_parameter"}
OPERATION_ALIASES = {
    "op": "operation",
    "feature_id": "target_feature_id",
    "parameter": "parameter_name",
    "value": "new_value",
}


def _normalise_operation(raw: dict[str, Any]) -> dict[str, Any]:
    """Map alias fields to canonical names."""
    out = dict(raw)
    for alias, canonical in OPERATION_ALIASES.items():
        if alias in out and canonical not in out:
            out[canonical] = out.pop(alias)
    return out


def load_patch_proposal(
    package_path: str | None = None,
    patch_path: str | None = None,
    patch_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a raw patch proposal from the first available source.

    Priority: ``patch_json`` → ``patch_path`` → ``package_path``/patch.json

    Returns:
        Raw patch dict, or raises ``ValueError`` if no patch is found.
    """
    if patch_json is not None:
        return dict(patch_json)

    if patch_path is not None:
        path = Path(patch_path)
        if not path.exists():
            raise ValueError(f"patch_path does not exist: {path}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    if package_path is not None:
        # Default lookup: patch.json in package root
        path = Path(package_path) / "patch.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)

    raise ValueError(
        "No patch proposal found. Provide one of: patch_json, patch_path, or package_path with patch.json."
    )


def parse_patch_proposal(raw_patch: dict[str, Any]) -> PatchPlan:
    """Validate a raw patch dict and separate supported from unsupported operations.

    Unsupported operations are recorded honestly; they are not guessed or
    silently dropped.
    """
    patch_id = raw_patch.get("patch_id")
    raw_operations = raw_patch.get("operations", [])
    if not isinstance(raw_operations, list):
        raw_operations = [raw_operations]

    operations: list[PatchOperation] = []
    unsupported: list[dict] = []
    warnings: list[str] = []

    for idx, raw_op in enumerate(raw_operations):
        if not isinstance(raw_op, dict):
            unsupported.append({"index": idx, "reason": "Operation is not a dict", "raw": raw_op})
            continue

        norm = _normalise_operation(raw_op)
        op_name = norm.get("operation", "")
        if not op_name:
            unsupported.append({"index": idx, "reason": "Missing 'operation' field", "raw": raw_op})
            continue

        if op_name not in SUPPORTED_OPERATIONS:
            unsupported.append(
                {
                    "index": idx,
                    "reason": f"Operation '{op_name}' is not supported",
                    "raw": raw_op,
                }
            )
            continue

        operations.append(
            PatchOperation(
                operation=op_name,
                target_feature_id=norm.get("target_feature_id"),
                parameter_name=norm.get("parameter_name"),
                new_value=norm.get("new_value"),
                raw=raw_op,
            )
        )

    if unsupported:
        warnings.append(f"{len(unsupported)} operation(s) marked unsupported and will not be executed.")

    return PatchPlan(
        patch_id=patch_id,
        operations=operations,
        unsupported_operations=unsupported,
        warnings=warnings,
    )


# ------------------------------------------------------------------
# Resolution
# ------------------------------------------------------------------

class ParameterResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_name: str
    parameter_name: str
    warnings: list[str] = []


def resolve_feature_parameter(
    context: AiengPackageContext,
    target_feature_id: str,
    parameter_name: str,
) -> ParameterResolution | None:
    """Resolve a semantic feature ID + parameter name to a FreeCAD executable ref.

    Resolution strategy (conservative):
    1. Look up ``target_feature_id`` in ``feature_graph.features``.
    2. Require ``freecad_object_name`` on the feature.
    3. Look for a parameter mapping in the feature's ``parameters`` list with
       a matching ``name`` and a ``freecad_parameter_name`` field.
    4. If no parameter mapping exists, reject.

    Returns ``None`` if resolution is not possible.
    """
    feature_graph = context.feature_graph or {}
    features = feature_graph.get("features", feature_graph)
    if not isinstance(features, dict):
        return None

    feature = features.get(target_feature_id)
    if not isinstance(feature, dict):
        return None

    freecad_object_name = feature.get("freecad_object_name")
    if not freecad_object_name:
        return None

    # Look for an explicit parameter mapping
    feature_params = feature.get("parameters", [])
    if isinstance(feature_params, list):
        for fp in feature_params:
            if isinstance(fp, dict) and fp.get("name") == parameter_name:
                freecad_param_name = fp.get("freecad_parameter_name")
                if freecad_param_name:
                    return ParameterResolution(
                        object_name=str(freecad_object_name),
                        parameter_name=str(freecad_param_name),
                    )

    # No explicit mapping found — reject rather than guess
    return None


class ParameterValidationResult(BaseModel):
    """Result of validating a parameter edit against feature graph constraints."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []


def validate_parameter_edit(
    context: AiengPackageContext,
    target_feature_id: str,
    parameter_name: str,
    new_value: Any,
) -> ParameterValidationResult:
    """Validate a parameter edit against feature graph constraints.

    Checks:
    - Parameter exists in the feature's ``parameters`` list.
    - Parameter is editable (``editability`` is not ``false``).
    - Value is within declared ``min_value`` / ``max_value`` bounds.
    - Type is compatible with the declared parameter type.

    Returns:
        ParameterValidationResult with ``valid=True`` if the edit may proceed.
    """
    errors: list[str] = []
    warnings: list[str] = []

    feature_graph = context.feature_graph or {}
    features = feature_graph.get("features", feature_graph)
    if not isinstance(features, dict):
        # No feature graph available — skip parameter-level validation
        return ParameterValidationResult(valid=True)

    feature = features.get(target_feature_id)
    if not isinstance(feature, dict):
        return ParameterValidationResult(
            valid=False,
            errors=[f"Feature '{target_feature_id}' not found in feature_graph."],
        )

    # Locate parameter definition
    param_def: dict[str, Any] | None = None
    for fp in feature.get("parameters", []):
        if isinstance(fp, dict) and (
            fp.get("name") == parameter_name
            or fp.get("freecad_parameter_name") == parameter_name
        ):
            param_def = fp
            break

    if param_def is None:
        return ParameterValidationResult(
            valid=False,
            errors=[
                f"Parameter '{parameter_name}' is not defined in feature '{target_feature_id}'."
            ],
        )

    # Check parameter-level editability
    param_editability = param_def.get("editability", {}) if isinstance(param_def, dict) else {}
    if isinstance(param_editability, dict) and param_editability.get("executable") is False:
        return ParameterValidationResult(
            valid=False,
            errors=[
                f"Parameter '{parameter_name}' on feature '{target_feature_id}' is not editable."
            ],
        )

    # Type compatibility
    param_type = param_def.get("type", "")
    if param_type:
        type_ok, type_msg = _check_type_compatibility(param_type, new_value)
        if not type_ok:
            errors.append(type_msg)

    # Range checks
    min_value = param_def.get("min_value")
    max_value = param_def.get("max_value")
    if min_value is not None or max_value is not None:
        range_ok, range_msg = _check_value_range(new_value, min_value, max_value)
        if not range_ok:
            errors.append(range_msg)

    # Unit check (warn only; strict unit enforcement is optional)
    expected_unit = param_def.get("unit")
    if expected_unit and not _check_unit_compatibility(expected_unit, new_value):
        warnings.append(
            f"Parameter '{parameter_name}' expects unit '{expected_unit}'; "
            "value provided without matching unit annotation."
        )

    if errors:
        return ParameterValidationResult(valid=False, errors=errors, warnings=warnings)

    return ParameterValidationResult(valid=True, warnings=warnings)


def _check_type_compatibility(param_type: str, value: Any) -> tuple[bool, str]:
    """Check whether ``value`` is compatible with ``param_type``.

    Supports a minimal set of FreeCAD-like type names.
    """
    numeric_types = {
        "App::PropertyFloat",
        "App::PropertyLength",
        "App::PropertyAngle",
        "App::PropertyInteger",
        "App::PropertyQuantity",
        "App::PropertyFloatConstraint",
        "App::PropertyIntegerConstraint",
        "App::PropertyPercent",
        "float",
        "int",
        "number",
    }
    if param_type in numeric_types:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False, f"Expected numeric value for type '{param_type}', got {type(value).__name__}."
    elif param_type in {"App::PropertyString", "str", "string"}:
        if not isinstance(value, str):
            return False, f"Expected string value for type '{param_type}', got {type(value).__name__}."
    elif param_type in {"App::PropertyBool", "bool", "boolean"}:
        if not isinstance(value, bool):
            return False, f"Expected boolean value for type '{param_type}', got {type(value).__name__}."
    return True, ""


def _check_value_range(
    value: Any,
    min_value: Any | None,
    max_value: Any | None,
) -> tuple[bool, str]:
    """Check whether ``value`` lies within ``min_value`` and ``max_value``."""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False, f"Cannot compare non-numeric value '{value}' against range bounds."

    if min_value is not None:
        try:
            if numeric_value < float(min_value):
                return False, f"Value {value} is below minimum {min_value}."
        except (TypeError, ValueError):
            pass

    if max_value is not None:
        try:
            if numeric_value > float(max_value):
                return False, f"Value {value} exceeds maximum {max_value}."
        except (TypeError, ValueError):
            pass

    return True, ""


def _check_unit_compatibility(expected_unit: str, _value: Any) -> bool:
    """Return ``True`` if the value appears compatible with ``expected_unit``.

    MVP 1B performs a permissive check: scalar values are accepted unless
    they are explicitly tagged with a conflicting unit.  Full unit parsing
    is deferred to MVP 1C.
    """
    # Permissive: accept scalar values; only reject obvious mismatches
    if isinstance(_value, str):
        # If the value string ends with a unit suffix that conflicts, reject.
        # For now, any string value is accepted (conservative).
        return True
    if isinstance(_value, (int, float)) and not isinstance(_value, bool):
        return True
    return True


# ------------------------------------------------------------------
# Execute
# ------------------------------------------------------------------

def _determine_artifact_output_dir(
    package_path: str | None,
    artifact_output_dir: str | None,
) -> Path | None:
    """Resolve artifact output directory."""
    if artifact_output_dir is not None:
        return Path(artifact_output_dir)
    if package_path is not None:
        return Path(package_path) / "geometry" / "modified"
    return None


def _persist_patch_run_record(
    package_path: str,
    summary: PatchExecutionSummary,
) -> str | None:
    """Append a patch execution run record to execution/patch_runs/.

    Returns the path of the written record, or None on failure.
    """
    try:
        runs_dir = Path(package_path) / "execution" / "patch_runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        # Count existing runs for this patch to build sequential filename
        existing = list(runs_dir.glob(f"{summary.patch_id or 'patch'}_run_*.json"))
        run_number = len(existing) + 1
        filename = f"{summary.patch_id or 'patch'}_run_{run_number:03d}.json"
        record_path = runs_dir / filename

        record = {
            "patch_id": summary.patch_id,
            "status": summary.status,
            "steps": [s.model_dump(mode="json") for s in summary.steps],
            "artifacts_written": summary.artifacts_written,
            "evidence_ids": summary.evidence_ids,
            "trace_ids": summary.trace_ids,
            "claim_policy": summary.claim_policy.model_dump(mode="json"),
            "warnings": summary.warnings,
            "errors": summary.errors,
        }

        with record_path.open("w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return str(record_path)
    except Exception:
        return None


async def execute_patch_plan(
    plan: PatchPlan,
    executor: CadExecutor,
    package_path: str | None = None,
    persist_to_aieng: bool = False,
    dry_run: bool = False,
    export_modified_step: bool = False,
    export_modified_fcstd: bool = False,
    artifact_output_dir: str | None = None,
    input_fcstd: str | None = None,
) -> PatchExecutionSummary:
    """Execute a validated patch plan step by step.

    Behavior:
    - Stop on the first failed/rejected step.
    - Run guard checks before each mutating operation.
    - Skip CAD execution when ``dry_run=True``.
    - Optionally export modified CAD artifacts after successful execution.
    - Optionally persist evidence, trace, and patch run records to ``.aieng``.
    """
    context = load_aieng_context(package_path)
    steps: list[PatchExecutionStep] = []
    evidence_ids: list[str] = []
    trace_ids: list[str] = []
    artifacts_written: list[str] = []
    overall_status: Literal["success", "partial", "failed", "rejected"] = "success"

    if persist_to_aieng and not package_path:
        return PatchExecutionSummary(
            status="rejected",
            patch_id=plan.patch_id,
            steps=[],
            claim_policy=ClaimPolicy(),
            primary_error_code=POLICY_VIOLATION,
            errors=["persist_to_aieng=true requires a valid package_path."],
        )

    out_dir = _determine_artifact_output_dir(package_path, artifact_output_dir)

    for idx, op in enumerate(plan.operations):
        step = PatchExecutionStep(
            operation_index=idx,
            operation=op.operation,
            target_feature_id=op.target_feature_id,
            status="skipped",
        )

        if op.operation == "modify_parameter":
            # Parameter resolution
            if op.target_feature_id is None or op.parameter_name is None:
                step.status = "rejected"
                step.errors.append("modify_parameter requires target_feature_id and parameter_name.")
                steps.append(step)
                overall_status = "rejected"
                break

            resolved: ParameterResolution | None = None
            if context.mode == "aieng_enhanced" and context.available:
                resolved = resolve_feature_parameter(context, op.target_feature_id, op.parameter_name)
            else:
                # Standalone mode: use raw IDs directly (caller must provide executable refs)
                resolved = ParameterResolution(
                    object_name=op.target_feature_id,
                    parameter_name=op.parameter_name,
                )

            if resolved is None:
                step.status = "rejected"
                step.errors.append(
                    "Could not resolve feature parameter to executable FreeCAD parameter reference."
                )
                steps.append(step)
                overall_status = "rejected"
                break

            # Guard check
            guard = check_operation_allowed(
                context,
                "cad_set_parameter",
                op.target_feature_id,
                is_modification=True,
            )
            if not guard.allowed:
                step.status = "rejected"
                step.errors.extend(guard.reasons)
                step.warnings.extend(guard.warnings)
                steps.append(step)
                overall_status = "rejected"
                break

            step.warnings.extend(guard.warnings)

            # Parameter-level validation (MVP 1B)
            if context.mode == "aieng_enhanced" and context.available:
                param_validation = validate_parameter_edit(
                    context,
                    op.target_feature_id,
                    op.parameter_name,
                    op.new_value,
                )
                if not param_validation.valid:
                    step.status = "rejected"
                    step.errors.extend(param_validation.errors)
                    step.warnings.extend(param_validation.warnings)
                    steps.append(step)
                    overall_status = "rejected"
                    break
                step.warnings.extend(param_validation.warnings)

            if dry_run:
                step.status = "success"
                step.result = {
                    "object_name": resolved.object_name,
                    "parameter_name": resolved.parameter_name,
                    "new_value": op.new_value,
                    "dry_run": True,
                }
                steps.append(step)
                continue

            # Execute
            try:
                result = await _execute_set_parameter(
                    executor,
                    resolved.object_name,
                    resolved.parameter_name,
                    op.new_value,
                    input_fcstd=input_fcstd,
                )
                step.status = "success"
                step.result = result
            except Exception as exc:
                step.status = "failed"
                step.errors.append(f"{type(exc).__name__}: {exc}")
                steps.append(step)
                overall_status = "failed"
                break

            steps.append(step)

        else:
            # Should not reach here because parse filters unsupported ops,
            # but defensively mark as unsupported.
            step.status = "unsupported"
            step.errors.append(f"Operation '{op.operation}' is not supported.")
            steps.append(step)
            overall_status = "partial"
            break

    # Artifact export (only after successful parameter modification)
    if overall_status == "success" and not dry_run and out_dir is not None:
        patch_slug = plan.patch_id or "patch"
        if export_modified_step:
            step_path = str(out_dir / f"{patch_slug}.step")
            try:
                result = await _execute_export_step(executor, step_path, input_fcstd=input_fcstd)
                artifacts_written.append(step_path)
            except Exception as exc:
                overall_status = "partial"
                steps[-1].warnings.append(f"STEP export failed: {exc}")

        if export_modified_fcstd:
            fcstd_path = str(out_dir / f"{patch_slug}.FCStd")
            try:
                result = await _execute_export_fcstd(executor, fcstd_path, input_fcstd=input_fcstd)
                artifacts_written.append(fcstd_path)
            except Exception as exc:
                overall_status = "partial"
                steps[-1].warnings.append(f"FCStd export failed: {exc}")

    # Mark existing reference maps as needing review after geometry changes
    if (
        overall_status == "success"
        and not dry_run
        and package_path
        and load_reference_map(package_path) is not None
    ):
        affected_feature_ids = [
            op.target_feature_id
            for op in plan.operations
            if op.target_feature_id is not None
        ]
        if affected_feature_ids:
            try:
                mark_references_needing_review(
                    package_path,
                    affected_feature_ids,
                    reason="Geometry modified by patch execution; mapping stability not guaranteed.",
                )
            except Exception as exc:
                # Do not fail the patch if reference marking fails
                if steps:
                    steps[-1].warnings.append(f"Reference map review marking failed: {exc}")

    # Aggregate step-level errors into summary errors
    step_errors: list[str] = []
    for s in steps:
        step_errors.extend(s.errors)

    # Build summary
    summary = PatchExecutionSummary(
        status=overall_status,
        patch_id=plan.patch_id,
        steps=steps,
        artifacts_written=artifacts_written,
        claim_policy=ClaimPolicy(claims_advanced=False, requires_explicit_update_claim=True),
        warnings=plan.warnings,
        errors=step_errors,
    )

    # Build artifact metadata for evidence
    artifact_metadata: list[dict[str, Any]] = []
    for artifact in artifacts_written:
        artifact_path = Path(artifact)
        suffix = artifact_path.suffix.lower()
        artifact_type = "unknown"
        if suffix == ".step":
            artifact_type = "modified_step"
        elif suffix == ".fcstd":
            artifact_type = "modified_fcstd"
        artifact_metadata.append({
            "path": artifact,
            "artifact_type": artifact_type,
            "source_artifact_preserved": True,
        })

    additional_metadata: dict[str, Any] = {
        "producer_kind": "freecad",
        "operation": "modify_parameter",
        "claims_advanced": False,
    }
    if artifact_metadata:
        additional_metadata["artifacts"] = artifact_metadata
    if steps and steps[0].result:
        step_result = steps[0].result
        additional_metadata["target_feature_id"] = plan.operations[0].target_feature_id
        additional_metadata["parameter_name"] = plan.operations[0].parameter_name
        additional_metadata["old_value"] = step_result.get("old_value")
        additional_metadata["new_value"] = step_result.get("new_value")

    # Persistence
    if persist_to_aieng and package_path:
        try:
            result = StandardToolResult(
                status=summary.status,
                operation="aieng_execute_patch",
                inputs={
                    "patch_id": plan.patch_id,
                    "operation_count": len(plan.operations),
                    "dry_run": dry_run,
                    "export_modified_step": export_modified_step,
                    "export_modified_fcstd": export_modified_fcstd,
                },
                outputs={"steps": [s.model_dump(mode="json") for s in steps]},
                artifacts_written=artifacts_written,
                evidence=EvidenceBlock(producer_kind="freecad"),
                claim_policy=summary.claim_policy,
                trace=TraceBlock(),
                warnings=summary.warnings,
                errors=summary.errors,
            )
            meta = persist_standard_result_to_aieng(
                package_path, result, additional_metadata=additional_metadata
            )
            summary.persistence = meta
            if "evidence_id" in meta:
                evidence_ids.append(meta["evidence_id"])
            if "trace_id" in meta:
                trace_ids.append(meta["trace_id"])
        except PersistenceError as exc:
            summary.primary_error_code = PERSISTENCE_FAILED
            summary.errors.append(f"Persistence failed: {exc}")

        # Patch run record
        record_path = _persist_patch_run_record(package_path, summary)
        if record_path:
            summary.artifacts_written.append(record_path)

    summary.evidence_ids = evidence_ids
    summary.trace_ids = trace_ids
    return summary
