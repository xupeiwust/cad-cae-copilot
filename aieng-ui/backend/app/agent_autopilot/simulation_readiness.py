"""Deterministic /simulate readiness report (v1.5).

Pure and side-effect-free. Inspects a normalized CAE setup view (the ``cae``
block of ``aieng.agent_context``) and reports whether the six core simulation
inputs are present / missing / defaultable / unknown, so the /simulate agent can
ask the user for missing *required* inputs instead of guessing.

This module never runs the solver, never touches CAD, and never bypasses
approval — it only produces prompt/context. v1.5 deliberately does NOT validate
deep physics; it is a structured, conservative readiness summary built from the
already-computed CAE context block.
"""

from __future__ import annotations

from typing import Any

from .mention_binding import bindings_to_targets, mention_status_word

# --- Status vocabulary ------------------------------------------------------
STATUS_PRESENT = "present"        # the setup clearly defines this input
STATUS_MISSING = "missing"        # a required input is absent (must ask the user)
STATUS_DEFAULTABLE = "defaultable"  # not set, but a sensible default exists for planning
STATUS_UNKNOWN = "unknown"        # cannot determine (e.g. explicitly unavailable)

# --- The six core inputs ----------------------------------------------------
# Required for solver execution — a missing one blocks a real run and the agent
# must ask the user for it.
REQUIRED_INPUTS: tuple[str, ...] = ("material", "loads", "constraints")
# Defaultable for planning unless explicitly unavailable.
DEFAULTABLE_INPUTS: tuple[str, ...] = ("analysis_type", "mesh", "solver")
CORE_INPUTS: tuple[str, ...] = ("analysis_type", "material", "loads", "constraints", "mesh", "solver")

_DEFAULT_ANALYSIS_TYPE = "linear_static"
_DEFAULT_SOLVER = "CalculiX"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _count(cae: dict[str, Any], *keys: str) -> int:
    """Best-effort count across list-valued and *_count integer keys."""
    total = 0
    for key in keys:
        value = cae.get(key)
        if isinstance(value, (list, tuple)):
            total = max(total, len(value))
        elif isinstance(value, int) and not isinstance(value, bool):
            total = max(total, value)
    return total


def _draft_has(draft: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = draft.get(key)
        if isinstance(value, (list, tuple, dict)) and len(value):
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _explicitly_unavailable(value: Any) -> bool:
    """True only when the setup *explicitly* marks something unavailable.

    A plain absence is NOT unavailable (it stays defaultable); only an explicit
    ``False`` / ``{"available": False}`` counts.
    """
    if value is False:
        return True
    if isinstance(value, dict) and value.get("available") is False:
        return True
    return False


def build_simulation_readiness_report(
    cae: dict[str, Any] | None,
    *,
    mention_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a structured, deterministic simulation-readiness report.

    ``cae`` is the ``cae`` block of ``aieng.agent_context`` (or None when no CAE
    context is available). ``mention_bindings`` are the resolved @part/@artifact
    bindings (see ``mention_binding.build_mention_bindings``); the report reuses
    them for its ``targets`` instead of duplicating the lookup. The report never
    asserts that the solver ran.
    """
    cae = _as_dict(cae)
    draft = _as_dict(cae.get("fea_setup_draft"))

    material_present = _count(cae, "materials", "materials_count") > 0 or _draft_has(draft, "material", "materials")
    loads_present = _count(cae, "loads", "loads_count") > 0 or _draft_has(draft, "loads", "load_cases", "load")
    constraints_present = (
        _count(cae, "boundary_conditions", "boundary_conditions_count", "constraints_count") > 0
        or _draft_has(draft, "boundary_conditions", "constraints", "supports", "fixtures")
    )

    analysis_value = cae.get("analysis_type") or draft.get("analysis_type")
    mesh_value = cae.get("mesh") if not isinstance(cae.get("mesh"), bool) else None
    mesh_value = mesh_value or cae.get("mesh_params") or draft.get("mesh")
    solver_status = cae.get("solver_status")
    solver_value = cae.get("solver") or draft.get("solver")

    # A setup "exists" if any of the real inputs / draft / solver are populated.
    has_setup = bool(
        cae.get("present")
        or material_present
        or loads_present
        or constraints_present
        or draft
        or analysis_value
        or mesh_value
        or solver_value
    )
    setup_source = "cae_setup" if has_setup else "not_found"

    def required_status(present: bool) -> str:
        return STATUS_PRESENT if present else STATUS_MISSING

    def defaultable_status(present_value: Any, unavailable_signal: Any, default: str) -> tuple[str, str]:
        if present_value:
            return STATUS_PRESENT, str(present_value if not isinstance(present_value, (dict, list)) else "set")
        if _explicitly_unavailable(unavailable_signal):
            return STATUS_UNKNOWN, "explicitly unavailable"
        return STATUS_DEFAULTABLE, f"will default to {default}"

    analysis_status, analysis_detail = defaultable_status(analysis_value, cae.get("analysis_type"), _DEFAULT_ANALYSIS_TYPE)
    mesh_status, mesh_detail = defaultable_status(mesh_value, cae.get("mesh"), "auto mesh")
    solver_status_value, solver_detail = defaultable_status(
        solver_value or (solver_status if isinstance(solver_status, dict) and solver_status.get("solver") else None),
        solver_status,
        _DEFAULT_SOLVER,
    )

    inputs: dict[str, dict[str, Any]] = {
        "analysis_type": {
            "status": analysis_status,
            "required": False,
            "detail": analysis_detail if analysis_status != STATUS_PRESENT else str(analysis_value),
        },
        "material": {
            "status": required_status(material_present),
            "required": True,
            "detail": "material assigned" if material_present else "no material assigned",
        },
        "loads": {
            "status": required_status(loads_present),
            "required": True,
            "detail": "load(s) defined" if loads_present else "no loads defined",
        },
        "constraints": {
            "status": required_status(constraints_present),
            "required": True,
            "detail": "constraint(s)/support(s) defined" if constraints_present else "no constraints/supports defined",
        },
        "mesh": {"status": mesh_status, "required": False, "detail": mesh_detail},
        "solver": {"status": solver_status_value, "required": False, "detail": solver_detail},
    }

    missing_required_inputs = [name for name in REQUIRED_INPUTS if inputs[name]["status"] == STATUS_MISSING]
    defaultable_inputs = [name for name in CORE_INPUTS if inputs[name]["status"] == STATUS_DEFAULTABLE]

    report: dict[str, Any] = {
        "setup_source": setup_source,
        "solver_executed": False,  # invariant for /simulate v1.5
        "ready_for_solver": not missing_required_inputs,
        "inputs": inputs,
        "missing_required_inputs": missing_required_inputs,
        "defaultable_inputs": defaultable_inputs,
        "targets": bindings_to_targets(mention_bindings),
    }
    report["summary"] = summarize_simulation_readiness(report)
    return report


def summarize_simulation_readiness(report: dict[str, Any]) -> str:
    """Human-readable readiness section injected into the /simulate prompt."""
    inputs = _as_dict(report.get("inputs"))
    parts = ", ".join(f"{name}={inputs.get(name, {}).get('status', STATUS_UNKNOWN)}" for name in CORE_INPUTS)
    missing = report.get("missing_required_inputs") or []
    lines = [
        "Simulation readiness (deterministic, no solver run): "
        f"setup_source={report.get('setup_source')}; {parts}.",
    ]

    targets = _as_dict(report.get("targets"))
    target_bits: list[str] = []
    for kind in ("parts", "artifacts"):
        for entry in targets.get(kind, []) or []:
            value = entry.get("value")
            mark = mention_status_word(entry.get("known"))
            target_bits.append(f"{kind[:-1]}:{value} ({mark})")
    if target_bits:
        lines.append("Referenced targets: " + ", ".join(target_bits) + ".")

    if missing:
        lines.append(
            "Missing REQUIRED inputs: " + ", ".join(missing) + ". "
            "Ask the user to provide these before proposing to run the solver, and "
            "do NOT claim the simulation has run."
        )
    else:
        lines.append(
            "All required inputs (material, loads, constraints) are present. "
            "Produce the simulation plan; defaultable inputs may use defaults. "
            "The solver has NOT been run — running it needs a separate, approved "
            "cae.run_solver step."
        )
    return " ".join(lines)
