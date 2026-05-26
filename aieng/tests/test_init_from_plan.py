from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aieng.orchestration.init_from_plan import init_from_plan
from aieng.modeling_plan.planner import RuleBasedModelingPlanner


def _make_valid_plan() -> dict:
    planner = RuleBasedModelingPlanner()
    return planner.plan("create a 120x80x10 plate with 4 holes")


def _write_plan(path: Path, plan: dict) -> None:
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


def _read_json_from_package(package_path: Path, member: str) -> dict:
    with zipfile.ZipFile(package_path, "r") as zf:
        return json.loads(zf.read(member))


def _read_text_from_package(package_path: Path, member: str) -> str:
    with zipfile.ZipFile(package_path, "r") as zf:
        return zf.read(member).decode("utf-8")


class TestInitFromPlanSuccess:
    def test_success_package_contains_required_members(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        with zipfile.ZipFile(out_path, "r") as zf:
            names = set(zf.namelist())

        assert "manifest.json" in names
        assert "authoring/modeling_plan.json" in names
        assert "authoring/construction_history.json" in names
        assert "provenance/tool_trace.jsonl" in names
        assert "results/evidence_index.json" in names
        assert "validation/status.yaml" in names

    def test_success_package_contains_geometry_source_and_normalized(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        with zipfile.ZipFile(out_path, "r") as zf:
            source = zf.read("geometry/source.step")
            normalized = zf.read("geometry/normalized.step")

        assert source == normalized
        assert b"ISO-10303-21" in source

    def test_success_package_status_yaml(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        status_text = _read_text_from_package(out_path, "validation/status.yaml")
        assert "modeling_status: success" in status_text
        assert "diagnostic_package: false" in status_text
        assert "geometry_available: true" in status_text

    def test_success_package_evidence_index(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        evidence = _read_json_from_package(out_path, "results/evidence_index.json")
        assert "entries" in evidence
        assert len(evidence["entries"]) >= 1

    def test_success_package_tool_trace_jsonl(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        trace_text = _read_text_from_package(out_path, "provenance/tool_trace.jsonl")
        lines = [line for line in trace_text.strip().split("\n") if line]
        assert len(lines) >= 1
        # Each line must be valid JSON
        for line in lines:
            entry = json.loads(line)
            assert "trace_type" in entry

    def test_modeling_plan_is_preserved_exactly(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        preserved = _read_json_from_package(out_path, "authoring/modeling_plan.json")
        assert preserved["plan_id"] == plan["plan_id"]
        assert preserved["steps"] == plan["steps"]

    def test_construction_history_written(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        history = _read_json_from_package(out_path, "authoring/construction_history.json")
        assert history["backend_id"] == "fake"
        assert "steps" in history
        assert len(history["steps"]) >= 1
        for step in history["steps"]:
            assert "backend_metadata" in step

    def test_manifest_has_resources(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        manifest = _read_json_from_package(out_path, "manifest.json")
        assert "resources" in manifest
        resources = manifest["resources"]
        assert "authoring" in resources
        assert "provenance" in resources
        assert "results" in resources
        assert "validation" in resources
        assert "geometry" in resources


class TestInitFromPlanFailures:
    def test_validation_failure_does_not_create_package(self, tmp_path: Path) -> None:
        plan = {"plan_id": "bad", "plan_schema_version": "0.1.0"}  # missing intent, units, steps
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        with pytest.raises(ValueError):
            init_from_plan(plan_path, out_path)

        assert not out_path.exists()

    def test_capability_failure_does_not_create_package(self, tmp_path: Path) -> None:
        from unittest.mock import patch
        from aieng.backends.fake_backend import FakeBackend

        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        class RejectAllBackend(FakeBackend):
            def validate_capabilities(self, plan):
                return ["Rejected by test stub"]

        with patch("aieng.orchestration.init_from_plan.discover_backend", return_value=RejectAllBackend):
            with pytest.raises(RuntimeError):
                init_from_plan(plan_path, out_path)

        assert not out_path.exists()

    def test_overwrite_false_refuses_existing_output(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"
        out_path.write_text("existing", encoding="utf-8")

        with pytest.raises(FileExistsError):
            init_from_plan(plan_path, out_path, overwrite=False)

    def test_overwrite_true_replaces_existing_output(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"
        out_path.write_text("existing", encoding="utf-8")

        init_from_plan(plan_path, out_path, overwrite=True)

        with zipfile.ZipFile(out_path, "r") as zf:
            assert "manifest.json" in zf.namelist()


class TestInitFromPlanDiagnostic:
    def test_partial_execution_creates_diagnostic_package(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(
            plan_path,
            out_path,
            backend_options={"fail_at_step_id": plan["steps"][1]["step_id"]},
        )

        status_text = _read_text_from_package(out_path, "validation/status.yaml")
        assert "modeling_status: partial" in status_text
        assert "diagnostic_package: true" in status_text

        evidence = _read_json_from_package(out_path, "results/evidence_index.json")
        failed_evidence = [e for e in evidence["entries"] if e["evidence_type"] == "validation_report"]
        assert len(failed_evidence) >= 1

    def test_failed_execution_creates_diagnostic_package(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(
            plan_path,
            out_path,
            backend_options={"fail_at_step_id": plan["steps"][0]["step_id"]},
        )

        status_text = _read_text_from_package(out_path, "validation/status.yaml")
        assert "modeling_status: failed" in status_text
        assert "diagnostic_package: true" in status_text

        # Evidence, trace, construction_history should still exist
        evidence = _read_json_from_package(out_path, "results/evidence_index.json")
        assert len(evidence["entries"]) >= 1
        trace_text = _read_text_from_package(out_path, "provenance/tool_trace.jsonl")
        assert trace_text.strip()
        history = _read_json_from_package(out_path, "authoring/construction_history.json")
        assert "steps" in history

    def test_diagnostic_package_no_geometry(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(
            plan_path,
            out_path,
            backend_options={"fail_at_step_id": plan["steps"][0]["step_id"]},
        )

        with zipfile.ZipFile(out_path, "r") as zf:
            names = set(zf.namelist())
        assert "geometry/source.step" not in names

    def test_backend_options_are_passed_to_backend(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        # fail_export should not prevent package creation
        init_from_plan(
            plan_path,
            out_path,
            backend_options={"fail_export": True},
        )

        status_text = _read_text_from_package(out_path, "validation/status.yaml")
        assert "modeling_status: partial" in status_text


class TestFallbackEvidence:
    def test_fallback_evidence_when_backend_returns_empty_entries(self, tmp_path: Path) -> None:
        """If a backend returns no evidence, orchestrator must add fallback."""
        from dataclasses import replace
        from unittest.mock import patch
        from aieng.backends.fake_backend import FakeBackend

        class NoEvidenceBackend(FakeBackend):
            def execute_plan(self, plan, output_dir):
                result = super().execute_plan(plan, output_dir)
                return replace(result, evidence_entries=[])

        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        with patch("aieng.orchestration.init_from_plan.discover_backend", return_value=NoEvidenceBackend):
            init_from_plan(plan_path, out_path, backend_id="no_evidence")

        evidence = _read_json_from_package(out_path, "results/evidence_index.json")
        assert len(evidence["entries"]) >= 1
        assert any("Backend did not provide evidence" in str(e) for e in evidence["entries"])
