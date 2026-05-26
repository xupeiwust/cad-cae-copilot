"""Agent Observation Loop (v0.35.2).

After an :mod:`intent_planner` action executes, the planner consumer needs
a *structured* answer to four questions:

  1. What happened? (status, summary, runtime errors)
  2. What changed in the package? (artifact_changes, evidence_refs, stale_changes)
  3. What can — or cannot — be claimed now? (readiness_delta, warnings, claim_boundary)
  4. What should happen next? (next_recommended_actions)

This module is a *pure* observation layer over the existing runtime state.
It never executes a tool, never mutates the package, and never bypasses
the approval gate. It reads ``RunRecord`` plus the action/plan that was
submitted, plus an optional structural preflight snapshot pair, and
returns a JSON-serialisable ``IntentObservation`` dictionary.

The recommender (``next_recommended_actions``) is heuristic; the next
recommendation list is *advice*, not a queued auto-run. A user must
still pick the next action manually.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal


from .honesty import AGENT_OBSERVATION_CLAIM_BOUNDARY as CLAIM_BOUNDARY

SCHEMA_VERSION = "0.1"


ObservationStatus = Literal[
    "submitted_for_approval",
    "approved_executed",
    "completed",
    "rejected",
    "failed",
]


# ── helpers ──────────────────────────────────────────────────────────────────


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_str_list(items: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if item is None:
            continue
        out.append(str(item))
    return out


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _tool_result_artifacts(tool_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Read artifact records out of a runtime tool result.

    The runtime executor hoists ``output["artifacts"]`` into
    ``ToolResult.artifacts`` when the handler returns a plural list. But the
    engineering_template handlers return:

      * ``artifacts: [...]`` (save_draft) — hoisted automatically.
      * ``artifact: {...}`` (generate_cad_fixture) — singular; not hoisted.
      * ``document``/``targets`` (adopt_targets) — no artifact list.

    We accept any of the above and normalize to a list of artifact dicts.
    """
    out: list[dict[str, Any]] = []
    raw = tool_result.get("artifacts")
    if isinstance(raw, list):
        for artifact in raw:
            if isinstance(artifact, dict):
                out.append(artifact)
    output = tool_result.get("output") if isinstance(tool_result.get("output"), dict) else None
    if output is None:
        return out
    singular = output.get("artifact")
    if isinstance(singular, dict) and singular not in out:
        out.append(singular)
    artifact_path = output.get("artifact_path")
    if isinstance(artifact_path, str) and artifact_path:
        if not any(a.get("path") == artifact_path for a in out):
            out.append({"path": artifact_path, "kind": "package_member"})
    return out


def _stale_paths_from_output(output: Any) -> list[str]:
    if not isinstance(output, dict):
        return []
    raw = output.get("stale_artifacts")
    if not isinstance(raw, list):
        return []
    paths: list[str] = []
    for item in raw:
        if isinstance(item, str):
            paths.append(item)
        elif isinstance(item, dict):
            path = item.get("path")
            if isinstance(path, str):
                paths.append(path)
    return paths


def _evidence_refs_for_action(
    tool_name: str,
    outputs: list[dict[str, Any]],
) -> list[str]:
    """Best-effort evidence reference extraction.

    The intent planner sends a single-action plan to the runtime, so we read
    the one tool result. Evidence references are the package-relative paths
    of artifacts produced; for adopt-targets we surface the design-targets
    artifact path explicitly because it is not in ``artifacts``.
    """
    refs: list[str] = []
    for tool_result in outputs:
        for artifact in _tool_result_artifacts(tool_result):
            path = artifact.get("path")
            if isinstance(path, str) and path:
                refs.append(path)
        output = tool_result.get("output")
        if isinstance(output, dict):
            for key in ("artifact_path", "revalidation_status_path"):
                value = output.get(key)
                if isinstance(value, str) and value:
                    refs.append(value)
            # adopt_targets returns an artifact_path string for design_targets.
            if tool_name == "engineering_template.adopt_targets":
                doc_path = output.get("artifact_path")
                if isinstance(doc_path, str) and doc_path:
                    refs.append(doc_path)
    return _dedupe_keep_order(refs)


def _audit_event_ids_from_run(run: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for event in _ensure_list(run.get("events")):
        if isinstance(event, dict):
            ev_id = event.get("id")
            if isinstance(ev_id, str):
                ids.append(ev_id)
    return ids


# ── status mapping ───────────────────────────────────────────────────────────


def _map_status(run_status: str, requires_approval: bool) -> ObservationStatus:
    if run_status == "awaiting_approval":
        return "submitted_for_approval"
    if run_status == "completed":
        return "approved_executed" if requires_approval else "completed"
    if run_status == "rejected":
        return "rejected"
    if run_status == "failed":
        return "failed"
    # pending / running / cancelled — surface them as submitted_for_approval
    # so the UI keeps the action card in a "waiting" affordance instead of
    # claiming completion.
    return "submitted_for_approval"


# ── summary ──────────────────────────────────────────────────────────────────


def _summary_for(
    *,
    status: ObservationStatus,
    action: dict[str, Any],
    artifact_changes: list[dict[str, Any]],
    stale_changes: list[str],
    errors: list[str],
) -> str:
    tool_name = str(action.get("tool_name") or "")
    label = str(action.get("label") or tool_name or "intent action")
    if status == "submitted_for_approval":
        return (
            f"{label}: submitted for approval. No package write has occurred yet — "
            "approval is required before this action takes effect."
        )
    if status == "rejected":
        return (
            f"{label}: rejected by reviewer. No package write occurred; downstream "
            "evidence remains unchanged."
        )
    if status == "failed":
        first_error = errors[0] if errors else "unknown error"
        return f"{label}: execution failed ({first_error})."
    if status in {"approved_executed", "completed"}:
        wrote = len(artifact_changes)
        if wrote == 0:
            base = (
                f"{label}: completed. No artifact change was reported by the tool "
                "(read-only or inline result)."
            )
        else:
            base = (
                f"{label}: completed. {wrote} artifact change(s) recorded."
            )
        if stale_changes:
            base += f" {len(stale_changes)} downstream artifact(s) now stale."
        return base
    return f"{label}: status={status}."


# ── readiness delta ──────────────────────────────────────────────────────────


def _readiness_snapshot(preflight: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(preflight, dict):
        return None
    inner = preflight.get("preflight") if isinstance(preflight.get("preflight"), dict) else preflight
    ready = inner.get("ready_to_run")
    if ready is None and "ready_to_run" in preflight:
        ready = preflight.get("ready_to_run")
    missing = inner.get("missing_items")
    if not isinstance(missing, list):
        missing = preflight.get("missing_items") if isinstance(preflight.get("missing_items"), list) else []
    return {
        "ready_to_run": bool(ready),
        "missing_items": [str(m) for m in (missing or [])],
    }


def _readiness_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    before_snap = _readiness_snapshot(before)
    after_snap = _readiness_snapshot(after)
    if before_snap is None and after_snap is None:
        return {
            "evaluated": False,
            "before": None,
            "after": None,
            "resolved_items": [],
            "newly_missing_items": [],
            "note": "Structural readiness was not evaluated for this action.",
        }
    before_items = set(before_snap["missing_items"]) if before_snap else set()
    after_items = set(after_snap["missing_items"]) if after_snap else set()
    return {
        "evaluated": True,
        "before": before_snap,
        "after": after_snap,
        "resolved_items": sorted(before_items - after_items),
        "newly_missing_items": sorted(after_items - before_items),
    }


# ── next recommended actions (heuristic) ─────────────────────────────────────


def _rec(kind: str, label: str, rationale: str, **extra: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "kind": kind,
        "label": label,
        "rationale": rationale,
    }
    rec.update(extra)
    return rec


def next_recommended_actions(
    plan: dict[str, Any],
    action: dict[str, Any],
    status: ObservationStatus,
    *,
    readiness: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Heuristic recommender. Returns *advice*, not a queued plan."""
    tool_name = str(action.get("tool_name") or "")
    template_id = plan.get("inferred_template_id") if isinstance(plan, dict) else None
    missing_information = _ensure_list(plan.get("missing_information")) if isinstance(plan, dict) else []
    refusals = _ensure_list(plan.get("refusals")) if isinstance(plan, dict) else []
    proposed_tools = {
        str(a.get("tool_name")) for a in _ensure_list(plan.get("actions") or [])
        if isinstance(a, dict)
    } if isinstance(plan, dict) else set()

    out: list[dict[str, Any]] = []

    # Premature-solver refusal → guide the user to resolve readiness gaps.
    refusal_tools = {r.get("tool_name") for r in refusals if isinstance(r, dict)}
    if "cae.run_solver" in refusal_tools:
        for item in missing_information:
            if isinstance(item, str) and item.startswith("solver_run_readiness:"):
                out.append(_rec(
                    "resolve_readiness_gap",
                    f"Resolve missing solver-run readiness item: {item.split(':', 1)[1]}",
                    rationale=(
                        "The planner refused to execute the solver from natural "
                        "language. Resolve each readiness gap via its dedicated card "
                        "(structural adapter / mesh / load case) before approving a "
                        "solver run."
                    ),
                    reference="structural_adapter",
                ))
        if not out:
            out.append(_rec(
                "resolve_readiness_gap",
                "Open the Structural Adapter card to address solver readiness gaps.",
                rationale="Solver execution stays approval-gated outside the planner.",
                reference="structural_adapter",
            ))

    # Status-dependent recommendations.
    if status == "submitted_for_approval":
        out.append(_rec(
            "await_approval",
            "Approve or reject this action in the Pilot Console.",
            rationale=(
                "Approval-gated actions never run silently. The runtime will not "
                "write to the package until you explicitly approve."
            ),
            reference="runtime_approval",
        ))
        return _dedupe_recs(out)

    if status == "rejected":
        out.append(_rec(
            "regenerate_plan",
            "Regenerate the plan with refined requirements.",
            rationale=(
                "The rejected action made no package change. Tighten the request or "
                "adjust constraints before proposing a new plan."
            ),
            reference="intent_planner",
        ))
        return _dedupe_recs(out)

    if status == "failed":
        out.append(_rec(
            "inspect_failure",
            "Review the runtime error and either fix inputs or open a different action.",
            rationale=(
                "Failures do not advance engineering claims. Treat the partial state "
                "as untrusted until you confirm what was written, if anything."
            ),
            reference="runtime_run",
        ))
        return _dedupe_recs(out)

    # status is approved_executed / completed
    if tool_name == "engineering_template.preview":
        if "engineering_template.save_draft" in proposed_tools:
            out.append(_rec(
                "execute_action",
                "Save the template draft into the project package.",
                rationale=(
                    "Preview confirmed the parameter set is valid. Saving the draft "
                    "is a metadata-write and remains approval-gated."
                ),
                reference="engineering_template.save_draft",
            ))
    elif tool_name == "engineering_template.save_draft":
        if "engineering_template.adopt_targets" in proposed_tools:
            out.append(_rec(
                "execute_action",
                "Adopt the suggested design targets into task/design_targets.yaml.",
                rationale=(
                    "Adoption merges the saved suggestions with existing targets and "
                    "feeds the target comparison engine."
                ),
                reference="engineering_template.adopt_targets",
            ))
        if "engineering_template.generate_cad_fixture" in proposed_tools:
            out.append(_rec(
                "execute_action",
                "Generate the deterministic CAD fixture metadata.",
                rationale=(
                    "Writes geometry/template_cad_fixture.json and marks downstream "
                    "mesh/result evidence stale. Approval-gated."
                ),
                reference="engineering_template.generate_cad_fixture",
            ))
    elif tool_name == "engineering_template.adopt_targets":
        if "engineering_template.generate_cad_fixture" in proposed_tools:
            out.append(_rec(
                "execute_action",
                "Generate the deterministic CAD fixture metadata.",
                rationale=(
                    "Targets are adopted; the CAD fixture closes the geometry side "
                    "of the controlled pilot path."
                ),
                reference="engineering_template.generate_cad_fixture",
            ))
        out.append(_rec(
            "inspect_evidence",
            "Refresh the Target Comparison card to verify pass/fail against the new targets.",
            rationale="Adopted targets only become evidence after a comparison run.",
            reference="target_comparison",
        ))
    elif tool_name == "engineering_template.generate_cad_fixture":
        out.append(_rec(
            "inspect_readiness",
            "Run the Structural Adapter preflight to see readiness gaps after the new fixture.",
            rationale=(
                "The CAD fixture marks mesh and solver evidence stale. Readiness for "
                "the next solver run must be reassessed before approving execution."
            ),
            reference="structural_adapter",
        ))
    elif tool_name == "aieng.inspect_package":
        if template_id and "engineering_template.preview" in proposed_tools:
            out.append(_rec(
                "execute_action",
                "Preview the controlled template draft.",
                rationale="Inspection confirmed project state; the template preview is the next safe step.",
                reference="engineering_template.preview",
            ))
    elif tool_name == "cae.prepare_solver_run":
        if readiness and not readiness.get("ready_to_run", True):
            out.append(_rec(
                "resolve_readiness_gap",
                "Address the missing structural-run readiness items before approving solver execution.",
                rationale=(
                    "The preflight reports the run is not ready. The planner will "
                    "continue to refuse direct solver execution until readiness passes."
                ),
                reference="structural_adapter",
            ))
        else:
            out.append(_rec(
                "open_structural_adapter",
                "Open the Structural Adapter card to start the approval-gated solver run.",
                rationale=(
                    "Preflight passed; solver execution remains explicit and "
                    "approval-gated. The planner does not execute it from natural language."
                ),
                reference="structural_adapter",
            ))

    # If the plan flagged missing engineering inputs (template not matched),
    # repeat them as guidance so the user knows what would unblock progress.
    if not template_id and missing_information:
        out.append(_rec(
            "request_missing_information",
            "Provide the missing engineering inputs and regenerate the plan.",
            rationale=(
                "No controlled template matched the request. AIENG will not "
                "synthesise a template; the listed inputs are needed first."
            ),
            reference="intent_planner",
            details=missing_information[:8],
        ))

    if not out:
        out.append(_rec(
            "review_observation",
            "Review this observation and decide the next manual step.",
            rationale=(
                "No deterministic next recommendation was derived. The Pilot Console "
                "shows the raw observation and the rest of the AIENG cards remain available."
            ),
            reference="intent_planner",
        ))
    return _dedupe_recs(out)


def _dedupe_recs(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for rec in recs:
        key = (str(rec.get("kind")), str(rec.get("label")))
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


# ── main entry ───────────────────────────────────────────────────────────────


def build_observation(
    *,
    plan: dict[str, Any],
    action: dict[str, Any],
    run: dict[str, Any],
    structural_preflight_before: dict[str, Any] | None = None,
    structural_preflight_after: dict[str, Any] | None = None,
    cad_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an :class:`IntentObservation` for a single executed action.

    Parameters
    ----------
    plan:
        The original :func:`intent_planner.plan_from_request` output.
    action:
        The chosen action dict from ``plan["actions"]``.
    run:
        ``runtime.run_to_dict(run)`` — the live run state. Pass the run state
        captured *after* the latest approve/reject/execute call so the
        observation reflects the user-visible state.
    structural_preflight_before / structural_preflight_after:
        Optional snapshots of
        :func:`structural_adapter.prepare_structural_run_preview`. When both
        are supplied the observation reports a real readiness delta;
        otherwise readiness is marked unevaluated.
    """
    requires_approval = bool(action.get("requires_approval"))
    status = _map_status(str(run.get("status") or ""), requires_approval)

    tool_results = _ensure_list(run.get("tool_results"))
    tool_results_dicts: list[dict[str, Any]] = [
        tr for tr in tool_results if isinstance(tr, dict)
    ]

    # Artifact changes — only meaningful for completed/approved runs. For
    # submitted_for_approval and rejected states, the package was not
    # written. We therefore emit an empty artifact_changes list to keep the
    # observation honest.
    artifact_changes: list[dict[str, Any]]
    stale_changes: list[str]
    evidence_refs: list[str]
    if status in {"approved_executed", "completed"}:
        artifact_changes = []
        for tr in tool_results_dicts:
            if tr.get("status") != "success":
                continue
            for artifact in _tool_result_artifacts(tr):
                artifact_changes.append({
                    "path": artifact.get("path"),
                    "kind": artifact.get("kind") or artifact.get("type") or "package_member",
                    "operation": artifact.get("operation") or artifact.get("op") or "write",
                })
        # honest stale collection: union of every successful tool's stale list.
        stale_changes_raw: list[str] = []
        for tr in tool_results_dicts:
            if tr.get("status") != "success":
                continue
            stale_changes_raw.extend(_stale_paths_from_output(tr.get("output")))
        stale_changes = _dedupe_keep_order(stale_changes_raw)
        evidence_refs = _evidence_refs_for_action(
            str(action.get("tool_name") or ""), tool_results_dicts
        )
    else:
        artifact_changes = []
        stale_changes = []
        evidence_refs = []

    errors = _as_str_list(_ensure_list(run.get("errors")))
    warnings: list[str] = []
    for tr in tool_results_dicts:
        output = tr.get("output")
        if isinstance(output, dict):
            warnings.extend(_as_str_list(_ensure_list(output.get("warnings"))))
    if status in {"submitted_for_approval"}:
        warnings.append(
            "Approval is required. No package write has occurred for this action yet."
        )
    if status in {"rejected", "failed"}:
        warnings.append(
            "No artifact changes are recorded because the action did not complete successfully."
        )
    warnings = _dedupe_keep_order(warnings)

    readiness_delta = _readiness_delta(
        structural_preflight_before, structural_preflight_after,
    )

    summary = _summary_for(
        status=status,
        action=action,
        artifact_changes=artifact_changes,
        stale_changes=stale_changes,
        errors=errors,
    )

    recs = next_recommended_actions(
        plan,
        action,
        status,
        readiness=readiness_delta.get("after") if readiness_delta.get("evaluated") else None,
    )

    # Surface CAD observation recommendations into the IntentObservation
    # recommender list so the UI only has to render one "next steps" block
    # per action. Source-of-truth detail still lives under
    # ``cad_observation``.
    if isinstance(cad_observation, dict):
        cad_recs = cad_observation.get("next_recommended_actions")
        if isinstance(cad_recs, list):
            recs = _dedupe_recs(list(recs) + [r for r in cad_recs if isinstance(r, dict)])
        cad_warnings = cad_observation.get("warnings")
        if isinstance(cad_warnings, list):
            warnings = _dedupe_keep_order(warnings + [str(w) for w in cad_warnings if w])

    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan.get("plan_id") if isinstance(plan, dict) else None,
        "action_id": action.get("id"),
        "run_id": run.get("run_id"),
        "tool_name": action.get("tool_name"),
        "mode": action.get("mode"),
        "status": status,
        "summary": summary,
        "artifact_changes": artifact_changes,
        "evidence_refs": evidence_refs,
        "audit_event_ids": _audit_event_ids_from_run(run),
        "stale_changes": stale_changes,
        "readiness_delta": readiness_delta,
        "warnings": warnings,
        "errors": errors,
        "cad_observation": cad_observation,
        "claim_advancement": "none",
        "claim_boundary": CLAIM_BOUNDARY,
        "next_recommended_actions": recs,
    }


__all__ = [
    "CLAIM_BOUNDARY",
    "ObservationStatus",
    "SCHEMA_VERSION",
    "build_observation",
    "next_recommended_actions",
]
