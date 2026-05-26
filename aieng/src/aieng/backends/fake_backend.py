from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aieng.backend_adapter import BackendAdapter, BackendExecutionResult, StepExecutionResult


class FakeBackend:
    """Reference backend adapter for testing the core pipeline without FreeCAD.

    Writes a placeholder STEP file and returns structured result data.
    No real geometry is created.
    """

    backend_id = "fake"
    transport_type = "in_process"
    adapter_version = "0.1.0"
    kernel = "fake"

    def __init__(
        self,
        *,
        fail_at_step_id: str | None = None,
        fail_export: bool = False,
    ) -> None:
        self._fail_at_step_id = fail_at_step_id
        self._fail_export = fail_export

    def validate_capabilities(self, plan: dict[str, Any]) -> list[str]:
        allowed = {"create_box", "create_cylindrical_cut"}
        unsupported: list[str] = []
        for step in plan.get("steps", []):
            op = step.get("operation")
            if op not in allowed:
                unsupported.append(f"Unsupported operation: {op}")
        return unsupported

    def dry_run(self, plan: dict[str, Any], output_dir: Path) -> BackendExecutionResult:
        return self._run(plan, output_dir, write_artifacts=False)

    def execute_plan(self, plan: dict[str, Any], output_dir: Path) -> BackendExecutionResult:
        return self._run(plan, output_dir, write_artifacts=True)

    def _run(
        self,
        plan: dict[str, Any],
        output_dir: Path,
        *,
        write_artifacts: bool,
    ) -> BackendExecutionResult:
        steps: list[StepExecutionResult] = []
        trace_entries: list[dict[str, Any]] = []
        evidence_entries: list[dict[str, Any]] = []
        step_ids_seen: set[str] = set()
        has_any_success = False

        for raw_step in plan.get("steps", []):
            step_id = raw_step.get("step_id", "unknown")
            op = raw_step.get("operation", "unknown")
            params = raw_step.get("parameters", {})

            status = "success"
            outputs: dict[str, Any] = {"name": params.get("name", "object")}
            errors: list[str] = []

            if op not in {"create_box", "create_cylindrical_cut"}:
                status = "unsupported"
                errors.append(f"Operation '{op}' is not supported by fake backend")
            elif self._fail_at_step_id == step_id:
                status = "failed"
                errors.append(f"Artificial failure triggered at step {step_id}")
            elif step_id in step_ids_seen:
                status = "failed"
                errors.append(f"Duplicate step_id: {step_id}")
            else:
                has_any_success = True
                if op == "create_box":
                    outputs["bbox"] = {
                        "xmin": 0.0, "ymin": 0.0, "zmin": 0.0,
                        "xmax": params.get("length", 0.0),
                        "ymax": params.get("width", 0.0),
                        "zmax": params.get("height", 0.0),
                    }
                elif op == "create_cylindrical_cut":
                    outputs["bbox"] = {
                        "xmin": 0.0, "ymin": 0.0, "zmin": 0.0,
                        "xmax": 1.0, "ymax": 1.0, "zmax": 1.0,
                    }

            step_ids_seen.add(step_id)

            step_res = StepExecutionResult(
                step_id=step_id,
                operation=op,
                status=status,
                inputs=dict(params),
                outputs=outputs,
                artifacts_written=[],
                evidence={},
                trace={},
                errors=errors,
                backend_metadata={
                    "backend_id": self.backend_id,
                    "adapter_version": self.adapter_version,
                    "transport_type": self.transport_type,
                    "kernel": self.kernel,
                },
            )
            steps.append(step_res)

            trace_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trace_type": "modeling_execution",
                "step_id": step_id,
                "operation": op,
                "status": status,
                "backend_id": self.backend_id,
                "transport_type": self.transport_type,
                "outputs": outputs,
            })

            if status == "success":
                evidence_entries.append({
                    "evidence_id": f"ev_geom_op_{step_id}",
                    "evidence_type": "geometry_modification",
                    "producer": {
                        "kind": "backend_adapter",
                        "tool_id": self.backend_id,
                        "version": self.adapter_version,
                    },
                    "artifact": {
                        "kind": "step",
                        "path": "geometry/source.step",
                    },
                    "claim_support": ["claim_geometry_created_001"],
                    "verification": {
                        "status": "available",
                        "notes": f"Step {step_id} ({op}) succeeded on fake backend.",
                    },
                })
            else:
                evidence_entries.append({
                    "evidence_id": f"ev_exec_fail_{step_id}",
                    "evidence_type": "validation_report",
                    "producer": {
                        "kind": "backend_adapter",
                        "tool_id": self.backend_id,
                        "version": self.adapter_version,
                    },
                    "artifact": {
                        "kind": "json",
                        "path": "authoring/construction_history.json",
                    },
                    "claim_support": [],
                    "verification": {
                        "status": "missing",
                        "notes": f"Step {step_id} ({op}) failed: {'; '.join(errors)}",
                    },
                })

            # Simulate a real backend that stops on first failure
            if self._fail_at_step_id == step_id and status == "failed":
                break

        # Export artifact
        exported_step_path: str | None = None
        export_success = False
        if write_artifacts and has_any_success:
            if not self._fail_export:
                step_file = output_dir / "fake_output.step"
                step_file.write_text(
                    "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
                    encoding="utf-8",
                )
                exported_step_path = str(step_file)
                export_success = True
            else:
                export_success = False

        # Determine overall_status
        modeling_success = all(
            s.status == "success" for s in steps
        )
        if write_artifacts:
            if modeling_success and export_success:
                overall_status = "success"
            elif has_any_success:
                overall_status = "partial"
            else:
                overall_status = "failed"
        else:
            # dry_run: export is not expected
            if modeling_success:
                overall_status = "success"
            elif has_any_success:
                overall_status = "partial"
            else:
                overall_status = "failed"

        construction_history = {
            "plan_id": plan.get("plan_id", "unknown"),
            "backend_id": self.backend_id,
            "transport_type": self.transport_type,
            "kernel": self.kernel,
            "steps": [
                {
                    "step_id": s.step_id,
                    "operation": s.operation,
                    "status": s.status,
                    "outputs": s.outputs,
                    "backend_metadata": s.backend_metadata,
                }
                for s in steps
            ],
        }

        return BackendExecutionResult(
            overall_status=overall_status,
            plan_id=plan.get("plan_id", "unknown"),
            backend_id=self.backend_id,
            transport_type=self.transport_type,
            kernel=self.kernel,
            steps=steps,
            artifacts=[exported_step_path] if exported_step_path else [],
            exported_step_path=exported_step_path,
            construction_history=construction_history,
            evidence_entries=evidence_entries,
            trace_entries=trace_entries,
            errors=[e for s in steps for e in s.errors],
        )
