"""Canonical iterative sizing-optimization demo — full Phase-2 Slice-A flow (#64).

Drives the whole iterative loop end-to-end through the REST layer on the same
deterministic plate-with-hole bracket as the Phase-1 open-loop demo, with NO
external solver:

  seed sample -> [ run -> inject static metrics -> evaluate -> rank ->
  check-convergence -> propose-next ]* -> accept (approval-gated) -> report

Metric model (stand-in for CAE): thinner wall = lighter but higher stress/defl,
so minimizing mass s.t. max_stress<=200 and max_displacement<=1.0 has a real
feasible frontier (wall >= 3). The trust-region proposer refines around the
incumbent with a shrinking radius, so the incumbent mass improves then plateaus
and convergence fires. Baseline geometry is never overwritten.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.main import create_app, default_project, project_dir, save_project
from starlette.testclient import TestClient
from test_api import _make_patch_settings

WALL_VAR_PATH = "parts/0/params/WALL_THICKNESS"


def _metrics_for_wall(wall: float) -> dict[str, float]:
    return {
        "mass_kg": round(0.5 + 0.15 * wall, 4),
        "max_stress": round(600.0 / wall, 4),
        "max_displacement": round(3.0 / wall, 4),
    }


def _baseline():
    return {"representation": "brep_build123d",
            "parts": [{"id": "plate", "type": "box",
                       "params": {"WALL_THICKNESS": 5.0, "FILLET_RADIUS": 2.0}}]}


def _problem():
    return {
        "format": "aieng.design_study_problem", "schema_version": "0.1", "id": "bracket_iter_001",
        "variables": [
            {"id": "wall_t", "path": WALL_VAR_PATH, "type": "continuous",
             "current_value": 5.0, "min_value": 2.0, "max_value": 6.0, "unit": "mm",
             "safe_to_modify": True, "semantic_role": "wall_thickness"},
        ],
        "constraints": [
            {"id": "stress_limit", "type": "max_stress", "limit": 200.0, "unit": "MPa"},
            {"id": "disp_limit", "type": "max_deflection", "limit": 1.0, "unit": "mm"},
        ],
        "objective": {"sense": "minimize", "metric": "mass"},
        "baseline_metrics": _metrics_for_wall(5.0),
        "settings": {"max_variables_per_candidate": 1, "require_reasoning": True},
        # tighten convergence so the demo converges quickly + deterministically
        "convergence": {"min_rel_improvement": 0.02, "patience": 2},
    }


def _variables_doc():
    return {
        "format": "aieng.optimization_variables", "schema_version": "0.2",
        "study_id": "opt_iter_001",
        "design_study_problem_ref": "analysis/design_study_problem.json",
        "design_study_problem_id": "bracket_iter_001",
        "variables": [
            {"id": "wall_t", "path": WALL_VAR_PATH, "type": "continuous",
             "current_value": 5.0, "min_value": 2.0, "max_value": 6.0, "unit": "mm",
             "safe_to_modify": True, "featureId": "feat_wall", "parameterName": "wall_t",
             "cad_parameter_name": "WALL_THICKNESS", "binding_status": "bound",
             "allowed_values": None, "scope": "local", "candidate_ids": []},
        ],
        "candidate_ids": [],
        "provenance": {"created_at": "2026-06-10T00:00:00Z", "created_by": "demo",
                       "claim_advancement": "none"},
        "claim_policy": {"advisory_only": True, "baseline_unchanged": True,
                         "human_approval_required_for_acceptance": True, "claim_advancement": "none"},
    }


def _seed(settings, project_id: str) -> Path:
    pkg = project_dir(settings, project_id) / "study.aieng"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as p:
        p.writestr("manifest.json", "{}")
        p.writestr("geometry/shape_ir.json", json.dumps(_baseline()))
        p.writestr("analysis/design_study_problem.json", json.dumps(_problem()))
        p.writestr("analysis/optimization_variables.json", json.dumps(_variables_doc()))
        p.writestr("analysis/static_metrics.json", json.dumps(_metrics_for_wall(5.0)))
    return pkg


def _write_seed_candidate(pkg: Path, cid: str, wall: float) -> None:
    """Write one deterministic feasible-but-heavy seed candidate (start = baseline wall).

    Seeding from the heavy baseline (rather than a lucky LHS draw) makes the
    refinement loop *visibly* improve the incumbent toward the feasible optimum.
    """
    patch = {"format": "aieng.design_candidate_patch", "candidate_id": cid,
             "variable_changes": [{"variable_id": "wall_t", "new_value": wall}],
             "reasoning": "seed at baseline wall thickness"}
    member = f"patches/design_candidates/{cid}.json"
    tmp = pkg.with_suffix(".seed.tmp.aieng")
    with zipfile.ZipFile(pkg, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for i in src.infolist():
            if i.filename != member:
                dst.writestr(i, src.read(i.filename))
        dst.writestr(member, json.dumps(patch).encode("utf-8"))
    tmp.replace(pkg)


def _wall_of(pkg: Path, cid: str) -> float:
    with zipfile.ZipFile(pkg) as p:
        patch = json.loads(p.read(f"patches/design_candidates/{cid}.json"))
    for ch in patch.get("variable_changes") or []:
        if ch.get("variable_id") == "wall_t":
            return float(ch["new_value"])
    return 5.0


def _inject_metrics(pkg: Path, candidate_ids: list[str]) -> None:
    """Write deterministic per-candidate static metrics (CAE stand-in) keyed on wall."""
    members = {
        f"candidates/{cid}/analysis/static_metrics.json":
            json.dumps(_metrics_for_wall(_wall_of(pkg, cid))).encode("utf-8")
        for cid in candidate_ids
    }
    tmp = pkg.with_suffix(".inj.tmp.aieng")
    with zipfile.ZipFile(pkg, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for i in src.infolist():
            if i.filename not in members:
                dst.writestr(i, src.read(i.filename))
        for n, d in members.items():
            dst.writestr(n, d)
    tmp.replace(pkg)


def _round(client, base, pkg, candidate_ids):
    """Run one evaluation round over the given new candidate ids, return convergence body."""
    run = client.post(f"{base}/run-candidates", json={"compile": False, "candidate_ids": candidate_ids})
    assert run.status_code == 200 and run.json()["status"] == "ok"
    _inject_metrics(pkg, candidate_ids)
    ev = client.post(f"{base}/evaluate-candidates", json={})
    assert ev.status_code == 200 and ev.json()["status"] == "ok"
    rank = client.post(f"{base}/rank", json={})
    assert rank.status_code == 200 and rank.json()["status"] == "ok"
    conv = client.post(f"{base}/check-convergence", json={})
    assert conv.status_code == 200 and conv.json()["status"] == "ok"
    return conv.json()


def test_iterative_sizing_demo_end_to_end(tmp_path: Path) -> None:
    settings = _make_patch_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("iter-demo"))
    project_id = project["id"]
    pkg = _seed(settings, project_id)
    project["aieng_file"] = "study.aieng"
    save_project(settings, project)
    base = f"/api/projects/{project_id}/design-study"

    with zipfile.ZipFile(pkg) as p:
        baseline_before = json.loads(p.read("geometry/shape_ir.json"))

    # ── round 0: seed deliberately heavy (baseline wall=5.0) so refinement has
    #    room to improve the incumbent toward the feasible optimum (wall=3) ────
    _write_seed_candidate(pkg, "cand_seed_heavy", 5.0)
    conv = _round(client, base, pkg, ["cand_seed_heavy"])
    seed_mass = conv["incumbent_objective"]
    assert seed_mass is not None

    incumbent_masses: list[float] = [seed_mass]
    radii: list[float] = []
    rounds = 0
    # ── iterate: propose-next → round, until converged or budget ─────────────
    while not conv["converged"] and rounds < 10:
        rounds += 1
        prop = client.post(f"{base}/propose-next", json={"count": 4, "shrink": 0.6, "seed": 100 + rounds})
        assert prop.status_code == 200
        pbody = prop.json()
        assert pbody["status"] == "ok"
        radii.append(pbody["radius_fraction"])
        conv = _round(client, base, pkg, pbody["candidate_ids"])
        if conv.get("incumbent_objective") is not None:
            incumbent_masses.append(conv["incumbent_objective"])

    # ── assertions on loop behavior ──────────────────────────────────────────
    assert conv["converged"] is True
    assert "converged_objective_delta" in conv["reason_codes"]
    # incumbent mass is monotonically non-increasing (ranking keeps the global best)
    for prev, cur in zip(incumbent_masses, incumbent_masses[1:]):
        assert cur <= prev + 1e-9
    # trust-region radius shrinks across iterations
    for prev, cur in zip(radii, radii[1:]):
        assert cur <= prev + 1e-9
    # the loop genuinely improved the incumbent below the heavy seed
    assert conv["incumbent_objective"] < seed_mass
    # the converged incumbent is feasible (wall >= 3) and near the optimum
    best_id = conv["incumbent_candidate_id"]
    assert best_id is not None
    assert _wall_of(pkg, best_id) >= 3.0 - 1e-6
    assert conv["feasible"] is True

    # ── accept (approval-gated) + report ─────────────────────────────────────
    acc = client.post(f"{base}/candidates/{best_id}/accept", json={})
    assert acc.status_code == 200 and acc.json()["accepted"] is True
    rep = client.post(f"{base}/report", json={})
    assert rep.status_code == 200 and rep.json()["status"] == "ok"

    with zipfile.ZipFile(pkg) as p:
        names = set(p.namelist())
        assert "analysis/optimization_iterations.json" in names
        assert f"accepted/{best_id}/geometry/shape_ir.json" in names
        report = json.loads(p.read("diagnostics/optimization_report.json"))
        iters = json.loads(p.read("analysis/optimization_iterations.json"))
        # baseline untouched through the whole loop
        assert json.loads(p.read("geometry/shape_ir.json")) == baseline_before

    # report aggregates the iteration history + acceptance
    assert report["iteration_history"]["iteration_count"] == len(iters["iterations"])
    assert report["iteration_history"]["iteration_count"] >= 3
    assert report["acceptance"]["accepted_candidate_id"] == best_id
    assert report["honesty"]["baseline_modified"] is False
    # the final recorded verdict is the converged one
    assert iters["latest_verdict"]["verdict"] == "converged"
