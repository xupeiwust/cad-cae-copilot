from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

import jsonschema
from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class PlanValidationMessage:
    level: str  # PASS | WARN | FAIL
    text: str
    step_id: str | None = None

    def render(self) -> str:
        prefix = f"[{self.step_id}] " if self.step_id else ""
        return f"{self.level} {prefix}{self.text}"


@dataclass(frozen=True)
class PlanValidationReport:
    messages: tuple[PlanValidationMessage, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not any(m.level == "FAIL" for m in self.messages)

    @property
    def has_warnings(self) -> bool:
        return any(m.level == "WARN" for m in self.messages)

    def render(self) -> str:
        return "\n".join(m.render() for m in self.messages)


_ALLOWED_OPERATIONS_PHASE1 = frozenset({"create_box", "create_cylindrical_cut"})

# Parameter keys required by each operation (logical guard beyond schema)
_REQUIRED_PARAMETERS: dict[str, set[str]] = {
    "create_box": {"length", "width", "height"},
    "create_cylindrical_cut": {"radius", "depth", "position"},
}


def _default_schema_path() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / "modeling_plan.schema.json"


def validate_modeling_plan(
    plan: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> PlanValidationReport:
    """Validate a modeling_plan dict against Phase 1 rules.

    Checks performed:
      1. Schema compliance (JSON Schema Draft 2020-12).
      2. Duplicate step_id values.
      3. Duplicate "creates" identifiers.
      4. Unresolved "target" references (must point to a prior step_id).
      5. Operation whitelist enforcement (no family operations).
      6. Required parameter keys present for each operation.
      7. Assumption refs validity (warn if missing).

    This module does NOT import from aieng.validate to avoid circular dependencies.
    """
    messages: list[PlanValidationMessage] = []

    # 1. Schema validation
    if schema_path is None:
        schema_path = _default_schema_path()

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(plan)
        messages.append(PlanValidationMessage("PASS", "Schema validation passed"))
    except jsonschema.ValidationError as exc:
        messages.append(
            PlanValidationMessage(
                "FAIL",
                f"Schema validation failed: {exc.message}",
                "/".join(str(p) for p in exc.absolute_path) if exc.absolute_path else None,
            )
        )
    except Exception as exc:
        messages.append(PlanValidationMessage("FAIL", f"Schema loading failed: {exc}"))

    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        messages.append(PlanValidationMessage("FAIL", "'steps' must be an array"))
        return PlanValidationReport(tuple(messages))

    step_ids: set[str] = set()
    creates: set[str] = set()
    assumption_ids = {
        a.get("id")
        for a in plan.get("assumptions", [])
        if isinstance(a, dict) and isinstance(a.get("id"), str)
    }

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            messages.append(PlanValidationMessage("FAIL", f"Step at index {idx} is not an object"))
            continue

        step_id = step.get("step_id", f"step_{idx:03d}")

        # 2. Step ID uniqueness
        if step_id in step_ids:
            messages.append(PlanValidationMessage("FAIL", f"Duplicate step_id: {step_id}", step_id))
        else:
            step_ids.add(step_id)

        operation = step.get("operation")

        # 5. Operation whitelist
        if operation not in _ALLOWED_OPERATIONS_PHASE1:
            messages.append(
                PlanValidationMessage(
                    "FAIL",
                    f"Operation '{operation}' is not allowed in Phase 1. Allowed: {_ALLOWED_OPERATIONS_PHASE1}",
                    step_id,
                )
            )

        # 6. Required parameters existence (logical guard)
        params = step.get("parameters")
        if not isinstance(params, dict):
            messages.append(PlanValidationMessage("FAIL", "Missing or invalid 'parameters'", step_id))
        elif operation in _REQUIRED_PARAMETERS:
            missing = _REQUIRED_PARAMETERS[operation] - set(params.keys())
            if missing:
                messages.append(
                    PlanValidationMessage(
                        "FAIL",
                        f"Missing required parameters for {operation}: {sorted(missing)}",
                        step_id,
                    )
                )

        # 3. Creates uniqueness
        created = step.get("creates")
        if isinstance(created, str) and created:
            if created in creates:
                messages.append(
                    PlanValidationMessage("FAIL", f"Duplicate creates identifier: {created}", step_id)
                )
            else:
                creates.add(created)

        # 4. Target resolution (only for cut operations)
        if operation == "create_cylindrical_cut":
            target = step.get("target")
            if not target:
                messages.append(
                    PlanValidationMessage("FAIL", "Missing 'target' for cylindrical_cut", step_id)
                )
            elif target not in step_ids:
                messages.append(
                    PlanValidationMessage(
                        "FAIL",
                        f"Target '{target}' does not resolve to a prior step",
                        step_id,
                    )
                )

        # 7. Assumption refs validity
        for ref in step.get("assumption_refs", []):
            if ref not in assumption_ids:
                messages.append(
                    PlanValidationMessage(
                        "WARN",
                        f"Assumption ref '{ref}' not found in plan.assumptions",
                        step_id,
                    )
                )

    return PlanValidationReport(tuple(messages))


def validate_modeling_plan_file(
    plan_path: str | Path,
    *,
    schema_path: Path | None = None,
) -> PlanValidationReport:
    """Load a modeling plan from disk and validate it."""
    path = Path(plan_path)
    with open(path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    return validate_modeling_plan(plan, schema_path=schema_path)
