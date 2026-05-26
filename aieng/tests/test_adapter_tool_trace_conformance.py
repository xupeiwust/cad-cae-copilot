"""Conformance tests for tool trace metadata across all adapters.

This test suite verifies that:
1. All adapters that record tool trace do so with valid structure
2. Tool trace entries contain required fields with valid values
3. Artifacts referenced in tool trace actually exist in package
4. Tool roles match the expected role for each adapter type
"""
import json
import zipfile

import pytest

from aieng.cli import main
from aieng.package import create_package
from aieng.results.evidence_writer import (
    record_evidence_package,
    write_evidence_scaffold_package,
)
from aieng.provenance.tool_trace_writer import record_trace_package
from aieng.validate import Level, validate_package


class TestToolTraceSchemaCompliance:
    """Verify tool trace entries follow schema and contain required fields."""

    def test_tool_trace_entry_has_required_fields(self, tmp_path):
        """A valid tool trace entry must have all required fields."""
        package_path = tmp_path / "test_compliance.aieng"
        create_package("test_compliance", package_path)
        
        # Record a trace entry
        record_trace_package(
            package_path,
            tool_id="test_solver_v1.0",
            tool_role="solver",
            step_name="static_structural_solve",
            exit_status="success",
            tool_version="1.0",
            inputs=["geometry/normalized.step", "simulation/setup.yaml"],
            outputs=["results/solver_output.dat"],
            artifacts_recorded=["evid_solver_001"],
            claims_advanced=["claim_displacement_max"],
            notes=["Test execution"],
        )
        
        # Read and verify
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
        
        assert trace_data["format_version"] == "0.1.0"
        assert trace_data["tool_trace_id"]
        assert trace_data["entries"]
        assert trace_data["claim_policy"]
        
        entry = trace_data["entries"][0]
        assert entry["entry_id"]
        assert entry["timestamp_utc"]
        assert entry["tool"]
        assert entry["step"]
        assert isinstance(entry["artifacts_recorded"], list)
        assert isinstance(entry["claims_advanced"], list)
        assert isinstance(entry["notes"], list)

    def test_tool_trace_entry_tool_ref_valid(self, tmp_path):
        """Tool reference must have valid tool_id and tool_role."""
        package_path = tmp_path / "test_toolref.aieng"
        create_package("test_toolref", package_path)
        
        record_trace_package(
            package_path,
            tool_id="ansys_19.2",
            tool_role="cae_preprocessor",
            step_name="mesh_generation",
            exit_status="success",
            tool_version="19.2",
        )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
        
        tool_ref = trace_data["entries"][0]["tool"]
        assert tool_ref["tool_id"] == "ansys_19.2"
        assert tool_ref["tool_role"] == "cae_preprocessor"
        assert tool_ref["version"] == "19.2"

    def test_tool_trace_entry_step_record_valid(self, tmp_path):
        """Step record must have name, inputs, outputs, and valid exit_status."""
        package_path = tmp_path / "test_step.aieng"
        create_package("test_step", package_path)
        
        record_trace_package(
            package_path,
            tool_id="gmsh_4.1",
            tool_role="cae_preprocessor",
            step_name="mesh_generation",
            exit_status="success",
            inputs=["geometry/source.step"],
            outputs=["mesh.msh"],
        )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
        
        step = trace_data["entries"][0]["step"]
        assert step["name"] == "mesh_generation"
        assert isinstance(step["inputs"], list)
        assert isinstance(step["outputs"], list)
        assert step["exit_status"] in {"success", "failure", "skipped"}

    def test_tool_trace_entry_exit_status_restricted(self, tmp_path):
        """Exit status must be one of allowed values."""
        package_path = tmp_path / "test_exit_status.aieng"
        create_package("test_exit_status", package_path)
        
        for status in ["success", "failure", "skipped"]:
            record_trace_package(
                package_path,
                tool_id=f"tool_{status}",
                tool_role="solver",
                step_name="step",
                exit_status=status,
            )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
        
        statuses = {e["step"]["exit_status"] for e in trace_data["entries"]}
        assert statuses == {"success", "failure", "skipped"}

    def test_tool_trace_claim_policy_is_const(self, tmp_path):
        """Claim policy must have const values."""
        package_path = tmp_path / "test_claim_policy.aieng"
        create_package("test_claim_policy", package_path)
        
        record_trace_package(
            package_path,
            tool_id="test",
            tool_role="solver",
            step_name="solve",
            exit_status="success",
        )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
        
        policy = trace_data["claim_policy"]
        assert policy["external_tools_execute"] is True
        assert policy["aieng_core_executes_external_tools"] is False


class TestToolTraceArtifactTracking:
    """Verify artifacts referenced in tool trace are tracked correctly."""

    def test_artifacts_recorded_field_is_list(self, tmp_path):
        """Artifacts field should be a list in tool trace."""
        package_path = tmp_path / "test_artifact_tracking.aieng"
        create_package("test_artifact_tracking", package_path)
        
        # Record a trace entry with artifacts
        record_trace_package(
            package_path,
            tool_id="tool_runner",
            tool_role="agent_runtime",
            step_name="import_and_verify",
            exit_status="success",
            artifacts_recorded=["evid_001", "evid_002"],
        )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
            entry = trace_data["entries"][0]
            # Should be able to list the artifacts
            assert isinstance(entry["artifacts_recorded"], list)
            assert "evid_001" in entry["artifacts_recorded"]


class TestToolTraceCrossResourceConformance:
    """Verify trace references align with evidence and claim ledgers."""

    def test_known_artifact_references_pass_validation(self, tmp_path):
        package_path = tmp_path / "test_trace_ref_pass.aieng"
        create_package("test_trace_ref_pass", package_path)
        write_evidence_scaffold_package(package_path)

        record_evidence_package(
            package_path,
            evidence_id="ev_solver_result_001",
            evidence_type="solver_result",
            producer_kind="external_solver",
            producer_tool="calculix",
            artifact_kind="result_file",
            artifact_path="results/solver_result.dat",
            claim_support=["claim_solver_result_001"],
        )

        record_trace_package(
            package_path,
            tool_id="calculix",
            tool_role="solver",
            step_name="static_structural_solve",
            exit_status="success",
            artifacts_recorded=["ev_solver_result_001"],
            claims_advanced=[],
        )

        report = validate_package(package_path)
        fails = [m for m in report.messages if m.level is Level.FAIL and "tool_trace" in m.text]
        assert not fails

    def test_unknown_artifact_reference_fails_validation(self, tmp_path):
        package_path = tmp_path / "test_trace_unknown_artifact.aieng"
        create_package("test_trace_unknown_artifact", package_path)
        write_evidence_scaffold_package(package_path)

        record_trace_package(
            package_path,
            tool_id="gmsh",
            tool_role="cae_preprocessor",
            step_name="mesh_generation",
            exit_status="success",
            artifacts_recorded=["ev_not_present_001"],
        )

        report = validate_package(package_path)
        assert any(
            m.level is Level.FAIL and "artifacts_recorded references unknown evidence ID" in m.text
            for m in report.messages
        )

    def test_claims_advanced_skipped_without_claim_map(self, tmp_path):
        """Without claim_map.json, claims_advanced references are not validated."""
        package_path = tmp_path / "test_trace_unknown_claim.aieng"
        create_package("test_trace_unknown_claim", package_path)
        write_evidence_scaffold_package(package_path)

        record_trace_package(
            package_path,
            tool_id="post_check",
            tool_role="postprocessor",
            step_name="post_validation",
            exit_status="success",
            claims_advanced=["claim_not_present_001"],
        )

        report = validate_package(package_path)
        # No claim_map means claims_advanced cross-reference is skipped
        assert not any(
            m.level is Level.FAIL and "claims_advanced references unknown claim ID" in m.text
            for m in report.messages
        )


class TestToolTraceCliConformance:
    """Verify record-trace CLI path emits schema-compatible entries."""

    def test_record_trace_cli_writes_entry_with_adapter_fields(self, tmp_path):
        package_path = tmp_path / "test_trace_cli.aieng"
        create_package("test_trace_cli", package_path)

        rc = main(
            [
                "record-trace",
                str(package_path),
                "--tool-id",
                "freecad",
                "--tool-role",
                "cad_runtime",
                "--step-name",
                "geometry_writeback",
                "--exit-status",
                "success",
                "--input",
                "geometry/source.step",
                "--output",
                "geometry/modified_patch_0001.step",
            ]
        )
        assert rc == 0

        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))

        assert len(trace_data["entries"]) == 1
        entry = trace_data["entries"][0]
        assert entry["tool"]["tool_id"] == "freecad"
        assert entry["tool"]["tool_role"] == "cad_runtime"
        assert entry["step"]["name"] == "geometry_writeback"
        assert entry["step"]["exit_status"] == "success"


class TestToolRoleConstraints:
    """Verify tool roles are correctly constrained."""

    @pytest.mark.parametrize(
        "valid_role",
        [
            "agent_runtime",
            "cad_runtime",
            "cae_runtime",
            "cae_preprocessor",
            "solver",
            "postprocessor",
            "manufacturing_checker",
        ],
    )
    def test_valid_tool_roles_accepted(self, tmp_path, valid_role):
        """All valid tool roles should be accepted."""
        package_path = tmp_path / "test_valid_roles.aieng"
        create_package("test_valid_roles", package_path)
        
        record_trace_package(
            package_path,
            tool_id=f"tool_{valid_role}",
            tool_role=valid_role,
            step_name="test_step",
            exit_status="success",
        )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
            assert trace_data["entries"][0]["tool"]["tool_role"] == valid_role

    def test_invalid_tool_role_rejected(self, tmp_path):
        """Invalid tool roles should be rejected."""
        package_path = tmp_path / "test_invalid_role.aieng"
        create_package("test_invalid_role", package_path)
        
        with pytest.raises(ValueError, match="tool_role must be one of"):
            record_trace_package(
                package_path,
                tool_id="bad_tool",
                tool_role="invalid_role",
                step_name="test",
                exit_status="success",
            )


class TestToolTraceCardinality:
    """Verify tool trace cardinality and uniqueness constraints."""

    def test_multiple_entries_appended_to_same_trace(self, tmp_path):
        """Multiple tool trace entries should append, not replace."""
        package_path = tmp_path / "test_cardinality.aieng"
        create_package("test_cardinality", package_path)
        
        for i in range(3):
            record_trace_package(
                package_path,
                tool_id=f"tool_{i}",
                tool_role="solver",
                step_name=f"step_{i}",
                exit_status="success",
            )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
            assert len(trace_data["entries"]) == 3

    def test_entry_ids_must_be_unique(self, tmp_path):
        """Each entry must have a unique entry_id."""
        package_path = tmp_path / "test_entry_id_unique.aieng"
        create_package("test_entry_id_unique", package_path)
        
        for i in range(3):
            record_trace_package(
                package_path,
                tool_id=f"tool_{i}",
                tool_role="solver",
                step_name=f"step_{i}",
                exit_status="success",
            )
        
        with zipfile.ZipFile(package_path, mode="r") as zf:
            trace_data = json.loads(zf.read("provenance/tool_trace.json"))
            entry_ids = [e["entry_id"] for e in trace_data["entries"]]
            assert len(entry_ids) == len(set(entry_ids))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
