from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_INTENT = "Reduce mass by 15% while keeping mounting holes unchanged."


def _cli_path(path: Path) -> str:
    return path.as_posix()


def command_chain(package_path: Path, context_path: Path, step_path: Path, intent: str) -> list[list[str]]:
    package_arg = _cli_path(package_path)
    context_arg = _cli_path(context_path)
    step_arg = _cli_path(step_path)
    return [
        ["import-step", step_arg, "--out", package_arg, "--overwrite"],
        ["extract-topology", package_arg, "--overwrite"],
        ["recognize-features", package_arg, "--overwrite"],
        ["apply-context", package_arg, "--context", context_arg, "--overwrite"],
        ["build-visual-index", package_arg, "--overwrite"],
        ["build-visual-manifest", package_arg, "--overwrite"],
        ["build-interface-graph", package_arg, "--overwrite"],
        ["import-cae-deck", package_arg, "--deck", "examples/bracket_loadcase.inp", "--format", "calculix", "--overwrite"],
        ["apply-cae-mapping", package_arg, "--mapping", "examples/bracket_cae_mapping.yaml", "--overwrite"],
        ["build-interface-graph", package_arg, "--overwrite"],
        ["build-object-registry", package_arg, "--overwrite"],
        ["summarize", package_arg, "--overwrite"],
        ["propose-patch", package_arg, "--intent", intent],
        ["export-calculix", package_arg, "--out", "build/solver_deck.inp", "--overwrite"],
        ["update-validation-status", package_arg, "--overwrite"],
        ["validate", package_arg],
    ]


def run_command(args: list[str], repo_root: Path) -> None:
    env = os.environ.copy()
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else src_path
    full_command = [sys.executable, "-m", "aieng.cli", *args]
    print("$", " ".join(full_command))
    completed = subprocess.run(full_command, cwd=repo_root, env=env, text=True)
    if completed.returncode != 0:
        raise SystemExit(f"command failed with exit code {completed.returncode}: {' '.join(args)}")


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run the .aieng reference bracket demo.")
    parser.add_argument("--out", default="build/bracket_001.aieng", help="Output .aieng package path")
    parser.add_argument("--step", default="examples/bracket.step", help="Input STEP-like fixture path")
    parser.add_argument("--context", default="examples/bracket_user_context.yaml", help="Input user context YAML path")
    parser.add_argument("--intent", default=DEFAULT_INTENT, help="Patch proposal intent")
    args = parser.parse_args(argv)

    package_path = repo_root / args.out
    step_path = repo_root / args.step
    context_path = repo_root / args.context
    package_path.parent.mkdir(parents=True, exist_ok=True)

    for command in command_chain(package_path, context_path, step_path, args.intent):
        run_command(command, repo_root)

    print(f"Reference demo complete: {package_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
