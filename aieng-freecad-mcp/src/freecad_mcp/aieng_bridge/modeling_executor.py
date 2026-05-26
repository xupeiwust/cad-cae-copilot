from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from aieng.backend_adapter import BackendExecutionResult, StepExecutionResult
except ImportError:
    @dataclass(frozen=True)
    class StepExecutionResult:
        """Local fallback when aieng is not installed in standalone CI."""

        step_id: str
        operation: str
        status: str
        inputs: dict[str, Any]
        outputs: dict[str, Any]
        artifacts_written: list[str]
        evidence: dict[str, Any]
        trace: dict[str, Any]
        warnings: list[str] = field(default_factory=list)
        errors: list[str] = field(default_factory=list)
        backend_metadata: dict[str, str] = field(default_factory=dict)

    @dataclass(frozen=True)
    class BackendExecutionResult:
        """Local fallback when aieng is not installed in standalone CI."""

        overall_status: str
        plan_id: str
        backend_id: str
        transport_type: str
        kernel: str | None = None
        steps: list[StepExecutionResult] = field(default_factory=list)
        artifacts: list[str] = field(default_factory=list)
        exported_step_path: str | None = None
        construction_history: dict[str, Any] = field(default_factory=dict)
        evidence_entries: list[dict[str, Any]] = field(default_factory=list)
        trace_entries: list[dict[str, Any]] = field(default_factory=list)
        warnings: list[str] = field(default_factory=list)
        errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# FreeCAD script template
# ------------------------------------------------------------------

_FREECAD_SCRIPT_TEMPLATE = '''\
import json
import os
import sys

plan_path = os.environ["FC_OP_INPUT"]
step_out = os.environ["FC_STEP_OUTPUT"]
result_path = os.environ["FC_RESULT_PATH"]

with open(plan_path, "r", encoding="utf-8") as f:
    plan = json.load(f)

import FreeCAD
import Part

doc = FreeCAD.newDocument("AiengPlan")
created_bodies = {}     # step_id -> FreeCAD object Name
current_body_name = None
step_results = []

for step in plan.get("steps", []):
    step_id = step["step_id"]
    op = step["operation"]
    params = step.get("parameters", {})

    result = {
        "step_id": step_id,
        "operation": op,
        "status": "success",
        "inputs": params,
        "outputs": {},
    }

    try:
        if op == "create_box":
            name = params.get("name", "Box")
            box = doc.addObject("Part::Box", name)
            box.Length = float(params["length"])
            box.Width = float(params["width"])
            box.Height = float(params["height"])

            origin = params.get("origin", [0.0, 0.0, 0.0])
            origin_mode = params.get("origin_mode", "corner")

            if origin_mode == "center":
                box.Placement.Base = FreeCAD.Vector(
                    float(origin[0]) - box.Length / 2.0,
                    float(origin[1]) - box.Width / 2.0,
                    float(origin[2]) - box.Height / 2.0,
                )
            else:
                box.Placement.Base = FreeCAD.Vector(
                    float(origin[0]), float(origin[1]), float(origin[2])
                )

            doc.recompute()
            current_body_name = box.Name
            created_bodies[step_id] = box.Name
            result["outputs"]["name"] = box.Name
            result["outputs"]["bbox"] = {
                "xmin": box.Shape.BoundBox.XMin,
                "ymin": box.Shape.BoundBox.YMin,
                "zmin": box.Shape.BoundBox.ZMin,
                "xmax": box.Shape.BoundBox.XMax,
                "ymax": box.Shape.BoundBox.YMax,
                "zmax": box.Shape.BoundBox.ZMax,
            }

        elif op == "create_cylindrical_cut":
            target_step = step.get("target")
            target_name = created_bodies.get(target_step)
            if not target_name:
                raise ValueError(f"Target step '{target_step}' not found")

            tool_name = params.get("name", "Cut") + "_tool"
            cyl = doc.addObject("Part::Cylinder", tool_name)
            cyl.Radius = float(params["radius"])
            cyl.Height = float(params["depth"])

            position = params.get("position", [0.0, 0.0, 0.0])
            cyl.Placement.Base = FreeCAD.Vector(
                float(position[0]), float(position[1]), float(position[2])
            )

            axis = params.get("axis", [0, 0, 1])
            axis_vec = FreeCAD.Vector(float(axis[0]), float(axis[1]), float(axis[2]))
            if axis_vec.Length < 1e-12:
                raise ValueError("Zero-length axis vector")
            axis_vec.normalize()

            z_axis = FreeCAD.Vector(0, 0, 1)
            if abs(z_axis.dot(axis_vec) - 1.0) > 1e-9:
                rotation = FreeCAD.Rotation(z_axis, axis_vec)
                cyl.Placement.Rotation = rotation

            doc.recompute()

            cut = doc.addObject("Part::Cut", params.get("name", "Cut"))
            cut.Base = doc.getObject(target_name)
            cut.Tool = cyl
            doc.recompute()

            current_body_name = cut.Name
            created_bodies[step_id] = cut.Name
            result["outputs"]["name"] = cut.Name
            result["outputs"]["bbox"] = {
                "xmin": cut.Shape.BoundBox.XMin,
                "ymin": cut.Shape.BoundBox.YMin,
                "zmin": cut.Shape.BoundBox.ZMin,
                "xmax": cut.Shape.BoundBox.XMax,
                "ymax": cut.Shape.BoundBox.YMax,
                "zmax": cut.Shape.BoundBox.ZMax,
            }

        else:
            raise ValueError(f"Unknown operation: {op}")

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {str(exc)}"
        step_results.append(result)
        break

    step_results.append(result)

# Export STEP — only the current body
export_success = False
if current_body_name:
    final_obj = doc.getObject(current_body_name)
    if final_obj and hasattr(final_obj, "Shape"):
        final_obj.Shape.exportStep(step_out)
        export_success = True
        step_results.append({
            "step_id": "export_step",
            "status": "success",
            "outputs": {"file_path": step_out}
        })
    else:
        step_results.append({
            "step_id": "export_step",
            "status": "failed",
            "error": f"Final body '{current_body_name}' has no Shape"
        })
else:
    step_results.append({
        "step_id": "export_step",
        "status": "failed",
        "error": "No geometry produced"
    })

# Compute overall status
modeling_results = [r for r in step_results if not r["step_id"].startswith("export")]
modeling_success = all(r["status"] == "success" for r in modeling_results)
has_any_modeling_success = any(r["status"] == "success" for r in modeling_results)

if modeling_success and export_success:
    overall = "success"
elif has_any_modeling_success:
    overall = "partial"
else:
    overall = "failed"

# Write result JSON
with open(result_path, "w", encoding="utf-8") as f:
    json.dump({
        "overall_status": overall,
        "step_results": step_results,
        "document_name": doc.Name,
        "exported_step": step_out if export_success else None,
    }, f, indent=2)

FreeCAD.closeDocument(doc.Name)
'''


class FreeCADModelingBackend:
    """FreeCAD reference backend adapter.

    Compiles an entire modeling plan into a single bounded Python script
    and executes it via one FreeCADCmd subprocess.  No per-step process
    spawning; document state persists across steps.
    """

    backend_id = "freecad"
    transport_type = "subprocess"
    adapter_version = "0.1.0"
    kernel = "FreeCAD"

    def __init__(
        self,
        freecad_cmd_path: str | None = None,
        timeout_seconds: int = 180,
    ) -> None:
        self._freecad_cmd_path = freecad_cmd_path
        self._timeout = timeout_seconds

    # ------------------------------------------------------------------
    # FreeCAD command resolution
    # ------------------------------------------------------------------

    def _resolve_freecad_cmd(self) -> str | None:
        """Resolve the FreeCADCmd executable path.

        Resolution order:
          1. Constructor argument ``freecad_cmd_path``.
          2. Environment variable ``FREECAD_MCP_FREECAD_PATH``.
          3. Environment variable ``FREECAD_HOME`` (with bin/ subdir).
          4. PATH search for ``FreeCADCmd``, ``freecadcmd``, ``freecad``.
        """
        if self._freecad_cmd_path:
            return self._freecad_cmd_path

        env_path = os.environ.get("FREECAD_MCP_FREECAD_PATH")
        if env_path:
            return env_path

        home_str = os.environ.get("FREECAD_HOME")
        if home_str:
            home = Path(home_str)
            candidates = [
                home / "bin" / "FreeCADCmd.exe",
                home / "bin" / "freecadcmd.exe",
                home / "bin" / "FreeCADCmd",
                home / "bin" / "freecadcmd",
            ]
            for cand in candidates:
                if cand.is_file():
                    return str(cand.resolve())

        # PATH fallback
        for name in ("FreeCADCmd", "freecadcmd", "freecad"):
            found = shutil.which(name)
            if found:
                return found

        return None

    # ------------------------------------------------------------------
    # BackendAdapter protocol methods
    # ------------------------------------------------------------------

    def validate_capabilities(self, plan: dict[str, Any]) -> list[str]:
        allowed = {"create_box", "create_cylindrical_cut"}
        unsupported: list[str] = []
        for step in plan.get("steps", []):
            op = step.get("operation")
            if op not in allowed:
                unsupported.append(f"Unsupported operation: {op}")
        return unsupported

    def dry_run(self, plan: dict[str, Any], output_dir: Path) -> BackendExecutionResult:
        """Validate plan without executing FreeCAD.

        Performs logical checks on parameters and target references.
        """
        steps: list[StepExecutionResult] = []
        trace_entries: list[dict[str, Any]] = []
        evidence_entries: list[dict[str, Any]] = []
        step_ids_seen: set[str] = set()
        has_any_success = False
        errors: list[str] = []

        for raw_step in plan.get("steps", []):
            step_id = raw_step.get("step_id", "unknown")
            op = raw_step.get("operation", "unknown")
            params = raw_step.get("parameters", {})

            status = "success"
            step_errors: list[str] = []
            outputs: dict[str, Any] = {"name": params.get("name", "object")}

            if op not in {"create_box", "create_cylindrical_cut"}:
                status = "unsupported"
                step_errors.append(f"Operation '{op}' is not supported")
            else:
                if op == "create_box":
                    for key in ("length", "width", "height"):
                        if key not in params or params[key] <= 0:
                            status = "failed"
                            step_errors.append(f"create_box requires positive {key}")
                elif op == "create_cylindrical_cut":
                    target = raw_step.get("target")
                    if not target or target not in step_ids_seen:
                        status = "failed"
                        step_errors.append(f"Target '{target}' does not resolve to a prior step")
                    for key in ("radius", "depth"):
                        if key not in params or params[key] <= 0:
                            status = "failed"
                            step_errors.append(f"create_cylindrical_cut requires positive {key}")
                    axis = params.get("axis", [0, 0, 1])
                    if all(float(v) == 0.0 for v in axis):
                        status = "failed"
                        step_errors.append("Axis vector cannot be zero-length")

            if status == "success":
                has_any_success = True

            step_ids_seen.add(step_id)
            errors.extend(step_errors)

            step_res = StepExecutionResult(
                step_id=step_id,
                operation=op,
                status=status,
                inputs=dict(params),
                outputs=outputs,
                artifacts_written=[],
                evidence={},
                trace={},
                errors=step_errors,
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
                "kernel": self.kernel,
            })

            if status == "success":
                evidence_entries.append(self._evidence_success(step_id, op))
            else:
                evidence_entries.append(self._evidence_failure(step_id, op, step_errors))

        overall = "success" if all(s.status == "success" for s in steps) else "failed" if not has_any_success else "partial"

        return self._build_result(
            plan, steps, trace_entries, evidence_entries, errors, overall, None
        )

    def execute_plan(self, plan: dict[str, Any], output_dir: Path) -> BackendExecutionResult:
        """Compile plan into a single FreeCAD script and execute it.

        Writes a temporary STEP file to ``output_dir`` if execution succeeds.
        """
        cmd_path = self._resolve_freecad_cmd()
        if cmd_path is None:
            return BackendExecutionResult(
                overall_status="failed",
                plan_id=plan.get("plan_id", "unknown"),
                backend_id=self.backend_id,
                transport_type=self.transport_type,
                kernel=self.kernel,
                errors=["FreeCAD command not found. Set FREECAD_MCP_FREECAD_PATH or ensure FreeCADCmd is in PATH."],
            )

        plan_path = output_dir / "plan.json"
        script_path = output_dir / "exec_plan.py"
        step_out = output_dir / "output.step"
        result_path = output_dir / "result.json"

        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        script_path.write_text(_FREECAD_SCRIPT_TEMPLATE, encoding="utf-8")

        env = {
            **os.environ,
            "FC_OP_INPUT": str(plan_path),
            "FC_STEP_OUTPUT": str(step_out),
            "FC_RESULT_PATH": str(result_path),
        }

        try:
            proc = subprocess.run(
                [cmd_path, str(script_path)],
                capture_output=True,
                text=True,
                env=env,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return BackendExecutionResult(
                overall_status="failed",
                plan_id=plan.get("plan_id", "unknown"),
                backend_id=self.backend_id,
                transport_type=self.transport_type,
                kernel=self.kernel,
                errors=[f"FreeCAD command timed out after {self._timeout}s"],
            )
        except FileNotFoundError:
            return BackendExecutionResult(
                overall_status="failed",
                plan_id=plan.get("plan_id", "unknown"),
                backend_id=self.backend_id,
                transport_type=self.transport_type,
                kernel=self.kernel,
                errors=[f"FreeCAD command not executable: {cmd_path}"],
            )
        except Exception as exc:
            return BackendExecutionResult(
                overall_status="failed",
                plan_id=plan.get("plan_id", "unknown"),
                backend_id=self.backend_id,
                transport_type=self.transport_type,
                kernel=self.kernel,
                errors=[f"Subprocess error: {exc}"],
            )

        if proc.returncode != 0:
            error_msg = proc.stderr.strip() or proc.stdout.strip() or f"FreeCAD exited {proc.returncode}"
            return BackendExecutionResult(
                overall_status="failed",
                plan_id=plan.get("plan_id", "unknown"),
                backend_id=self.backend_id,
                transport_type=self.transport_type,
                kernel=self.kernel,
                errors=[error_msg],
                warnings=[proc.stdout.strip()] if proc.stdout.strip() else [],
            )

        if not result_path.exists():
            return BackendExecutionResult(
                overall_status="failed",
                plan_id=plan.get("plan_id", "unknown"),
                backend_id=self.backend_id,
                transport_type=self.transport_type,
                kernel=self.kernel,
                errors=["FreeCAD did not produce result.json"],
                warnings=[proc.stdout.strip()] if proc.stdout.strip() else [],
            )

        with open(result_path, "r", encoding="utf-8") as f:
            raw_result = json.load(f)

        return self._map_result(plan, raw_result, str(step_out) if step_out.exists() else None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _map_result(
        self,
        plan: dict[str, Any],
        raw_result: dict[str, Any],
        exported_step_path: str | None,
    ) -> BackendExecutionResult:
        steps: list[StepExecutionResult] = []
        trace_entries: list[dict[str, Any]] = []
        evidence_entries: list[dict[str, Any]] = []

        for sr in raw_result.get("step_results", []):
            step_id = sr["step_id"]
            if step_id.startswith("export"):
                continue

            status = sr.get("status", "unknown")
            step_res = StepExecutionResult(
                step_id=step_id,
                operation=sr.get("operation", "unknown"),
                status=status,
                inputs=sr.get("inputs", {}),
                outputs=sr.get("outputs", {}),
                artifacts_written=[exported_step_path] if exported_step_path and status == "success" else [],
                evidence={},
                trace={},
                errors=[sr["error"]] if "error" in sr else [],
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
                "operation": sr.get("operation"),
                "status": status,
                "backend_id": self.backend_id,
                "transport_type": self.transport_type,
                "kernel": self.kernel,
            })

            if status == "success":
                evidence_entries.append(self._evidence_success(step_id, sr.get("operation", "unknown")))
            else:
                evidence_entries.append(
                    self._evidence_failure(step_id, sr.get("operation", "unknown"), [sr.get("error", "")])
                )

        overall = raw_result.get("overall_status", "failed")

        return self._build_result(
            plan, steps, trace_entries, evidence_entries, [], overall, exported_step_path
        )

    def _build_result(
        self,
        plan: dict[str, Any],
        steps: list[StepExecutionResult],
        trace_entries: list[dict[str, Any]],
        evidence_entries: list[dict[str, Any]],
        errors: list[str],
        overall_status: str,
        exported_step_path: str | None,
    ) -> BackendExecutionResult:
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
            errors=errors,
        )

    @staticmethod
    def _evidence_success(step_id: str, operation: str) -> dict[str, Any]:
        return {
            "evidence_id": f"ev_freecad_{step_id}",
            "evidence_type": "geometry_modification",
            "producer": {
                "kind": "backend_adapter",
                "tool_id": "freecad",
                "notes": "FreeCADModelingBackend v0.1.0",
            },
            "artifact": {
                "kind": "step",
                "path": "geometry/source.step",
            },
            "claim_support": [],
            "verification": {
                "status": "available",
                "notes": f"Step {step_id} ({operation}) succeeded.",
            },
        }

    @staticmethod
    def _evidence_failure(step_id: str, operation: str, errors: list[str]) -> dict[str, Any]:
        return {
            "evidence_id": f"ev_freecad_{step_id}_failed",
            "evidence_type": "validation_report",
            "producer": {
                "kind": "backend_adapter",
                "tool_id": "freecad",
                "notes": "FreeCADModelingBackend v0.1.0",
            },
            "artifact": {
                "kind": "json",
                "path": "authoring/construction_history.json",
            },
            "claim_support": [],
            "verification": {
                "status": "missing",
                "notes": f"Step {step_id} ({operation}) failed: {'; '.join(errors)}",
            },
        }
