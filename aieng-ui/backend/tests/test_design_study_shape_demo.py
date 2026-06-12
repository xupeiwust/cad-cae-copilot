"""Phase-3 shape-study demo — fillet radius + hole diameter on a bracket.

End-to-end backend regression exercising:
  opt.propose_candidates/opt.propose_next over shape-bearing vars
  → execute candidates
  → evaluate candidates with P3-2 critique folding
  → rank candidates (with the small ranking fix for critique-driven infeasibility)
  → explain recommendation
  → write report
  → accept best candidate (approval-gated)

Uses deterministic static metrics and fake geometry snapshots so
``cad.critique`` can flag a manufacturing-rule violation without an external
solver or geometry kernel.  Baseline geometry is never overwritten.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_AIENG_SRC = _WORKSPACE_ROOT / "aieng" / "src"
_TESTS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_AIENG_SRC) not in sys.path:
    sys.path.insert(0, str(_AIENG_SRC))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.main import Settings, create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient

from aieng.converters.design_study_acceptance import (
    DESIGN_STUDY_ACCEPTANCE_PATH,
    DESIGN_STUDY_ACCEPTANCE_REPORT_PATH,
)
from aieng.converters.design_study_execution import (
    DESIGN_STUDY_ITERATIONS_PATH,
    DESIGN_STUDY_REPORT_PATH,
)
from aieng.converters.design_study_ranking import (
    DESIGN_STUDY_CANDIDATE_RANKING_PATH,
    DESIGN_STUDY_SCORING_REPORT_PATH,
)
from aieng.converters.optimization_recommendation import OPTIMIZATION_RECOMMENDATION_PATH
from aieng.converters.optimization_report import OPTIMIZATION_REPORT_PATH
from design_study_shape_demo_fixture import (
    ALL_STUDY_ARTIFACTS,
    BASELINE_SHAPE_IR_PATH,
    expected_accepted_artifacts,
    expected_cae_evaluation_artifacts,
    expected_candidate_artifacts,
    inject_candidate_geometry,
    inject_static_evaluation,
    load_demo_inputs,
    write_demo_package,
)


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project_with_demo_package(tmp_path: Path) -> tuple[TestClient, str, Path, dict]:
    """Create a project with the shape-study demo package."""
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("design-study-shape-demo"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "shape-demo.aieng"
    data = write_demo_package(pkg)
    project["aieng_file"] = "shape-demo.aieng"
    save_project(settings, project)
    return client, project_id, pkg, data


def _read_pkg(pkg: Path, name: str):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def _baseline_unchanged(pkg: Path, original: dict) -> bool:
    return _read_pkg(pkg, BASELINE_SHAPE_IR_PATH) == original


# ── Part C: full-flow shape-study regression ───────────────────────────────────

def test_shape_study_demo_full_flow(tmp_path: Path) -> None:
    """PR1→PR2→PR3→recommendation→report→PR4 for a shape-bearing bracket study."""
    client, project_id, pkg, data = _make_project_with_demo_package(tmp_path)
    baseline = data["baseline_shape_ir"]
    candidates = data["candidates"]
    assert len(candidates) == 5, "fixture should provide ≥5 candidates"

    # ── PR1: validate ────────────────────────────────────────────────────────
    resp = client.post(f"/api/projects/{project_id}/design-study/validate", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["design_study_present"] is True
    assert body["problem_status"] == "passed"
    assert body["candidate_count"] == 5

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert "diagnostics/design_study_problem_diagnostics.json" in names
        assert "diagnostics/design_study_candidate_validation.json" in names
    assert _baseline_unchanged(pkg, baseline)

    # ── PR2: execute candidates (no external compile) ────────────────────────
    for cid in candidates:
        resp = client.post(
            f"/api/projects/{project_id}/design-study/candidates/{cid}/run",
            json={"compile": False},
        )
        assert resp.status_code == 200, f"run {cid} failed: {resp.text}"
        run_body = resp.json()
        assert run_body["baseline_modified"] is False
        assert run_body["candidate_id"] == cid

    # Inject deterministic static metrics + fake geometry snapshots for critique.
    for cid in ("candidate_good", "candidate_larger_hole", "candidate_sharp_fillet", "candidate_overstressed"):
        inject_static_evaluation(pkg, cid)
        inject_candidate_geometry(pkg, cid)

    # ── Candidate-local CAE evaluation (normalize_existing, no solver) ───────
    for cid in ("candidate_good", "candidate_larger_hole", "candidate_sharp_fillet", "candidate_overstressed", "candidate_unknown"):
        resp = client.post(
            f"/api/projects/{project_id}/design-study/candidates/{cid}/cae-evaluate",
            json={"mode": "normalize_existing", "allow_solver_execution": False,
                  "allow_ranking_refresh": False, "requested_by": "test"},
        )
        assert resp.status_code == 200, f"cae-evaluate {cid} failed: {resp.text}"
        cae_body = resp.json()
        assert cae_body["baseline_modified"] is False
        assert cae_body["candidate_id"] == cid

    # Verify evaluation artifacts and critique-driven infeasibility.
    sharp_eval = _read_pkg(pkg, "candidates/candidate_sharp_fillet/analysis/evaluation.json")
    assert sharp_eval["feasibility"] == "infeasible"
    assert sharp_eval["evaluation_status"] == "complete"
    assert sharp_eval["critique_blocking"] is True
    assert any(
        e.get("rule") == "min_wall_thickness" and e.get("status") == "violated"
        for e in sharp_eval.get("constraint_evidence", [])
    )

    over_eval = _read_pkg(pkg, "candidates/candidate_overstressed/analysis/evaluation.json")
    assert over_eval["feasibility"] == "infeasible"
    assert over_eval["evaluation_status"] == "complete"

    good_eval = _read_pkg(pkg, "candidates/candidate_good/analysis/evaluation.json")
    assert good_eval["feasibility"] == "feasible"
    assert good_eval["evaluation_status"] == "complete"

    # candidate_unknown has no metrics and no geometry, so evaluation is unknown.
    # (The evaluation artifact may be created lazily during ranking; we assert
    # the ranking classification below instead of the artifact here.)

    # Baseline still untouched after all executions + evaluations
    assert _baseline_unchanged(pkg, baseline)

    # Verify iteration artifacts
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert DESIGN_STUDY_ITERATIONS_PATH in names
        assert DESIGN_STUDY_REPORT_PATH in names

    iters = _read_pkg(pkg, DESIGN_STUDY_ITERATIONS_PATH)["iterations"]
    assert len(iters) == 5
    by_id = {i["candidate_id"]: i for i in iters}
    for cid in candidates:
        assert by_id[cid]["execution_status"] == "patch_applied", (
            f"{cid}: {by_id[cid].get('execution_status')} - errors: {by_id[cid].get('errors')}"
        )

    # Verify derived workspaces exist
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        for cid in candidates:
            for art in expected_candidate_artifacts(cid):
                assert art in names, f"missing {art}"
            for art in expected_cae_evaluation_artifacts(cid):
                assert art in names, f"missing cae artifact: {art}"

    # ── PR3: rank ────────────────────────────────────────────────────────────
    resp = client.post(f"/api/projects/{project_id}/design-study/rank", json={})
    assert resp.status_code == 200, f"rank failed: {resp.text}"
    rank_body = resp.json()
    assert rank_body["design_study_present"] is True
    assert rank_body["candidate_count"] == 5

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert DESIGN_STUDY_CANDIDATE_RANKING_PATH in names
        assert DESIGN_STUDY_SCORING_REPORT_PATH in names

    ranking = _read_pkg(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["status"] == "ranked"

    ranked = {c["candidate_id"]: c for c in ranking["candidates"]}
    assert ranked["candidate_good"]["feasibility"] == "feasible"
    assert ranked["candidate_good"]["score"] > 0
    assert ranked["candidate_larger_hole"]["feasibility"] == "feasible"
    assert ranked["candidate_overstressed"]["feasibility"] == "infeasible"
    assert ranked["candidate_unknown"]["feasibility"] == "unknown"

    # Key P3-2 assertion: critique-driven infeasibility propagates to ranking.
    assert ranked["candidate_sharp_fillet"]["feasibility"] == "infeasible"
    assert any(
        "min_wall_thickness" in v for v in ranked["candidate_sharp_fillet"]["constraint_violations"]
    ), "manufacturing-rule violation should appear in ranking constraint_violations"
    assert any(
        "min_wall_thickness" in r or "critique" in r.lower()
        for r in ranked["candidate_sharp_fillet"]["reasons"]
    )

    # Best candidate is the feasible one with the highest score.
    assert ranking["best_candidate_id"] == "candidate_good"
    assert ranking["safe_to_accept"] is True

    # Scoring report reflects the manufacturing-rule violation.
    scoring = _read_pkg(pkg, DESIGN_STUDY_SCORING_REPORT_PATH)
    assert scoring["constraint_evaluation_summary"]["violations_found"] >= 1
    violation_detail = scoring["constraint_evaluation_summary"]["violation_details"]
    assert any(
        d["candidate_id"] == "candidate_sharp_fillet" and any("min_wall_thickness" in v for v in d["violations"])
        for d in violation_detail
    )

    # ── Recommendation (advisory, reason-coded) ──────────────────────────────
    resp = client.post(f"/api/projects/{project_id}/design-study/recommendation", json={})
    assert resp.status_code == 200, f"recommendation failed: {resp.text}"
    rec_body = resp.json()
    assert rec_body["status"] == "ok"
    assert rec_body["advisory_only"] is True
    assert rec_body["recommended_candidate_id"] == "candidate_good"
    assert rec_body.get("reason_codes")

    with zipfile.ZipFile(pkg) as zf:
        assert OPTIMIZATION_RECOMMENDATION_PATH in zf.namelist()

    recommendation = _read_pkg(pkg, OPTIMIZATION_RECOMMENDATION_PATH)
    assert recommendation["advisory_only"] is True
    assert recommendation["recommended_candidate_id"] == "candidate_good"
    assert recommendation.get("reason_codes")

    # ── Report: must flag this as a shape study (P3-1) ───────────────────────
    resp = client.post(f"/api/projects/{project_id}/design-study/report", json={})
    assert resp.status_code == 200, f"report failed: {resp.text}"
    report_body = resp.json()
    assert report_body["status"] == "ok"
    assert report_body["baseline_modified"] is False

    with zipfile.ZipFile(pkg) as zf:
        assert OPTIMIZATION_REPORT_PATH in zf.namelist()

    report = _read_pkg(pkg, OPTIMIZATION_REPORT_PATH)
    assert report["problem"]["shape_study"] is True
    assert report["problem"]["shape_bearing_variable_count"] == 2
    assert report["candidate_count"] == 5
    assert report["ranking"]["best_candidate_id"] == "candidate_good"

    # Baseline still untouched
    assert _baseline_unchanged(pkg, baseline)

    # ── PR4: accept (approval-gated) ─────────────────────────────────────────
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_good/accept",
        json={"accepted_by": "agent", "reasoning": "best mass reduction within constraints and manufacturing rules"},
    )
    assert resp.status_code == 200, f"accept failed: {resp.text}"
    acc_body = resp.json()
    assert acc_body["accepted"] is True
    assert acc_body["baseline_modified"] is False
    assert acc_body["candidate_id"] == "candidate_good"

    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert DESIGN_STUDY_ACCEPTANCE_PATH in names
        assert DESIGN_STUDY_ACCEPTANCE_REPORT_PATH in names
        for art in expected_accepted_artifacts("candidate_good"):
            assert art in names, f"missing accepted artifact: {art}"

    acceptance = _read_pkg(pkg, DESIGN_STUDY_ACCEPTANCE_PATH)
    assert acceptance["status"] == "accepted"
    assert acceptance["accepted_candidate_id"] == "candidate_good"
    assert acceptance["baseline_modified"] is False
    assert acceptance["promotion_mode"] == "derived_only"

    report = _read_pkg(pkg, DESIGN_STUDY_ACCEPTANCE_REPORT_PATH)
    assert report["accepted"] is True
    assert report["eligibility_checks"]["eligible"] is True
    assert report["eligibility_checks"]["safe_to_accept"] is True
    assert report["eligibility_checks"]["is_best_candidate"] is True

    # Accepted Shape IR is derived, not baseline.
    accepted_shape_ir = _read_pkg(pkg, "accepted/candidate_good/geometry/shape_ir.json")
    assert accepted_shape_ir != baseline
    assert accepted_shape_ir["parts"][0]["params"]["FILLET_RADIUS"] == 3.0
    assert accepted_shape_ir["parts"][0]["params"]["HOLE_DIAMETER"] == 8.0

    # Baseline STILL unchanged
    assert _baseline_unchanged(pkg, baseline)


# ── Part D: unsafe-data regression for shape study ────────────────────────────

def test_shape_study_rejects_manufacturing_rule_candidate(tmp_path: Path) -> None:
    """A candidate that passes numerical constraints but fails manufacturing rules
    is correctly ranked infeasible and cannot be accepted."""
    client, project_id, pkg, data = _make_project_with_demo_package(tmp_path)
    baseline = data["baseline_shape_ir"]

    # Execute, evaluate only the critique-infeasible candidate.
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_sharp_fillet/run",
        json={"compile": False},
    )
    assert resp.status_code == 200
    inject_static_evaluation(pkg, "candidate_sharp_fillet")
    inject_candidate_geometry(pkg, "candidate_sharp_fillet")
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_sharp_fillet/cae-evaluate",
        json={"mode": "normalize_existing", "allow_solver_execution": False,
              "allow_ranking_refresh": False, "requested_by": "test"},
    )
    assert resp.status_code == 200

    resp = client.post(f"/api/projects/{project_id}/design-study/rank", json={})
    assert resp.status_code == 200
    ranking = _read_pkg(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["best_candidate_id"] is None
    assert ranking["safe_to_accept"] is False
    assert ranking["next_action"] == "no_viable_candidate"

    sharp = next(c for c in ranking["candidates"] if c["candidate_id"] == "candidate_sharp_fillet")
    assert sharp["feasibility"] == "infeasible"
    assert any("min_wall_thickness" in v for v in sharp["constraint_violations"])

    # Try to accept the infeasible candidate — rejected.
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_sharp_fillet/accept",
        json={"override_unsafe": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is False
    assert body["status"] == "rejected"

    assert _baseline_unchanged(pkg, baseline)


def test_shape_study_missing_ranking_blocks_acceptance(tmp_path: Path) -> None:
    """Acceptance without prior ranking returns needs_user_input."""
    client, project_id, pkg, data = _make_project_with_demo_package(tmp_path)

    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_good/run",
        json={"compile": False},
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_good/accept",
        json={},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is False
    assert body["status"] == "needs_user_input"
    assert any("ranking" in r.lower() for r in body["reasons"])
