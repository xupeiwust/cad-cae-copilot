"""Design-history branching + governed baseline promotion (#202)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from aieng.converters.design_study_acceptance import DESIGN_STUDY_ACCEPTANCE_PATH
from aieng.converters.design_study_promotion import (
    BASELINE_BRANCH_ID,
    DESIGN_HISTORY_PATH,
    promote_design_branch,
    record_design_branch,
    rollback_baseline_promotion,
)


def _pkg(tmp_path: Path, *, accepted_id: str | None = "cand_good", status: str = "accepted") -> Path:
    pkg = tmp_path / "study.aieng"
    acc = {
        "format": "aieng.design_study.acceptance.v0",
        "status": status,
        "accepted_candidate_id": accepted_id,
        "accepted_by": "engineer_a",
        "accepted_artifacts": ["accepted/cand_good/geometry/shape_ir.json"],
    }
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("metadata.json", json.dumps({"name": "study"}))
        zf.writestr(DESIGN_STUDY_ACCEPTANCE_PATH, json.dumps(acc))
    return pkg


def _history(pkg: Path) -> dict:
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(DESIGN_HISTORY_PATH))


def test_branch_created_for_accepted_candidate() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pkg = _pkg(Path(td))
        res = record_design_branch(pkg, candidate_id="cand_good", created_by="engineer_a",
                                   rationale="lighter bracket")
        assert res["status"] == "ok"
        assert res["branch_id"] == "branch_cand_good"
        assert res["parent"] == BASELINE_BRANCH_ID
        h = _history(pkg)
        b = h["branches"][0]
        assert b["candidate_id"] == "cand_good"
        assert b["parent"] == BASELINE_BRANCH_ID
        assert b["status"] == "derived"
        assert b["provenance"]["accepted_by"] == "engineer_a"
        assert h["honesty"]["baseline_geometry_overwritten"] is False


def test_branch_refused_when_candidate_not_accepted() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pkg = _pkg(Path(td), status="rejected")
        res = record_design_branch(pkg, candidate_id="cand_good", created_by="x", rationale="y")
        assert res["status"] == "needs_user_input"
        assert res["reason"] == "candidate_not_accepted"
        assert res["baseline_modified"] is False
        # no history written
        with zipfile.ZipFile(pkg) as zf:
            assert DESIGN_HISTORY_PATH not in set(zf.namelist())


def test_promotion_denied_without_explicit_approval() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pkg = _pkg(Path(td))
        record_design_branch(pkg, candidate_id="cand_good", created_by="a", rationale="r")
        res = promote_design_branch(pkg, candidate_id="cand_good", approved_by="engineer_b",
                                    approval=False, rationale="not yet")
        assert res["status"] == "refused"
        assert res["reason"] == "approval_required"
        assert res["baseline_modified"] is False
        # current baseline still the original baseline
        assert _history(pkg)["current_baseline"]["branch_id"] == BASELINE_BRANCH_ID


def test_promotion_requires_a_branch_first() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pkg = _pkg(Path(td))
        res = promote_design_branch(pkg, candidate_id="cand_good", approved_by="engineer_b",
                                    approval=True, rationale="promote")
        assert res["status"] == "needs_user_input"
        assert res["reason"] == "no_branch_for_candidate"


def test_approved_promotion_moves_baseline_and_records_provenance() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pkg = _pkg(Path(td))
        record_design_branch(pkg, candidate_id="cand_good", created_by="a", rationale="r")
        res = promote_design_branch(pkg, candidate_id="cand_good", approved_by="engineer_b",
                                    approval=True, rationale="meets targets",
                                    changed={"wall_thickness_mm": {"from": 5, "to": 4}})
        assert res["status"] == "ok"
        assert res["to_baseline"] == "branch_cand_good"
        assert res["from_baseline"] == BASELINE_BRANCH_ID
        assert res["baseline_geometry_overwritten"] is False
        h = _history(pkg)
        assert h["current_baseline"]["branch_id"] == "branch_cand_good"
        promo = h["promotions"][0]
        assert promo["approved"] is True
        assert promo["approved_by"] == "engineer_b"
        assert promo["rationale"] == "meets targets"
        assert promo["changed"]["wall_thickness_mm"] == {"from": 5, "to": 4}
        assert any(b["branch_id"] == "branch_cand_good" and b["status"] == "promoted" for b in h["branches"])


def test_rollback_restores_previous_baseline() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pkg = _pkg(Path(td))
        record_design_branch(pkg, candidate_id="cand_good", created_by="a", rationale="r")
        promote_design_branch(pkg, candidate_id="cand_good", approved_by="engineer_b",
                              approval=True, rationale="promote")
        res = rollback_baseline_promotion(pkg, performed_by="engineer_c", rationale="regression found")
        assert res["status"] == "ok"
        assert res["restored_baseline"] == BASELINE_BRANCH_ID
        assert res["rolled_back_branch"] == "branch_cand_good"
        h = _history(pkg)
        assert h["current_baseline"]["branch_id"] == BASELINE_BRANCH_ID
        assert h["rollbacks"][0]["performed_by"] == "engineer_c"
        assert any(b["branch_id"] == "branch_cand_good" and b["status"] == "rolled_back" for b in h["branches"])
