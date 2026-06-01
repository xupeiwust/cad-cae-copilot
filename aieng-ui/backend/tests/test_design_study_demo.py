"""Canonical design-study demo — full-flow PR1–PR4 regression (backend-only).

Validates, executes, ranks, and accepts candidates using deterministic static metrics.
No external solver. No random generation. Baseline geometry is never overwritten.
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
from design_study_demo_fixture import (
    ALL_STUDY_ARTIFACTS,
    BASELINE_SHAPE_IR_PATH,
    expected_accepted_artifacts,
    expected_candidate_artifacts,
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
    """Create a project with the canonical demo package. Returns (client, project_id, pkg_path, fixture_data)."""
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("design-study-demo"))
    project_id = project["id"]
    pkg = project_dir(settings, project_id) / "demo.aieng"
    data = write_demo_package(pkg)
    project["aieng_file"] = "demo.aieng"
    save_project(settings, project)
    return client, project_id, pkg, data


def _read_pkg(pkg: Path, name: str):
    with zipfile.ZipFile(pkg) as zf:
        return json.loads(zf.read(name))


def _baseline_unchanged(pkg: Path, original: dict) -> bool:
    return _read_pkg(pkg, BASELINE_SHAPE_IR_PATH) == original


# ── Part C: full-flow regression ──────────────────────────────────────────────

def test_canonical_demo_package_full_flow(tmp_path: Path) -> None:
    """PR1→PR2→PR3→PR4: validate → execute → rank → accept.

    Uses deterministic static evaluation metrics (no external solver).
    """
    client, project_id, pkg, data = _make_project_with_demo_package(tmp_path)
    baseline = data["baseline_shape_ir"]
    candidates = data["candidates"]

    # ── PR1: validate ────────────────────────────────────────────────────────
    resp = client.post(f"/api/projects/{project_id}/design-study/validate", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["design_study_present"] is True
    assert body["problem_status"] == "passed"
    assert body["candidate_count"] == 5

    # Verify diagnostics written
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert "diagnostics/design_study_problem_diagnostics.json" in names
        assert "diagnostics/design_study_candidate_validation.json" in names
    assert _baseline_unchanged(pkg, baseline)

    # ── PR2: execute candidates ──────────────────────────────────────────────
    # Execute each candidate (no compile — static metrics will be injected)
    for cid in candidates:
        resp = client.post(
            f"/api/projects/{project_id}/design-study/candidates/{cid}/run",
            json={"compile": False},
        )
        assert resp.status_code == 200, f"run {cid} failed: {resp.text}"
        run_body = resp.json()
        assert run_body["baseline_modified"] is False
        assert run_body["candidate_id"] == cid

    # Inject static evaluation metrics for deterministic ranking
    inject_static_evaluation(pkg, "candidate_good")
    inject_static_evaluation(pkg, "candidate_unknown")
    inject_static_evaluation(pkg, "candidate_infeasible")

    # Verify baseline still untouched after all executions
    assert _baseline_unchanged(pkg, baseline)

    # Verify iteration artifacts
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert DESIGN_STUDY_ITERATIONS_PATH in names
        assert DESIGN_STUDY_REPORT_PATH in names

    iters = _read_pkg(pkg, DESIGN_STUDY_ITERATIONS_PATH)["iterations"]
    assert len(iters) == 5
    by_id = {i["candidate_id"]: i for i in iters}

    # candidate_bad_bounds → rejected
    assert by_id["candidate_bad_bounds"]["execution_status"] == "rejected"
    # candidate_protected → rejected
    assert by_id["candidate_protected"]["execution_status"] == "rejected"
    # candidate_good → patch_applied (no compile)
    assert by_id["candidate_good"]["execution_status"] == "patch_applied"
    # candidate_unknown → patch_applied
    assert by_id["candidate_unknown"]["execution_status"] == "patch_applied"
    # candidate_infeasible → patch_applied
    assert by_id["candidate_infeasible"]["execution_status"] == "patch_applied"

    # Verify derived workspaces exist for valid candidates
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        for cid in ("candidate_good", "candidate_unknown", "candidate_infeasible"):
            for art in expected_candidate_artifacts(cid):
                assert art in names, f"missing {art}"
        # Rejected candidates have no workspace
        for cid in ("candidate_bad_bounds", "candidate_protected"):
            assert not any(n.startswith(f"candidates/{cid}/") for n in names)

    # ── PR3: rank ────────────────────────────────────────────────────────────
    resp = client.post(f"/api/projects/{project_id}/design-study/rank", json={})
    assert resp.status_code == 200, f"rank failed: {resp.text}"
    rank_body = resp.json()
    assert rank_body["design_study_present"] is True
    assert rank_body["candidate_count"] == 5

    # Verify ranking artifacts
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        assert DESIGN_STUDY_CANDIDATE_RANKING_PATH in names
        assert DESIGN_STUDY_SCORING_REPORT_PATH in names

    ranking = _read_pkg(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["status"] == "ranked"

    ranked = {c["candidate_id"]: c for c in ranking["candidates"]}
    # candidate_good is feasible and improves volume
    assert ranked["candidate_good"]["feasibility"] == "feasible"
    assert ranked["candidate_good"]["score"] > 0
    # candidate_infeasible has stress violation
    assert ranked["candidate_infeasible"]["feasibility"] == "infeasible"
    # candidate_unknown has no metrics
    assert ranked["candidate_unknown"]["feasibility"] == "unknown"
    # rejected candidates are failed
    assert ranked["candidate_bad_bounds"]["feasibility"] == "failed"
    assert ranked["candidate_protected"]["feasibility"] == "failed"

    # best_candidate_id is candidate_good (feasible + improves objective)
    assert ranking["best_candidate_id"] == "candidate_good"
    assert ranking["safe_to_accept"] is True

    # Verify baseline still untouched
    assert _baseline_unchanged(pkg, baseline)

    # ── PR4: accept ──────────────────────────────────────────────────────────
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_good/accept",
        json={"accepted_by": "agent", "reasoning": "best volume reduction within constraints"},
    )
    assert resp.status_code == 200, f"accept failed: {resp.text}"
    acc_body = resp.json()
    assert acc_body["accepted"] is True
    assert acc_body["baseline_modified"] is False
    assert acc_body["candidate_id"] == "candidate_good"

    # Verify acceptance artifacts
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
    assert report["artifact_existence_checks"]["patch"] is True
    assert report["artifact_existence_checks"]["shape_ir"] is True
    assert report["artifact_existence_checks"]["evaluation"] is True

    # Accepted Shape IR is the derived one, not baseline
    accepted_shape_ir = _read_pkg(pkg, "accepted/candidate_good/geometry/shape_ir.json")
    assert accepted_shape_ir != baseline
    assert accepted_shape_ir["parts"][0]["params"]["WALL_THICKNESS"] == 2.5
    assert accepted_shape_ir["parts"][0]["params"]["RIB_THICKNESS"] == 4.0

    # Baseline is STILL unchanged
    assert _baseline_unchanged(pkg, baseline)

    # No viewer artifacts created
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert not any("viewer" in n for n in names)
        assert not any("preview" in n for n in names)


# ── Part D: unsafe-data regression ────────────────────────────────────────────

def test_unsafe_data_rejects_acceptance(tmp_path: Path) -> None:
    """When no candidate is safe, acceptance is blocked and baseline is untouched."""
    client, project_id, pkg, data = _make_project_with_demo_package(tmp_path)
    baseline = data["baseline_shape_ir"]

    # Execute only the bad candidates (all rejected/failed)
    for cid in ("candidate_bad_bounds", "candidate_protected"):
        resp = client.post(
            f"/api/projects/{project_id}/design-study/candidates/{cid}/run",
            json={"compile": False},
        )
        assert resp.status_code == 200

    # Rank
    resp = client.post(f"/api/projects/{project_id}/design-study/rank", json={})
    assert resp.status_code == 200
    ranking = _read_pkg(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["best_candidate_id"] is None
    assert ranking["safe_to_accept"] is False
    assert ranking["next_action"] == "no_viable_candidate"

    # Try to accept a failed candidate — rejected
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_bad_bounds/accept",
        json={},
    )
    assert resp.status_code == 200  # endpoint returns 200 with rejection status
    body = resp.json()
    assert body["accepted"] is False
    assert body["status"] == "rejected"

    # Acceptance artifact records rejection
    acc = _read_pkg(pkg, DESIGN_STUDY_ACCEPTANCE_PATH)
    assert acc["status"] == "rejected"
    assert acc["accepted_candidate_id"] is None

    # No accepted workspace created
    with zipfile.ZipFile(pkg) as zf:
        names = zf.namelist()
        assert not any(n.startswith("accepted/") for n in names)

    # Baseline untouched
    assert _baseline_unchanged(pkg, baseline)


def test_non_best_candidate_needs_override(tmp_path: Path) -> None:
    """Accepting a non-best feasible candidate requires explicit override."""
    client, project_id, pkg, data = _make_project_with_demo_package(tmp_path)
    baseline = data["baseline_shape_ir"]

    # Execute only two: good (best) and unknown
    for cid in ("candidate_good", "candidate_unknown"):
        resp = client.post(
            f"/api/projects/{project_id}/design-study/candidates/{cid}/run",
            json={"compile": False},
        )
        assert resp.status_code == 200

    inject_static_evaluation(pkg, "candidate_good")
    inject_static_evaluation(pkg, "candidate_unknown")

    # Rank
    resp = client.post(f"/api/projects/{project_id}/design-study/rank", json={})
    assert resp.status_code == 200
    ranking = _read_pkg(pkg, DESIGN_STUDY_CANDIDATE_RANKING_PATH)
    assert ranking["best_candidate_id"] == "candidate_good"

    # Try to accept candidate_unknown — rejected because feasibility is unknown
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_unknown/accept",
        json={},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is False
    assert body["status"] == "rejected"  # unknown feasibility

    # Even with override, unknown candidates are rejected (not just unsafe)
    resp = client.post(
        f"/api/projects/{project_id}/design-study/candidates/candidate_unknown/accept",
        json={"override_unsafe": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is False
    assert body["status"] == "rejected"  # unknown feasibility

    # Baseline untouched
    assert _baseline_unchanged(pkg, baseline)


def test_missing_ranking_blocks_acceptance(tmp_path: Path) -> None:
    """Acceptance without prior ranking returns needs_user_input."""
    client, project_id, pkg, data = _make_project_with_demo_package(tmp_path)

    # Run a candidate but do NOT rank
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
