from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare copied benchmark inputs for benchmark_runs/real_bracket_001.",
    )
    parser.add_argument("--package", default="build/real_bracket_001.aieng", help="Source .aieng package path")
    parser.add_argument(
        "--out-dir",
        default="benchmark_runs/real_bracket_001/input",
        help="Output folder for copied condition inputs",
    )
    parser.add_argument("--step", default="examples/real_bracket.step", help="Raw STEP fixture path")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    package_path = repo_root / args.package
    out_dir = repo_root / args.out_dir
    step_path = repo_root / args.step

    out_raw = out_dir / "condition_a_raw"
    out_aieng = out_dir / "condition_b_aieng"
    out_raw.mkdir(parents=True, exist_ok=True)
    out_aieng.mkdir(parents=True, exist_ok=True)

    if not step_path.exists():
        print(f"prepare benchmark: raw STEP not found: {step_path}")
        print("Generate it with scripts/generate_real_bracket_step.py")
        return 1

    shutil.copy2(step_path, out_raw / "real_bracket.step")

    if not package_path.exists():
        print(f"prepare benchmark: package not found: {package_path}")
        print("Run scripts/run_real_step_demo.py first")
        return 1

    wanted = [
        "manifest.json",
        "geometry/source.step",
        "geometry/normalized.step",
        "geometry/topology_map.json",
        "graph/aag.json",
        "graph/feature_graph.json",
        "graph/constraints.json",
        "simulation/setup.yaml",
        "ai/protected_regions.json",
        "ai/summary.md",
        "validation/status.yaml",
        "ai/patches/patch_0001.json",
    ]

    with zipfile.ZipFile(package_path, mode="r") as package:
        names = set(package.namelist())
        for member in wanted:
            if member not in names:
                print(f"prepare benchmark: WARN missing optional member: {member}")
                continue
            target = out_aieng / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(member))

    print(f"prepare benchmark: wrote raw inputs to {out_raw}")
    print(f"prepare benchmark: wrote .aieng inputs to {out_aieng}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
