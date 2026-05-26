"""Tests for .aieng zip evidence and trace persistence."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from freecad_mcp.aieng_bridge.persistence import (
    PersistenceError,
    append_evidence_entry,
    append_trace_entry,
    persist_standard_result_to_aieng,
)
from freecad_mcp.tool_contracts import (
    ClaimPolicy,
    EvidenceBlock,
    StandardToolResult,
    TraceBlock,
)


def _build_aieng_zip(
    tmp_path: Path,
    files: dict[str, Any] | None = None,
) -> Path:
    """Create a .aieng zip package from a dict of file paths to JSON-serializable data."""
    zip_path = tmp_path / "test_package.aieng"
    files = files or {}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in files.items():
            if isinstance(content, (dict, list)):
                data = json.dumps(content, indent=2)
            else:
                data = str(content)
            zf.writestr(arcname, data)
    return zip_path


def _read_zip_json(zip_path: Path, arcname: str) -> Any:
    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open(arcname) as f:
            return json.load(f)


class TestAppendEvidenceZip:
    def test_append_evidence_to_empty_zip(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(tmp_path, {})

        evidence_id = append_evidence_entry(
            str(zip_path),
            {"evidence_type": "tool_execution", "status": "success"},
        )

        assert evidence_id == "ev-0000"
        data = _read_zip_json(zip_path, "results/evidence_index.json")
        assert data["entries"][0]["evidence_id"] == "ev-0000"
        assert data["entries"][0]["evidence_type"] == "tool_execution"

    def test_append_evidence_preserves_existing(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "results/evidence_index.json": {
                    "entries": [
                        {"evidence_id": "ev-0000", "evidence_type": "existing"}
                    ]
                },
            },
        )

        evidence_id = append_evidence_entry(
            str(zip_path),
            {"evidence_type": "new_execution", "status": "success"},
        )

        assert evidence_id == "ev-0001"
        data = _read_zip_json(zip_path, "results/evidence_index.json")
        assert len(data["entries"]) == 2
        assert data["entries"][0]["evidence_type"] == "existing"
        assert data["entries"][1]["evidence_type"] == "new_execution"

    def test_append_evidence_claim_map_unchanged(self, tmp_path: Path) -> None:
        original_claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "results/claim_map.json": original_claim_map,
                "results/evidence_index.json": {"entries": []},
            },
        )

        append_evidence_entry(
            str(zip_path),
            {"evidence_type": "tool_execution", "status": "success"},
        )

        claim_map = _read_zip_json(zip_path, "results/claim_map.json")
        assert claim_map == original_claim_map


class TestAppendTraceZip:
    def test_append_trace_to_empty_zip(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(tmp_path, {})

        trace_id = append_trace_entry(
            str(zip_path),
            {"operation": "cad_set_parameter", "status": "success"},
        )

        assert trace_id == "trace-0000"
        data = _read_zip_json(zip_path, "provenance/tool_trace.json")
        assert data["entries"][0]["trace_id"] == "trace-0000"
        assert data["entries"][0]["operation"] == "cad_set_parameter"

    def test_append_trace_preserves_existing(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "provenance/tool_trace.json": {
                    "entries": [
                        {"trace_id": "trace-0000", "operation": "old_op"}
                    ]
                },
            },
        )

        trace_id = append_trace_entry(
            str(zip_path),
            {"operation": "new_op", "status": "success"},
        )

        assert trace_id == "trace-0001"
        data = _read_zip_json(zip_path, "provenance/tool_trace.json")
        assert len(data["entries"]) == 2
        assert data["entries"][0]["operation"] == "old_op"
        assert data["entries"][1]["operation"] == "new_op"

    def test_append_trace_claim_map_unchanged(self, tmp_path: Path) -> None:
        original_claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "results/claim_map.json": original_claim_map,
                "provenance/tool_trace.json": {"entries": []},
            },
        )

        append_trace_entry(
            str(zip_path),
            {"operation": "cad_set_parameter", "status": "success"},
        )

        claim_map = _read_zip_json(zip_path, "results/claim_map.json")
        assert claim_map == original_claim_map


class TestPersistStandardResultZip:
    def test_persist_full_result_to_zip(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "results/evidence_index.json": {"entries": []},
                "provenance/tool_trace.json": {"entries": []},
            },
        )

        result = StandardToolResult(
            status="success",
            operation="cad_set_parameter",
            inputs={"object": "BasePlate", "param": "Thickness", "value": 8.0},
            outputs={"old_value": 10.0, "new_value": 8.0},
            claim_policy=ClaimPolicy(claims_advanced=False),
            evidence=EvidenceBlock(producer_kind="freecad"),
            trace=TraceBlock(),
        )

        meta = persist_standard_result_to_aieng(str(zip_path), result)

        assert meta["evidence_id"] == "ev-0000"
        assert meta["trace_id"] == "trace-0000"
        assert meta["claims_advanced"] is False

        evidence_data = _read_zip_json(zip_path, "results/evidence_index.json")
        assert len(evidence_data["entries"]) == 1
        assert evidence_data["entries"][0]["claims_advanced"] is False

        trace_data = _read_zip_json(zip_path, "provenance/tool_trace.json")
        assert len(trace_data["entries"]) == 1
        assert trace_data["entries"][0]["operation"] == "cad_set_parameter"

    def test_persist_preserves_other_zip_entries(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(
            tmp_path,
            {
                "manifest.json": {"model_id": "test"},
                "graph/feature_graph.json": {"features": {}},
                "results/claim_map.json": {"claims": []},
                "results/evidence_index.json": {"entries": []},
                "provenance/tool_trace.json": {"entries": []},
            },
        )

        result = StandardToolResult(
            status="success",
            operation="test_op",
            claim_policy=ClaimPolicy(),
        )
        persist_standard_result_to_aieng(str(zip_path), result)

        # Verify other files are untouched
        assert _read_zip_json(zip_path, "manifest.json") == {"model_id": "test"}
        assert _read_zip_json(zip_path, "graph/feature_graph.json") == {"features": {}}
        assert _read_zip_json(zip_path, "results/claim_map.json") == {"claims": []}

    def test_persist_claims_advanced_false(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(tmp_path, {})

        result = StandardToolResult(
            status="success",
            operation="test_op",
            claim_policy=ClaimPolicy(claims_advanced=False),
        )
        meta = persist_standard_result_to_aieng(str(zip_path), result)

        assert meta["claims_advanced"] is False
        trace_data = _read_zip_json(zip_path, "provenance/tool_trace.json")
        # Trace entry itself does not carry claims_advanced directly in our builder,
        # but evidence does.
        evidence_data = _read_zip_json(zip_path, "results/evidence_index.json")
        assert evidence_data["entries"][0]["claims_advanced"] is False

    def test_persist_multiple_times_sequential_ids(self, tmp_path: Path) -> None:
        zip_path = _build_aieng_zip(tmp_path, {})

        for i in range(3):
            result = StandardToolResult(
                status="success",
                operation=f"op_{i}",
                claim_policy=ClaimPolicy(),
            )
            meta = persist_standard_result_to_aieng(str(zip_path), result)
            assert meta["evidence_id"] == f"ev-{i:04d}"
            assert meta["trace_id"] == f"trace-{i:04d}"

        evidence_data = _read_zip_json(zip_path, "results/evidence_index.json")
        trace_data = _read_zip_json(zip_path, "provenance/tool_trace.json")
        assert len(evidence_data["entries"]) == 3
        assert len(trace_data["entries"]) == 3


class TestDirectoryBehaviorPreserved:
    def test_append_evidence_to_directory(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "results").mkdir()
        (pkg_dir / "results" / "evidence_index.json").write_text(
            json.dumps({"entries": []})
        )

        evidence_id = append_evidence_entry(
            str(pkg_dir),
            {"evidence_type": "tool_execution", "status": "success"},
        )

        assert evidence_id == "ev-0000"
        data = json.loads((pkg_dir / "results" / "evidence_index.json").read_text())
        assert len(data["entries"]) == 1

    def test_append_trace_to_directory(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "provenance").mkdir()
        (pkg_dir / "provenance" / "tool_trace.json").write_text(
            json.dumps({"entries": []})
        )

        trace_id = append_trace_entry(
            str(pkg_dir),
            {"operation": "cad_set_parameter", "status": "success"},
        )

        assert trace_id == "trace-0000"
        data = json.loads((pkg_dir / "provenance" / "tool_trace.json").read_text())
        assert len(data["entries"]) == 1

    def test_persist_to_directory(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "results").mkdir()
        (pkg_dir / "provenance").mkdir()

        result = StandardToolResult(
            status="success",
            operation="test_op",
            claim_policy=ClaimPolicy(),
        )
        meta = persist_standard_result_to_aieng(str(pkg_dir), result)

        assert meta["evidence_id"] == "ev-0000"
        assert meta["trace_id"] == "trace-0000"
        assert (pkg_dir / "results" / "evidence_index.json").exists()
        assert (pkg_dir / "provenance" / "tool_trace.json").exists()

    def test_invalid_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PersistenceError):
            append_evidence_entry(
                str(tmp_path / "not_a_dir"),
                {"evidence_type": "test"},
            )


class TestSchemaConformance:
    def test_evidence_conforms_to_schema(self, tmp_path: Path) -> None:
        schema_path = Path(__file__).parents[2] / ".." / "aieng" / "schemas" / "evidence_index.schema.json"
        if not schema_path.exists():
            pytest.skip("aieng schema not available at expected path")

        zip_path = _build_aieng_zip(tmp_path, {})
        result = StandardToolResult(
            status="success",
            operation="test_op",
            claim_policy=ClaimPolicy(),
        )
        persist_standard_result_to_aieng(str(zip_path), result)

        evidence_data = _read_zip_json(zip_path, "results/evidence_index.json")
        schema = json.loads(schema_path.read_text())
        import jsonschema

        jsonschema.validate(instance=evidence_data, schema=schema)

    def test_trace_conforms_to_schema(self, tmp_path: Path) -> None:
        schema_path = Path(__file__).parents[2] / ".." / "aieng" / "schemas" / "tool_trace.schema.json"
        if not schema_path.exists():
            pytest.skip("aieng schema not available at expected path")

        zip_path = _build_aieng_zip(tmp_path, {})
        result = StandardToolResult(
            status="success",
            operation="test_op",
            claim_policy=ClaimPolicy(),
        )
        persist_standard_result_to_aieng(str(zip_path), result)

        trace_data = _read_zip_json(zip_path, "provenance/tool_trace.json")
        schema = json.loads(schema_path.read_text())
        import jsonschema

        jsonschema.validate(instance=trace_data, schema=schema)
