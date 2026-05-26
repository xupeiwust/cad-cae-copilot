"""v1.0.0 Public composable `.aieng`-enhanced CAD/CAE execution demo.

CAD and CAE workflows are independent first-class capabilities.
This demo shows five composable paths:

1. cad-only    — .aieng patch -> FreeCAD edit -> modified artifact evidence -> trace
2. cae-only    — .aieng simulation setup -> CAE evidence -> post-process evidence -> trace
3. cad-cae     — CAD patch -> modified artifact -> explicit CAE orchestration -> evidence -> trace
4. reference   — reference_map -> geometry modification -> affected refs marked needs_review
5. claim       — evidence_ids + criteria -> explicit aieng_update_claim -> claim_map update
6. all         — run all five paths sequentially

Usage:
    python scripts/run_v1_demo.py --path cad-only
    python scripts/run_v1_demo.py --path all
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEMO_DIR = Path(__file__).resolve().parent
ROOT_DIR = DEMO_DIR.parent


def _run_script(name: str) -> int:
    script = DEMO_DIR / name
    print(f"\n{'=' * 70}")
    print(f" Running: {name}")
    print(f"{'=' * 70}")
    result = subprocess.run([sys.executable, str(script)])
    if result.returncode != 0:
        print(f"FAILED: {name} exited with code {result.returncode}")
    else:
        print(f"SUCCESS: {name}")
    return result.returncode


def path_cad_only() -> int:
    """Path 1: CAD-only — patch execution without CAE."""
    print("\n[Path 1: CAD-only]")
    print("Demonstrates that CAD patch execution is an independent workflow.")
    print("No CAE mesh, deck, or solver is invoked.")
    return _run_script("run_aieng_patch_demo.py")


def path_cae_only() -> int:
    """Path 2: CAE-only — post-processing without a preceding patch."""
    print("\n[Path 2: CAE-only]")
    print("Demonstrates that CAE execution is an independent workflow.")
    print("No CAD geometry modification is performed.")
    return _run_script("run_postprocessing_demo.py")


def path_cad_cae() -> int:
    """Path 3: Optional CAD->CAE — explicit orchestration of independent workflows."""
    print("\n[Path 3: Optional CAD->CAE]")
    print("Demonstrates explicit optional orchestration of CAD + CAE.")
    print("The orchestration helper is not automatic; it runs only when invoked.")
    return _run_script("run_cad_to_cae_demo.py")


def path_reference() -> int:
    """Path 4: Reference — traceability metadata as an independent support workflow."""
    print("\n[Path 4: Reference]")
    print("Demonstrates traceability metadata independence.")
    print("No CAE or claim updates are triggered.")
    return _run_script("run_reference_mapping_demo.py")


def path_claim() -> int:
    """Path 5: Claim — explicit evidence-backed claim update."""
    print("\n[Path 5: Claim]")
    print("Demonstrates that claim updates are explicit and independent.")
    print("Evidence alone does not advance claims.")
    return _run_script("run_claim_update_demo.py")


def path_all() -> int:
    """Run all five composable paths sequentially."""
    print("\n" + "=" * 70)
    print(" v1.0.0 Public Composable .aieng-Enhanced CAD/CAE Execution Demo")
    print("=" * 70)
    print("\nCAD and CAE workflows are independent first-class capabilities.")
    print("CAD modification does not automatically trigger CAE execution.")
    print("CAE execution does not require a preceding CAD modification.")
    print("CAD and CAE may be combined only when explicitly requested.")

    results: dict[str, int] = {}
    results["cad-only"] = path_cad_only()
    results["cae-only"] = path_cae_only()
    results["cad-cae"] = path_cad_cae()
    results["reference"] = path_reference()
    results["claim"] = path_claim()

    print("\n" + "=" * 70)
    print(" Summary")
    print("=" * 70)
    all_passed = True
    for name, code in results.items():
        status = "PASS" if code == 0 else "FAIL"
        if code != 0:
            all_passed = False
        print(f"  {name:12s} -> {status}")

    if all_passed:
        print("\n  All five composable paths completed successfully.")
        print("=" * 70)
        return 0
    else:
        print("\n  Some paths failed. See output above.")
        print("=" * 70)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="v1.0.0 Public composable .aieng-enhanced CAD/CAE execution demo"
    )
    parser.add_argument(
        "--path",
        choices=["cad-only", "cae-only", "cad-cae", "reference", "claim", "all"],
        default="all",
        help="Which composable path to run (default: all)",
    )
    args = parser.parse_args()

    paths: dict[str, callable[[], int]] = {
        "cad-only": path_cad_only,
        "cae-only": path_cae_only,
        "cad-cae": path_cad_cae,
        "reference": path_reference,
        "claim": path_claim,
        "all": path_all,
    }

    return paths[args.path]()


if __name__ == "__main__":
    sys.exit(main())
