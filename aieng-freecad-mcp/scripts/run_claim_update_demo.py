"""Claim update demo.

Demonstrates explicit evidence-backed claim update using mock evidence.

Usage:
    python scripts/run_claim_update_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from freecad_mcp.aieng_bridge.claims import (
    ClaimDecisionCriterion,
    ClaimUpdateRequest,
    update_claim_status,
)


def _copy_fixture(tmp_dir: Path) -> Path:
    fixture_src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package"
    fixture_dst = tmp_dir / "package"
    shutil.copytree(fixture_src, fixture_dst)
    return fixture_dst


def main() -> int:
    print("=" * 60)
    print(" Explicit Claim Update Demo")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        package_path = _copy_fixture(tmp_dir)
        print(f"\n1. Loaded .aieng package: {package_path}")

        # Load initial claim_map
        claim_map_path = package_path / "results" / "claim_map.json"
        initial_claim_map = json.loads(claim_map_path.read_text())
        print(f"   Initial claims: {len(initial_claim_map['claims'])}")
        for claim in initial_claim_map["claims"]:
            print(f"      {claim['id']}: {claim['status']}")

        # Create mock evidence entry with a known metric
        evidence_id = "ev-mock-displacement-001"
        evidence_entry = {
            "evidence_id": evidence_id,
            "evidence_type": "mock_test",
            "producer_kind": "mock",
            "status": "success",
            "operation": "mock_analysis",
            "metadata": {
                "metrics": [
                    {"name": "max_displacement_mm", "value": 1.5, "unit": "mm", "status": "found"}
                ]
            },
        }

        evidence_path = package_path / "results" / "evidence_index.json"
        evidence_path.write_text(json.dumps({"entries": [evidence_entry]}), encoding="utf-8")
        print(f"\n2. Created mock evidence: {evidence_id}")
        print(f"   Metric: max_displacement_mm = 1.5 mm (under 2.0 mm limit)")

        # Dry-run claim update
        print("\n3. Running claim update (dry-run)...")
        dry_request = ClaimUpdateRequest(
            package_path=str(package_path),
            claim_id="claim_max_displacement_under_limit",
            evidence_ids=[evidence_id],
            decision_criteria=[
                ClaimDecisionCriterion(
                    metric_name="max_displacement_mm",
                    operator="<=",
                    threshold=2.0,
                    unit="mm",
                )
            ],
            mode="evaluate",
            dry_run=True,
        )
        dry_summary = update_claim_status(dry_request)

        print(f"   Dry-run status: {dry_summary.status}")
        print(f"   Predicted new status: {dry_summary.new_status}")
        assert dry_summary.claim_map_updated is False, "Dry-run must not write claim_map"

        # Verify claim_map unchanged after dry-run
        after_dry = json.loads(claim_map_path.read_text())
        assert after_dry == initial_claim_map, "Dry-run must not modify claim_map"
        print("   claim_map.json: UNCHANGED (dry-run)")

        # Real claim update
        print("\n4. Running claim update (real)...")
        real_request = ClaimUpdateRequest(
            package_path=str(package_path),
            claim_id="claim_max_displacement_under_limit",
            evidence_ids=[evidence_id],
            decision_criteria=[
                ClaimDecisionCriterion(
                    metric_name="max_displacement_mm",
                    operator="<=",
                    threshold=2.0,
                    unit="mm",
                )
            ],
            mode="evaluate",
            dry_run=False,
        )
        real_summary = update_claim_status(real_request)

        print(f"   Update status: {real_summary.status}")
        print(f"   Old status: {real_summary.old_status}")
        print(f"   New status: {real_summary.new_status}")
        print(f"   Claim map updated: {real_summary.claim_map_updated}")
        print(f"   Trace ID: {real_summary.trace_id}")

        # Verify claim_map updated
        final_claim_map = json.loads(claim_map_path.read_text())
        target_claim = None
        other_claims_unchanged = True
        for claim in final_claim_map["claims"]:
            if claim["id"] == "claim_max_displacement_under_limit":
                target_claim = claim
            elif claim["status"] != next(
                c["status"] for c in initial_claim_map["claims"] if c["id"] == claim["id"]
            ):
                other_claims_unchanged = False

        assert target_claim is not None
        assert target_claim["status"] == "pass", f"Expected pass, got {target_claim['status']}"
        assert other_claims_unchanged, "Other claims must not be modified"
        assert "last_updated" in target_claim
        assert target_claim["update_mode"] == "evaluate"
        assert target_claim["evidence_ids"] == [evidence_id]
        print("   claim_map.json: UPDATED (target claim only)")

        # Verify trace appended
        trace_path = package_path / "provenance" / "tool_trace.json"
        trace = json.loads(trace_path.read_text())
        assert len(trace.get("entries", [])) >= 1
        print(f"   Trace entries: {len(trace.get('entries', []))}")

        # Verify evidence_index unchanged
        evidence_after = json.loads(evidence_path.read_text())
        assert evidence_after == {"entries": [evidence_entry]}
        print("   evidence_index.json: UNCHANGED")

        # Show criteria results
        print(f"\n5. Criteria evaluation")
        for cr in real_summary.criteria_results:
            print(f"   {cr.metric_name}: actual={cr.actual_value}, threshold={cr.threshold}, result={cr.status}")

    print("\n" + "=" * 60)
    print(" Demo completed successfully.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
