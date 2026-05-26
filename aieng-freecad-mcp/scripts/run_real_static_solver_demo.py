"""Real static structural solver demo.

Demonstrates the real FreeCAD FEM / CalculiX solver path with conservative
fallback when components are unavailable.

Usage:
    python scripts/run_real_static_solver_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from freecad_mcp.aieng_bridge.persistence import (
    append_evidence_entry,
    append_trace_entry,
)
from freecad_mcp.freecad_runtime import detect_freecad_runtime


def _copy_fixture(tmp_dir: Path) -> Path:
    fixture_src = Path(__file__).resolve().parent.parent / "examples" / "parametric_bracket" / "package"
    fixture_dst = tmp_dir / "package"
    shutil.copytree(fixture_src, fixture_dst)
    return fixture_dst


def main() -> int:
    print("=" * 60)
    print(" Real Static Solver Demo")
    print("=" * 60)

    # 1. Runtime detection
    print("\n1. Detecting runtime capabilities...")
    caps = detect_freecad_runtime()
    print(f"   FreeCAD available: {caps.freecad_available}")
    print(f"   FreeCAD version: {caps.freecad_version}")
    print(f"   FEM available: {caps.fem_available}")
    print(f"   Gmsh available: {caps.gmsh_available}")
    print(f"   Netgen available: {caps.netgen_available}")
    print(f"   CalculiX available: {caps.calculix_available}")
    print(f"   Headless supported: {caps.headless_supported}")

    if not caps.freecad_available:
        print("\n   FreeCAD not available. Skipping real solver demo.")
        print("   (This is not an error; real solver is optional.)")
        return 0

    if not caps.fem_available:
        print("\n   FreeCAD FEM workbench not available. Skipping real solver demo.")
        return 0

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        package_path = _copy_fixture(tmp_dir)
        print(f"\n2. Loaded .aieng package: {package_path}")

        # 2. Build a simple model in FreeCAD
        print("\n3. Building simple model in FreeCAD...")
        import FreeCAD as App

        doc = App.newDocument("SolverDemo")
        box = doc.addObject("Part::Box", "BasePlate")
        box.Length = 100.0
        box.Width = 60.0
        box.Height = 10.0
        doc.recompute()
        print(f"   Model: {box.Length}x{box.Width}x{box.Height} mm box")

        # 3. Create FEM analysis (if FEM is available)
        print("\n4. Creating FEM analysis...")
        try:
            import ObjectsFem

            analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
            solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "Solver")
            solver.AnalysisType = "static"
            analysis.addObject(solver)

            # Material
            material = ObjectsFem.makeMaterialSolid(doc, "Material")
            mat = material.Material
            mat["Name"] = "Aluminum 6061-T6"
            mat["YoungsModulus"] = "68900 MPa"
            mat["PoissonRatio"] = "0.33"
            material.Material = mat
            analysis.addObject(material)

            # Fixed constraint
            fixed = ObjectsFem.makeConstraintFixed(doc, "FixedConstraint")
            analysis.addObject(fixed)

            # Force load
            force = ObjectsFem.makeConstraintForce(doc, "ForceLoad")
            force.Force = 500.0
            force.Direction = (0, 0, -1)
            analysis.addObject(force)

            print("   FEM analysis created successfully")
            fem_created = True
        except Exception as exc:
            print(f"   FEM setup failed: {exc}")
            fem_created = False

        # 4. Mesh (if mesher available)
        mesh_generated = False
        if fem_created:
            print("\n5. Generating mesh...")
            try:
                mesh_obj = ObjectsFem.makeMeshGmsh(doc, "Mesh")
                mesh_obj.Part = box
                from femmesh import gmshtools

                gmsh = gmshtools.GmshTools(mesh_obj)
                error = gmsh.create_mesh()
                if error:
                    print(f"   Mesh warning: {error}")
                else:
                    print(f"   Mesh generated: {len(mesh_obj.FemMesh.Nodes)} nodes")
                    mesh_generated = True
            except Exception as exc:
                print(f"   Mesh generation skipped: {exc}")

        # 5. Export deck
        deck_exported = False
        deck_path = None
        if fem_created:
            print("\n6. Exporting solver deck...")
            try:
                import Fem

                deck_path = str(tmp_dir / "solver_deck.inp")
                Fem.writeDeck(deck_path, doc)
                if Path(deck_path).exists():
                    print(f"   Deck exported: {deck_path}")
                    deck_exported = True
            except Exception as exc:
                print(f"   Deck export skipped: {exc}")

        # 6. Run solver
        solver_executed = False
        result_path = None
        if deck_exported and caps.calculix_available:
            print("\n7. Running CalculiX solver...")
            try:
                import subprocess

                solver_dir = tmp_dir / "solver_run"
                solver_dir.mkdir(parents=True, exist_ok=True)
                # Copy deck to solver dir
                deck_in_solver = solver_dir / "model.inp"
                shutil.copy2(deck_path, str(deck_in_solver))
                # Run ccx
                result = subprocess.run(
                    ["ccx", "model"],
                    cwd=str(solver_dir),
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print("   Solver completed successfully")
                    solver_executed = True
                    # Look for result files
                    for ext in [".frd", ".dat"]:
                        candidate = solver_dir / f"model{ext}"
                        if candidate.exists():
                            result_path = str(candidate)
                            print(f"   Result file: {result_path}")
                            break
                else:
                    print(f"   Solver exit code: {result.returncode}")
                    if result.stderr:
                        print(f"   stderr: {result.stderr[:200]}")
            except Exception as exc:
                print(f"   Solver run failed: {exc}")
        elif deck_exported and not caps.calculix_available:
            print("\n7. CalculiX not available; solver run skipped.")
        else:
            print("\n7. No deck to run; solver skipped.")

        # 7. Extract metrics
        metrics: list[dict[str, Any]] = []
        if result_path:
            print("\n8. Extracting metrics...")
            # Conservative: try to parse result file, but don't guess
            try:
                # For .frd files, we could parse with FreeCAD FEM
                # For now, record that result exists but values are not parsed
                metrics.append(
                    {
                        "name": "max_displacement_mm",
                        "value": None,
                        "status": "not_found",
                        "reason": "Result parsing not yet implemented; file exists.",
                    }
                )
                metrics.append(
                    {
                        "name": "max_von_mises_mpa",
                        "value": None,
                        "status": "not_found",
                        "reason": "Result parsing not yet implemented; file exists.",
                    }
                )
                print("   Result file present; metrics marked not_found (conservative)")
            except Exception as exc:
                metrics.append(
                    {
                        "name": "result_parsing",
                        "value": None,
                        "status": "unsupported",
                        "reason": str(exc),
                    }
                )
        else:
            print("\n8. No result file; metrics not available.")
            metrics.append(
                {
                    "name": "max_displacement_mm",
                    "value": None,
                    "status": "not_found",
                    "reason": "Solver did not produce result file.",
                }
            )

        # 8. Write evidence and trace
        print("\n9. Writing evidence and trace...")
        evidence_entry = {
            "evidence_id": "ev-real-solver-demo",
            "evidence_type": "solver_execution",
            "producer_kind": "freecad_fem" if fem_created else "surrogate",
            "status": "success" if solver_executed else "partial",
            "operation": "run_real_static_solver_demo",
            "metadata": {
                "freecad_version": caps.freecad_version,
                "fem_available": caps.fem_available,
                "mesh_generated": mesh_generated,
                "solver_deck_exported": deck_exported,
                "solver_executed": solver_executed,
                "calculix_available": caps.calculix_available,
                "engineering_validation": False,
                "claims_advanced": False,
                "metrics": metrics,
            },
            "warnings": caps.warnings,
        }

        trace_entry = {
            "trace_id": "trace-real-solver-demo",
            "producer": "freecad_mcp",
            "operation": "run_real_static_solver_demo",
            "status": "success" if solver_executed else "partial",
            "inputs": {
                "freecad_version": caps.freecad_version,
                "fem_available": caps.fem_available,
            },
            "outputs": {
                "mesh_generated": mesh_generated,
                "solver_deck_exported": deck_exported,
                "solver_executed": solver_executed,
                "metrics": metrics,
            },
        }

        append_evidence_entry(str(package_path), evidence_entry)
        append_trace_entry(str(package_path), trace_entry)

        evidence = json.loads((package_path / "results" / "evidence_index.json").read_text())
        trace = json.loads((package_path / "provenance" / "tool_trace.json").read_text())
        print(f"   Evidence entries: {len(evidence.get('entries', []))}")
        print(f"   Trace entries: {len(trace.get('entries', []))}")

        # Verify claim_map unchanged
        claim_map = json.loads((package_path / "results" / "claim_map.json").read_text())
        assert all(c["status"] == "unsupported" for c in claim_map.get("claims", []))
        print(f"   claim_map.json: UNCHANGED")

        # Verify evidence metadata
        last_ev = evidence["entries"][-1]
        meta = last_ev.get("metadata", {})
        assert meta.get("engineering_validation") is False
        assert meta.get("claims_advanced") is False
        print(f"   engineering_validation: {meta.get('engineering_validation')}")
        print(f"   claims_advanced: {meta.get('claims_advanced')}")
        print(f"   solver_executed: {meta.get('solver_executed')}")

        App.closeDocument(doc.Name)

    print("\n" + "=" * 60)
    print(" Demo completed successfully.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
