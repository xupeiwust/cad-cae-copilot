"""Tests for the explicit claim update layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
from freecad_mcp.tools_aieng import register_aieng_tools


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestClaimModels:
    def test_claim_decision_criterion_defaults(self) -> None:
        c = ClaimDecisionCriterion(
            metric_name="stress", operator="<=", threshold=200.0
        )
        assert c.unit is None
        assert c.evidence_field is None

    def test_claim_update_request_defaults(self) -> None:
        req = ClaimUpdateRequest(
            package_path="/tmp/pkg",
            claim_id="c1",
            evidence_ids=["ev1"],
        )
        assert req.mode == "evaluate"
        assert req.dry_run is False
        assert req.decision_criteria == []
        assert req.rationale is None
        assert req.requested_status is None

    def test_criterion_result_serialization(self) -> None:
        cr = CriterionResult(
            metric_name="stress",
            operator="<=",
            threshold=200.0,
            actual_value=150.0,
            status="pass",
        )
        dumped = cr.model_dump(mode="json")
        assert dumped["metric_name"] == "stress"
        assert dumped["status"] == "pass"


# ---------------------------------------------------------------------------
# Evidence lookup tests
# ---------------------------------------------------------------------------

class TestEvidenceLookup:
    def test_load_claim_map_missing(self, tmp_path: Path) -> None:
        result = load_claim_map(str(tmp_path))
        assert result == {"claims": []}

    def test_load_claim_map_existing(self, tmp_path: Path) -> None:
        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        result = load_claim_map(str(tmp_path))
        assert result == claim_map

    def test_load_evidence_index_missing(self, tmp_path: Path) -> None:
        result = load_evidence_index(str(tmp_path))
        assert result == {"entries": []}

    def test_load_evidence_index_existing(self, tmp_path: Path) -> None:
        evidence = {"entries": [{"evidence_id": "ev1"}]}
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "evidence_index.json").write_text(json.dumps(evidence))
        result = load_evidence_index(str(tmp_path))
        assert result == evidence

    def test_find_claim_found(self) -> None:
        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        claim = find_claim(claim_map, "c1")
        assert claim is not None
        assert claim["id"] == "c1"

    def test_find_claim_not_found(self) -> None:
        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        claim = find_claim(claim_map, "c2")
        assert claim is None

    def test_find_evidence_by_ids(self) -> None:
        evidence_index = {
            "entries": [
                {"evidence_id": "ev1"},
                {"evidence_id": "ev2"},
                {"evidence_id": "ev3"},
            ]
        }
        found = find_evidence(evidence_index, ["ev1", "ev3"])
        assert len(found) == 2
        ids = {e["evidence_id"] for e in found}
        assert ids == {"ev1", "ev3"}


# ---------------------------------------------------------------------------
# Criteria evaluation tests
# ---------------------------------------------------------------------------

class TestCriteriaEvaluation:
    def test_criteria_pass(self) -> None:
        evidence = [{"metadata": {"metrics": [{"name": "stress", "value": 150.0}]}}]
        criteria = [ClaimDecisionCriterion(metric_name="stress", operator="<=", threshold=200.0)]
        results = evaluate_claim_criteria(evidence, criteria)

        assert len(results) == 1
        assert results[0].status == "pass"
        assert results[0].actual_value == 150.0

    def test_criteria_fail(self) -> None:
        evidence = [{"metadata": {"metrics": [{"name": "stress", "value": 250.0}]}}]
        criteria = [ClaimDecisionCriterion(metric_name="stress", operator="<=", threshold=200.0)]
        results = evaluate_claim_criteria(evidence, criteria)

        assert results[0].status == "fail"

    def test_criteria_not_found(self) -> None:
        evidence = [{"metadata": {"metrics": [{"name": "stress", "value": 150.0}]}}]
        criteria = [ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)]
        results = evaluate_claim_criteria(evidence, criteria)

        assert results[0].status == "not_found"

    def test_criteria_unsupported_type(self) -> None:
        evidence = [{"metadata": {"metrics": [{"name": "stress", "value": "high"}]}}]
        criteria = [ClaimDecisionCriterion(metric_name="stress", operator="<=", threshold=200.0)]
        results = evaluate_claim_criteria(evidence, criteria)

        assert results[0].status == "unsupported"

    def test_multiple_criteria_all_pass(self) -> None:
        evidence = [{
            "metadata": {
                "metrics": [
                    {"name": "stress", "value": 150.0},
                    {"name": "displacement", "value": 1.5},
                ]
            }
        }]
        criteria = [
            ClaimDecisionCriterion(metric_name="stress", operator="<=", threshold=200.0),
            ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0),
        ]
        results = evaluate_claim_criteria(evidence, criteria)

        assert all(r.status == "pass" for r in results)
        from freecad_mcp.aieng_bridge.claims import _determine_status_from_results
        assert _determine_status_from_results(results) == "pass"

    def test_multiple_criteria_one_fail(self) -> None:
        evidence = [{
            "metadata": {
                "metrics": [
                    {"name": "stress", "value": 250.0},
                    {"name": "displacement", "value": 1.5},
                ]
            }
        }]
        criteria = [
            ClaimDecisionCriterion(metric_name="stress", operator="<=", threshold=200.0),
            ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0),
        ]
        results = evaluate_claim_criteria(evidence, criteria)

        from freecad_mcp.aieng_bridge.claims import _determine_status_from_results
        assert _determine_status_from_results(results) == "fail"

    def test_multiple_criteria_one_not_found(self) -> None:
        evidence = [{
            "metadata": {
                "metrics": [
                    {"name": "stress", "value": 150.0},
                ]
            }
        }]
        criteria = [
            ClaimDecisionCriterion(metric_name="stress", operator="<=", threshold=200.0),
            ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0),
        ]
        results = evaluate_claim_criteria(evidence, criteria)

        from freecad_mcp.aieng_bridge.claims import _determine_status_from_results
        assert _determine_status_from_results(results) == "unsupported"

    def test_direct_key_lookup_in_metadata(self) -> None:
        evidence = [{"metadata": {"max_displacement_mm": 1.5}}]
        criteria = [ClaimDecisionCriterion(metric_name="max_displacement_mm", operator="<=", threshold=2.0)]
        results = evaluate_claim_criteria(evidence, criteria)

        assert results[0].status == "pass"
        assert results[0].actual_value == 1.5

    def test_direct_key_lookup_in_outputs(self) -> None:
        evidence = [{"outputs": {"max_stress_mpa": 180.0}}]
        criteria = [ClaimDecisionCriterion(metric_name="max_stress_mpa", operator="<=", threshold=200.0)]
        results = evaluate_claim_criteria(evidence, criteria)

        assert results[0].status == "pass"

    def test_equality_operator(self) -> None:
        evidence = [{"metadata": {"metrics": [{"name": "status", "value": "ok"}]}}]
        criteria = [ClaimDecisionCriterion(metric_name="status", operator="==", threshold="ok")]
        results = evaluate_claim_criteria(evidence, criteria)

        assert results[0].status == "pass"

    def test_not_equal_operator(self) -> None:
        evidence = [{"metadata": {"metrics": [{"name": "status", "value": "failed"}]}}]
        criteria = [ClaimDecisionCriterion(metric_name="status", operator="!=", threshold="ok")]
        results = evaluate_claim_criteria(evidence, criteria)

        assert results[0].status == "pass"


# ---------------------------------------------------------------------------
# Claim update integration tests
# ---------------------------------------------------------------------------

class TestClaimUpdate:
    def _build_package(self, tmp_path: Path) -> Path:
        """Build a minimal .aieng package with claim_map and evidence_index."""
        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "provenance").mkdir()
        claim_map = {
            "claims": [
                {
                    "id": "claim_max_displacement",
                    "status": "unsupported",
                    "description": "Max displacement <= 2.0 mm",
                },
                {
                    "id": "claim_mass",
                    "status": "unsupported",
                    "description": "Mass under 500g",
                },
            ]
        }
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        (tmp_path / "results" / "evidence_index.json").write_text(json.dumps({"entries": []}))
        return tmp_path

    def _add_evidence(self, package_path: Path, evidence: dict[str, Any]) -> None:
        evidence_path = package_path / "results" / "evidence_index.json"
        data = json.loads(evidence_path.read_text())
        data["entries"].append(evidence)
        evidence_path.write_text(json.dumps(data))

    def test_reject_missing_package_path(self) -> None:
        request = ClaimUpdateRequest(
            package_path="/nonexistent/path",
            claim_id="c1",
            evidence_ids=["ev1"],
        )
        summary = update_claim_status(request)
        assert summary.status == "rejected"
        assert summary.primary_error_code == "MISSING_PACKAGE_PATH"
        assert "not a directory" in str(summary.errors)

    def test_reject_unknown_claim_id(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {"evidence_id": "ev1"})

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="unknown_claim",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="x", operator="<=", threshold=1.0)],
        )
        summary = update_claim_status(request)
        assert summary.status == "rejected"
        assert summary.primary_error_code == "CLAIM_NOT_FOUND"
        assert "Claim not found" in str(summary.errors)

    def test_reject_missing_evidence_ids(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=[],
            decision_criteria=[ClaimDecisionCriterion(metric_name="x", operator="<=", threshold=1.0)],
        )
        summary = update_claim_status(request)
        assert summary.status == "rejected"
        assert summary.primary_error_code == "MISSING_EVIDENCE_IDS"
        assert "evidence_ids must not be empty" in str(summary.errors)

    def test_reject_evidence_not_found(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev_missing"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="x", operator="<=", threshold=1.0)],
        )
        summary = update_claim_status(request)
        assert summary.status == "rejected"
        assert summary.primary_error_code == "EVIDENCE_NOT_FOUND"
        assert "Evidence IDs not found" in str(summary.errors)

    def test_reject_evaluate_without_criteria(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {"evidence_id": "ev1"})

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            mode="evaluate",
        )
        summary = update_claim_status(request)
        assert summary.status == "rejected"
        assert summary.primary_error_code == "MISSING_DECISION_CRITERIA"
        assert "requires at least one decision_criterion" in str(summary.errors)

    def test_reject_manual_without_rationale(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {"evidence_id": "ev1"})

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            mode="manual",
            requested_status="pass",
        )
        summary = update_claim_status(request)
        assert summary.status == "rejected"
        assert summary.primary_error_code == "MISSING_MANUAL_FIELDS"
        assert "manual mode requires a rationale" in str(summary.errors)

    def test_reject_unknown_mode(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {"evidence_id": "ev1"})

        # Bypass Pydantic literal validation to test the defensive branch
        request = ClaimUpdateRequest.model_construct(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            mode="invalid_mode",
        )
        summary = update_claim_status(request)
        assert summary.status == "rejected"
        assert summary.primary_error_code == "UNKNOWN_MODE"
        assert "Unknown mode" in str(summary.errors)

    def test_persistence_failure_returns_error_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {"evidence_id": "ev1"})

        from freecad_mcp.aieng_bridge import claims as claims_mod
        from freecad_mcp.aieng_bridge.persistence import PersistenceError

        def failing_write(path: Any, data: Any) -> None:
            raise PersistenceError("disk full")

        monkeypatch.setattr(claims_mod, "_atomic_write_json", failing_write)

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            mode="manual",
            requested_status="pass",
            rationale="Human review confirmed.",
        )
        summary = update_claim_status(request)
        assert summary.status == "failed"
        assert summary.primary_error_code == "PERSISTENCE_FAILED"
        assert "disk full" in str(summary.errors)
        assert summary.claim_map_updated is False

    def test_evaluate_updates_claim_to_pass(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {
            "evidence_id": "ev1",
            "metadata": {"metrics": [{"name": "displacement", "value": 1.5}]},
        })

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)],
            mode="evaluate",
        )
        summary = update_claim_status(request)

        assert summary.status == "success"
        assert summary.old_status == "unsupported"
        assert summary.new_status == "pass"
        assert summary.claim_map_updated is True
        assert summary.trace_id is not None

        claim_map = json.loads((package / "results" / "claim_map.json").read_text())
        target = find_claim(claim_map, "claim_max_displacement")
        assert target is not None
        assert target["status"] == "pass"
        assert target["update_mode"] == "evaluate"
        assert target["evidence_ids"] == ["ev1"]
        assert "last_updated" in target

    def test_evaluate_updates_claim_to_fail(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {
            "evidence_id": "ev1",
            "metadata": {"metrics": [{"name": "displacement", "value": 3.0}]},
        })

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)],
            mode="evaluate",
        )
        summary = update_claim_status(request)

        assert summary.status == "success"
        assert summary.new_status == "fail"

        claim_map = json.loads((package / "results" / "claim_map.json").read_text())
        target = find_claim(claim_map, "claim_max_displacement")
        assert target is not None
        assert target["status"] == "fail"

    def test_evaluate_updates_claim_to_unsupported(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {"evidence_id": "ev1", "metadata": {}})

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)],
            mode="evaluate",
        )
        summary = update_claim_status(request)

        assert summary.status == "success"
        assert summary.new_status == "unsupported"

        claim_map = json.loads((package / "results" / "claim_map.json").read_text())
        target = find_claim(claim_map, "claim_max_displacement")
        assert target is not None
        assert target["status"] == "unsupported"

    def test_manual_mode_updates_claim(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {"evidence_id": "ev1"})

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            mode="manual",
            requested_status="pass",
            rationale="Human review confirmed design is acceptable.",
        )
        summary = update_claim_status(request)

        assert summary.status == "success"
        assert summary.new_status == "pass"
        assert any("manually" in w.lower() for w in summary.warnings)

        claim_map = json.loads((package / "results" / "claim_map.json").read_text())
        target = find_claim(claim_map, "claim_max_displacement")
        assert target is not None
        assert target["status"] == "pass"
        assert target["update_mode"] == "manual"
        assert target["rationale"] == "Human review confirmed design is acceptable."

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {
            "evidence_id": "ev1",
            "metadata": {"metrics": [{"name": "displacement", "value": 1.5}]},
        })
        initial_claim_map = json.loads((package / "results" / "claim_map.json").read_text())

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)],
            mode="evaluate",
            dry_run=True,
        )
        summary = update_claim_status(request)

        assert summary.status == "success"
        assert summary.new_status == "pass"
        assert summary.claim_map_updated is False

        final_claim_map = json.loads((package / "results" / "claim_map.json").read_text())
        assert final_claim_map == initial_claim_map

        trace_path = package / "provenance" / "tool_trace.json"
        assert not trace_path.exists()

    def test_only_target_claim_modified(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {
            "evidence_id": "ev1",
            "metadata": {"metrics": [{"name": "displacement", "value": 1.5}]},
        })
        initial_claim_map = json.loads((package / "results" / "claim_map.json").read_text())

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)],
            mode="evaluate",
        )
        summary = update_claim_status(request)

        assert summary.status == "success"

        final_claim_map = json.loads((package / "results" / "claim_map.json").read_text())
        for claim in final_claim_map["claims"]:
            if claim["id"] == "claim_mass":
                initial = find_claim(initial_claim_map, "claim_mass")
                assert claim["status"] == initial["status"]

    def test_trace_appended_on_success(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {
            "evidence_id": "ev1",
            "metadata": {"metrics": [{"name": "displacement", "value": 1.5}]},
        })

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)],
            mode="evaluate",
        )
        summary = update_claim_status(request)

        assert summary.status == "success"
        assert summary.trace_id is not None

        trace = json.loads((package / "provenance" / "tool_trace.json").read_text())
        assert len(trace["entries"]) >= 1
        last_trace = trace["entries"][-1]
        assert last_trace["operation"] == "aieng_update_claim"
        assert last_trace["claim_id"] == "claim_max_displacement"

    def test_evidence_index_not_modified(self, tmp_path: Path) -> None:
        package = self._build_package(tmp_path)
        self._add_evidence(package, {
            "evidence_id": "ev1",
            "metadata": {"metrics": [{"name": "displacement", "value": 1.5}]},
        })
        initial_evidence = json.loads((package / "results" / "evidence_index.json").read_text())

        request = ClaimUpdateRequest(
            package_path=str(package),
            claim_id="claim_max_displacement",
            evidence_ids=["ev1"],
            decision_criteria=[ClaimDecisionCriterion(metric_name="displacement", operator="<=", threshold=2.0)],
            mode="evaluate",
        )
        summary = update_claim_status(request)

        assert summary.status == "success"

        final_evidence = json.loads((package / "results" / "evidence_index.json").read_text())
        assert final_evidence == initial_evidence


# ---------------------------------------------------------------------------
# MCP tool tests
# ---------------------------------------------------------------------------

class TestClaimUpdateMcpTool:
    def _make_mcp(self) -> Any:
        from mcp.server.fastmcp import FastMCP
        from freecad_mcp.bridge.executor import FreecadExecutor

        class DummyExecutor(FreecadExecutor):
            async def execute_async(self, code: str) -> dict[str, Any]:
                return {"success": True, "result": {}}

            async def get_version_async(self) -> dict[str, Any]:
                return {"version": "0.21.0", "gui_available": False}

        mcp = FastMCP(name="test")
        executor = DummyExecutor()
        register_aieng_tools(mcp, executor)
        return mcp

    @pytest.mark.asyncio
    async def test_mcp_tool_rejects_missing_package_path(self) -> None:
        mcp = self._make_mcp()
        tool = mcp._tool_manager._tools["aieng_update_claim"].fn
        response = await tool(
            package_path="/nonexistent/path",
            claim_id="c1",
            evidence_ids=["ev1"],
            decision_criteria=[{"metric_name": "x", "operator": "<=", "threshold": 1.0}],
        )
        assert response["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_mcp_tool_successful_update(self, tmp_path: Path) -> None:
        mcp = self._make_mcp()

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "provenance").mkdir()
        claim_map = {
            "claims": [{"id": "c1", "status": "unsupported"}]
        }
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        evidence = {
            "entries": [{
                "evidence_id": "ev1",
                "metadata": {"metrics": [{"name": "stress", "value": 150.0}]},
            }]
        }
        (tmp_path / "results" / "evidence_index.json").write_text(json.dumps(evidence))

        tool = mcp._tool_manager._tools["aieng_update_claim"].fn
        response = await tool(
            package_path=str(tmp_path),
            claim_id="c1",
            evidence_ids=["ev1"],
            decision_criteria=[{"metric_name": "stress", "operator": "<=", "threshold": 200.0}],
            mode="evaluate",
        )

        assert response["status"] == "success"
        assert response["new_status"] == "pass"
        assert response["claim_map_updated"] is True
        assert response["trace_id"] is not None

    @pytest.mark.asyncio
    async def test_mcp_tool_dry_run(self, tmp_path: Path) -> None:
        mcp = self._make_mcp()

        (tmp_path / "manifest.json").write_text(json.dumps({"name": "test"}))
        (tmp_path / "results").mkdir()
        (tmp_path / "provenance").mkdir()
        claim_map = {"claims": [{"id": "c1", "status": "unsupported"}]}
        (tmp_path / "results" / "claim_map.json").write_text(json.dumps(claim_map))
        evidence = {"entries": [{"evidence_id": "ev1", "metadata": {"metrics": [{"name": "stress", "value": 150.0}]}}]}
        (tmp_path / "results" / "evidence_index.json").write_text(json.dumps(evidence))

        tool = mcp._tool_manager._tools["aieng_update_claim"].fn
        response = await tool(
            package_path=str(tmp_path),
            claim_id="c1",
            evidence_ids=["ev1"],
            decision_criteria=[{"metric_name": "stress", "operator": "<=", "threshold": 200.0}],
            mode="evaluate",
            dry_run=True,
        )

        assert response["status"] == "success"
        assert response["claim_map_updated"] is False

        after = json.loads((tmp_path / "results" / "claim_map.json").read_text())
        assert after == claim_map


# ---------------------------------------------------------------------------
# Demo script test
# ---------------------------------------------------------------------------

def test_demo_script_runs() -> None:
    """Verify the claim update demo script exits cleanly."""
    import subprocess
    import sys

    script = Path(__file__).resolve().parent.parent / "scripts" / "run_claim_update_demo.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)

    assert result.returncode == 0, f"Demo script failed:\n{result.stderr}"
    assert "Demo completed successfully" in result.stdout
