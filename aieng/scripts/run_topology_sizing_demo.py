"""Scripted demo: 2D topology → sizing → CAE end-to-end (#110).

Deterministic, no external solver. Creates a plate-with-loads .aieng package,
bridges a 2D contour topology writeback to a sizing study, samples candidates,
evaluates them with analytical stand-in metrics, ranks, recommends, and performs
an approval-gated acceptance.

Usage:
    python scripts/run_topology_sizing_demo.py [--out build/topology_sizing_demo.aieng]
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

DENSITY_KG_MM3 = 2.7e-6


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _metrics_for_thickness(thickness: float) -> dict[str, Any]:
    area = 100.0  # 10 x 10 square plate
    volume = area * float(thickness)
    return {"volume_mm3": round(volume, 4), "mass_kg": round(volume * DENSITY_KG_MM3, 8)}


def _shape_ir() -> dict[str, Any]:
    return {
        "format": "aieng.shape_ir",
        "representation": "manifold_mesh",
        "model_id": "optimized_plate",
        "parts": [
            {
                "id": "optimized_plate",
                "label": "optimized_plate",
                "type": "extruded_region",
                "polygons": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                "boundary": "polygon",
                "thickness": 5.0,
                "origin": [0, 0, 0],
                "u_axis": "x",
                "v_axis": "y",
                "placed_in_frame": True,
                "source_optimization": {"optimizer": "simp_2d"},
            }
        ],
    }


def _topology_optimization() -> dict[str, Any]:
    return {
        "format": "aieng.topology_optimization",
        "schema_version": "0.1",
        "contract_version": "0.1",
        "dimension": "2d",
        "optimizer": {"name": "simp_2d", "method": "SIMP", "dimension": 2},
        "objective": "compliance_minimization",
        "problem": {"design_space_node": "plate", "volfrac": 0.5},
        "result": {},
    }


def _create_package(package_path: Path) -> None:
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _dumps({
            "format": "aieng.package",
            "format_version": "0.1.0",
            "resources": {},
        }))
        zf.writestr("metadata.json", _dumps({"name": "topology sizing demo"}))
        zf.writestr("geometry/shape_ir.json", _dumps(_shape_ir()))
        zf.writestr("analysis/topology_optimization.json", _dumps(_topology_optimization()))


def _rewrite_member(package_path: Path, name: str, data: bytes) -> None:
    tmp = package_path.with_suffix(".demo.tmp.aieng")
    with (
        zipfile.ZipFile(package_path, "r") as src,
        zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            if item.filename != name:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(name, data)
    tmp.replace(package_path)


def _thickness_of_candidate(package_path: Path, cid: str) -> float:
    with zipfile.ZipFile(package_path) as zf:
        patch = json.loads(zf.read(f"patches/design_candidates/{cid}.json"))
    for ch in patch.get("variable_changes") or []:
        if ch.get("variable_id") == "extrusion_thickness":
            return float(ch["new_value"])
    return 5.0


def _inject_baseline_metrics(package_path: Path) -> None:
    with zipfile.ZipFile(package_path, "r") as zf:
        problem = json.loads(zf.read("analysis/design_study_problem.json"))
    problem["baseline_metrics"] = _metrics_for_thickness(5.0)
    _rewrite_member(package_path, "analysis/design_study_problem.json", _dumps(problem))


def _inject_static_metrics(package_path: Path, candidate_ids: list[str]) -> None:
    members: dict[str, bytes] = {}
    for cid in candidate_ids:
        thickness = _thickness_of_candidate(package_path, cid)
        members[f"candidates/{cid}/analysis/static_metrics.json"] = _dumps(_metrics_for_thickness(thickness))
    tmp = package_path.with_suffix(".inject.tmp.aieng")
    with (
        zipfile.ZipFile(package_path, "r") as src,
        zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            if item.filename not in members:
                dst.writestr(item, src.read(item.filename))
        for name, data in members.items():
            dst.writestr(name, data)
    tmp.replace(package_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the 2D topology → sizing → CAE demo.")
    parser.add_argument("--out", default="build/topology_sizing_demo.aieng", help="Output .aieng package path")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    package_path = repo_root / args.out
    _create_package(package_path)
    print(f"Created demo package: {package_path}")

    # Ensure PYTHONPATH so the aieng package is importable.
    import os
    import sys
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from aieng.converters.design_study_acceptance import accept_design_study_candidate
    from aieng.converters.design_study_batch import (
        run_design_study_batch,
        run_design_study_evaluation_batch,
    )
    from aieng.converters.design_study_ranking import rank_design_study_candidates
    from aieng.converters.optimization_recommendation import explain_recommendation
    from aieng.converters.optimization_report import build_optimization_report
    from aieng.converters.optimization_sampler import sample_candidates_package
    from aieng.converters.topology_to_sizing import topology_to_sizing

    # 1) Bridge topology → sizing.
    t2s = topology_to_sizing(package_path)
    if t2s.get("status") != "ok":
        print(f"topology_to_sizing: {t2s.get('status')} ({t2s.get('code')})")
        return 1
    print("1) topology_to_sizing: ok")

    # 1b) Add baseline metrics for high-confidence ranking.
    _inject_baseline_metrics(package_path)

    # 2) Sample candidates.
    sample = sample_candidates_package(package_path, algorithm="grid", max_candidates=5)
    if sample.get("status") != "ok":
        print(f"sample_candidates: {sample.get('status')} - {sample.get('message')}")
        return 1
    candidate_ids = [c["candidate_id"] for c in sample.get("candidates", [])]
    print(f"2) sampled {len(candidate_ids)} candidates: {candidate_ids}")

    # 3) Execute without recompilation.
    run = run_design_study_batch(package_path, recompiler=None)
    if run.get("status") != "ok":
        print(f"run_design_study_batch: {run.get('status')} - {run.get('message')}")
        return 1
    print(f"3) executed {run.get('executed')} candidates")

    # 4) Inject analytical metrics.
    _inject_static_metrics(package_path, candidate_ids)
    print("4) injected analytical volume/mass metrics")

    # 5) Evaluate.
    ev = run_design_study_evaluation_batch(package_path)
    if ev.get("status") != "ok":
        print(f"evaluate: {ev.get('status')} - {ev.get('message')}")
        return 1
    print(f"5) evaluated {ev.get('evaluated')} candidates")

    # 6) Rank.
    rank = rank_design_study_candidates(package_path)
    if rank.get("status") != "ok":
        print(f"rank: {rank.get('status')} - {rank.get('message')}")
        return 1
    best_id = rank.get("best_candidate_id")
    print(f"6) ranked; best_candidate_id={best_id}, safe_to_accept={rank.get('safe_to_accept')}")

    # 7) Recommend.
    rec = explain_recommendation(package_path)
    if rec.get("status") != "ok":
        print(f"recommendation: {rec.get('status')} - {rec.get('message')}")
        return 1
    print(f"7) recommendation: {rec.get('recommended_candidate_id')} ({rec.get('headline')})")

    # 8) Acceptance (approval-gated).
    if best_id is None:
        print("No best candidate; acceptance skipped")
        return 0
    acc = accept_design_study_candidate(package_path, best_id, accepted_by="demo")
    if not acc.get("accepted"):
        print(f"acceptance failed: {acc.get('status')} - {acc.get('reasons')}")
        return 1
    print(f"8) acceptance: {acc.get('candidate_id')} accepted (derived-only)")

    # 9) Report.
    rep = build_optimization_report(package_path)
    if rep.get("status") != "ok":
        print(f"report: {rep.get('status')} - {rep.get('message')}")
        return 1
    print("9) report: ok")

    # ── summary ───────────────────────────────────────────────────────────────
    with zipfile.ZipFile(package_path) as zf:
        study = json.loads(zf.read("analysis/optimization_study.json"))
        report_doc = json.loads(zf.read("diagnostics/optimization_report.json"))
        tool_trace = json.loads(zf.read("provenance/tool_trace.json"))

    chain = study.get("topology_to_sizing_chain", {})
    print()
    print("Demo summary:")
    print(f"  production_ready: {chain.get('production_ready')}")
    print(f"  design_space_node: {chain.get('design_space_node')}")
    print(f"  accepted_candidate_id: {acc.get('candidate_id')}")
    print(f"  baseline_modified: {report_doc.get('honesty', {}).get('baseline_modified')}")
    print(f"  tool_trace_entries: {len(tool_trace.get('entries', []))}")
    print()
    print("Key artifacts:")
    for name in (
        "analysis/design_study_problem.json",
        "analysis/optimization_study.json",
        "analysis/optimization_decision_log.json",
        "analysis/design_study_candidate_ranking.json",
        "analysis/design_study_acceptance.json",
        "diagnostics/optimization_report.json",
        "provenance/tool_trace.json",
    ):
        print(f"  {name}")
    print()
    print(f"Package written to: {package_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
