from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(REPO_ROOT / "src")

import sys

if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from aieng.ai.summary_writer import summarize_package
from aieng.definition import define_package
from aieng.results.evidence_writer import write_evidence_scaffold_package
from aieng.task.external_tool_requirements_writer import write_external_tool_requirements_package
from aieng.task.task_spec_writer import write_task_spec_package
from aieng.validation.evidence_report_writer import write_evidence_report_package


def _copy_selected_members(package_path: Path, out_dir: Path, members: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, mode="r") as package:
        names = set(package.namelist())
        for member in members:
            if member not in names:
                continue
            target = out_dir / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(member))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare benchmark inputs for benchmark_runs/plate_with_pattern_001.",
    )
    parser.add_argument(
        "--definition",
        default="examples/definition_plate_with_pattern.yaml",
        help="Definition YAML used to generate probe packages",
    )
    parser.add_argument(
        "--rich-package",
        default="build/plate_with_pattern_001_rich.aieng",
        help="Output path for the rich .aieng variant",
    )
    parser.add_argument(
        "--sparse-package",
        default="build/plate_with_pattern_001_sparse.aieng",
        help="Output path for the sparse .aieng variant",
    )
    parser.add_argument(
        "--out-dir",
        default="benchmark_runs/plate_with_pattern_001/input",
        help="Output folder for copied condition inputs",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    definition_path = repo_root / args.definition
    rich_package = repo_root / args.rich_package
    sparse_package = repo_root / args.sparse_package
    out_dir = repo_root / args.out_dir

    if not definition_path.exists():
        print(f"prepare benchmark: definition not found: {definition_path}")
        return 1

    rich_package.parent.mkdir(parents=True, exist_ok=True)
    sparse_package.parent.mkdir(parents=True, exist_ok=True)

    define_package(definition_path, rich_package, overwrite=True)
    summarize_package(rich_package, overwrite=True)
    write_task_spec_package(
        rich_package,
        intent="Reduce mass by 12 percent while preserving the hole pattern interface.",
        overwrite=True,
    )
    write_external_tool_requirements_package(rich_package, overwrite=True)
    write_evidence_scaffold_package(rich_package, overwrite=True)
    write_evidence_report_package(rich_package, overwrite=True)

    define_package(definition_path, sparse_package, overwrite=True)

    out_rich = out_dir / "condition_b_rich"
    out_sparse = out_dir / "condition_b_sparse"
    if out_rich.exists():
        shutil.rmtree(out_rich)
    if out_sparse.exists():
        shutil.rmtree(out_sparse)

    rich_members = [
        "README_FOR_AI.md",
        "manifest.json",
        "graph/feature_graph.json",
        "graph/constraints.json",
        "ai/summary.md",
        "validation/status.yaml",
        "validation/completeness_report.json",
        "task/task_spec.yaml",
        "task/external_tool_requirements.json",
        "results/evidence_index.json",
        "results/claim_map.json",
        "validation/evidence_report.json",
    ]
    sparse_members = [
        "README_FOR_AI.md",
        "manifest.json",
        "graph/feature_graph.json",
        "graph/constraints.json",
        "validation/status.yaml",
        "validation/completeness_report.json",
    ]

    _copy_selected_members(rich_package, out_rich, rich_members)
    _copy_selected_members(sparse_package, out_sparse, sparse_members)

    print(f"prepare benchmark: wrote rich package to {rich_package}")
    print(f"prepare benchmark: wrote sparse package to {sparse_package}")
    print(f"prepare benchmark: copied rich inputs to {out_rich}")
    print(f"prepare benchmark: copied sparse inputs to {out_sparse}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
