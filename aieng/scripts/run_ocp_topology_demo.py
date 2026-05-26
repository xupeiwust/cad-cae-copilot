from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _cli_path(path: Path) -> str:
    return path.as_posix()


def _run_command(args: list[str], repo_root: Path) -> None:
    env = os.environ.copy()
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else src_path
    full_command = [sys.executable, "-m", "aieng.cli", *args]
    print("$", " ".join(full_command))
    completed = subprocess.run(full_command, cwd=repo_root, env=env, text=True)
    if completed.returncode != 0:
        raise SystemExit(f"command failed with exit code {completed.returncode}: {' '.join(args)}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    repo_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "Optional OCP topology demo for .aieng (Phase 7C).\n\n"
            "Requires OCP/CadQuery: pip install cadquery\n"
            "Requires a real STEP file exported from a CAD application.\n"
            "The examples/bracket.step fixture is a mock-only fixture and cannot be used here.\n\n"
            "Exits cleanly with a skip message if OCP is not installed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "step_file",
        nargs="?",
        default=None,
        help="Path to a real STEP file (.step or .stp) from a CAD application.",
    )
    parser.add_argument(
        "--out",
        default="build/ocp_topology_demo.aieng",
        help="Output .aieng package path (default: build/ocp_topology_demo.aieng)",
    )
    args = parser.parse_args(argv)

    if args.step_file is None:
        print(
            "OCP topology demo: no STEP file provided.\n"
            "\n"
            "Usage: python scripts/run_ocp_topology_demo.py path/to/model.step\n"
            "\n"
            "This demo requires a real STEP file exported from a CAD application\n"
            "(FreeCAD, Fusion 360, SolidWorks, or similar).\n"
            "The examples/bracket.step fixture is a mock-only fixture and cannot be used.\n"
            "\n"
            "Also requires OCP/CadQuery: pip install cadquery\n"
            "\n"
            "See docs/ocp_topology_demo.md for full instructions."
        )
        return 0

    # Check OCP availability via detect_occ_runtime
    sys.path.insert(0, str(repo_root / "src"))
    try:
        from aieng.geometry.backend import detect_occ_runtime
        runtime = detect_occ_runtime()
    except Exception as exc:
        print(f"OCP topology demo: could not check OCP runtime: {exc}", file=sys.stderr)
        return 1

    if not runtime["available"] or runtime.get("provider") != "OCP":
        provider_msg = runtime.get("message", "")
        print(
            f"OCP topology demo: skipping — OCP/CadQuery is not available.\n"
            f"  {provider_msg}\n"
            f"\n"
            f"Install CadQuery and try again:\n"
            f"  pip install cadquery\n"
            f"\n"
            f"See docs/ocp_topology_demo.md for full instructions."
        )
        return 0

    step_path = Path(args.step_file).resolve()
    if not step_path.exists():
        print(f"OCP topology demo: STEP file not found: {step_path}", file=sys.stderr)
        return 1

    package_path = repo_root / args.out
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_arg = _cli_path(package_path)
    step_arg = _cli_path(step_path)

    print(f"OCP topology demo: OCP runtime detected ({runtime['provider']})")
    print(f"OCP topology demo: input  {step_path}")
    print(f"OCP topology demo: output {package_path}")
    print()

    chain = [
        ["import-step", step_arg, "--out", package_arg, "--overwrite"],
        ["extract-topology", package_arg, "--backend", "occ", "--overwrite"],
        ["update-validation-status", package_arg, "--overwrite"],
        ["validate", package_arg],
    ]
    for command in chain:
        _run_command(command, repo_root)

    print()
    print(f"OCP topology demo complete: {package_path}")
    print()
    print("Inspect results:")
    print("  python -c \"")
    print("  import zipfile, json, yaml")
    print(f"  with zipfile.ZipFile('{_cli_path(package_path)}') as zf:")
    print("      topo = json.loads(zf.read('geometry/topology_map.json'))")
    print("      status = yaml.safe_load(zf.read('validation/status.yaml'))")
    print("      print('extraction_backend:', topo['metadata']['extraction_backend'])")
    print("      print('real_step_parsing:', topo['metadata']['real_step_parsing'])")
    print("      print('topology_status:', status['topology_status']['status'])")
    print("  \"")
    print()
    print("See docs/ocp_topology_demo.md for full field-by-field inspection guidance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
