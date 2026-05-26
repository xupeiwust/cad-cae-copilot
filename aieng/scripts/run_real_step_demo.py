from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import yaml

DEFAULT_INTENT = "Reduce mass by 15% while keeping mounting holes unchanged."


class _HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Show defaults while preserving multi-line description formatting."""


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


def _read_feature_graph(package_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(package_path, mode="r") as package:
        return json.loads(package.read("graph/feature_graph.json"))


def _feature_ids(feature_graph: dict[str, Any]) -> set[str]:
    features = feature_graph.get("features", [])
    return {
        item["id"]
        for item in features
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _load_context(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _context_is_compatible(context: dict[str, Any], known_feature_ids: set[str]) -> bool:
    protected = context.get("protected_features", [])
    simulation = context.get("simulation", {}) if isinstance(context.get("simulation"), dict) else {}
    fixed = simulation.get("fixed", [])
    loads = simulation.get("loads", [])

    referenced: set[str] = set()
    referenced.update(item for item in protected if isinstance(item, str))
    referenced.update(item for item in fixed if isinstance(item, str))
    for load in loads if isinstance(loads, list) else []:
        if isinstance(load, dict) and isinstance(load.get("target"), str):
            referenced.add(load["target"])
    return referenced.issubset(known_feature_ids)


def _first_feature_of_type(feature_graph: dict[str, Any], feature_type: str) -> str | None:
    features = feature_graph.get("features", [])
    for feature in features:
        if isinstance(feature, dict) and feature.get("type") == feature_type and isinstance(feature.get("id"), str):
            return feature["id"]
    return None


def _first_feature_id(feature_graph: dict[str, Any]) -> str | None:
    features = feature_graph.get("features", [])
    for feature in features:
        if isinstance(feature, dict) and isinstance(feature.get("id"), str):
            return feature["id"]
    return None


def _write_fallback_context(feature_graph: dict[str, Any], out_path: Path) -> Path:
    protected_id = (
        _first_feature_of_type(feature_graph, "mounting_hole_pattern")
        or _first_feature_of_type(feature_graph, "mounting_hole")
        or _first_feature_id(feature_graph)
    )
    load_id = (
        _first_feature_of_type(feature_graph, "base_plate")
        or _first_feature_of_type(feature_graph, "interface_face")
        or _first_feature_id(feature_graph)
    )

    if protected_id is None or load_id is None:
        raise SystemExit("real STEP demo: unable to derive fallback context because no feature IDs were found")

    fallback = {
        "material": "Al6061-T6",
        "protected_features": [protected_id],
        "simulation": {
            "type": "static_structural",
            "fixed": [protected_id],
            "loads": [
                {
                    "target": load_id,
                    "type": "force",
                    "value_n": 500,
                    "direction": [1, 0, 0],
                }
            ],
        },
        "targets": {"max_von_mises_stress_mpa": 120},
        "assumptions": [
            "Feature targets are candidate-level from rule-based recognition.",
            "No solver execution or mesh generation has been run in this demo.",
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(fallback, sort_keys=False), encoding="utf-8")
    print(f"real STEP demo: wrote fallback context at {out_path}")
    return out_path


def _ensure_context(repo_root: Path, package_path: Path, context_path: Path) -> Path:
    feature_graph = _read_feature_graph(package_path)
    known_feature_ids = _feature_ids(feature_graph)
    if not known_feature_ids:
        raise SystemExit("real STEP demo: feature graph has no feature IDs")

    if context_path.exists():
        try:
            context = _load_context(context_path)
            if isinstance(context, dict) and _context_is_compatible(context, known_feature_ids):
                return context_path
            print("real STEP demo: default context references IDs that are not present; generating fallback context")
        except Exception:
            print("real STEP demo: failed to parse default context; generating fallback context")

    fallback_path = repo_root / "build" / "real_bracket_user_context.generated.yaml"
    return _write_fallback_context(feature_graph, fallback_path)


def _summarize_outputs(package_path: Path) -> None:
    expected = [
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
    ]
    with zipfile.ZipFile(package_path, mode="r") as package:
        names = set(package.namelist())
    print("\nReal STEP demo generated resources:")
    for member in expected:
        status = "PASS" if member in names else "WARN"
        print(f"  {status} {member}")


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "Run the optional real STEP .aieng demo pipeline (Phase 11C).\n\n"
            "Pipeline: import-step -> extract-topology --backend occ -> build-aag -> "
            "recognize-features -> apply-context -> summarize -> propose-patch -> "
            "update-validation-status -> validate.\n\n"
            "Requires optional OCP/CadQuery runtime for --backend occ extraction."
        ),
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("--out", default="build/real_bracket_001.aieng", help="Output .aieng package path")
    parser.add_argument("--step", default="examples/real_bracket.step", help="Input real STEP fixture path")
    parser.add_argument(
        "--context",
        default="examples/real_bracket_user_context.yaml",
        help="Context YAML path (script auto-generates fallback context if IDs mismatch)",
    )
    parser.add_argument("--intent", default=DEFAULT_INTENT, help="Patch proposal intent")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(repo_root / "src"))
    try:
        from aieng.geometry.backend import detect_occ_runtime
    except Exception as exc:
        print(f"real STEP demo: could not import backend detector: {exc}", file=sys.stderr)
        return 1

    runtime = detect_occ_runtime()
    if not runtime.get("available") or runtime.get("provider") != "OCP":
        print(
            "real STEP demo: skipping because optional OCP/CadQuery runtime is unavailable.\n"
            f"Detection: {runtime.get('message', 'unknown')}\n"
            "Install optional dependency:\n"
            "  pip install cadquery\n"
            "Then generate fixture if needed:\n"
            "  python scripts/generate_real_bracket_step.py --overwrite"
        )
        return 0

    package_path = repo_root / args.out
    step_path = repo_root / args.step
    context_path = repo_root / args.context

    if not step_path.exists():
        print(
            f"real STEP demo: STEP fixture not found: {step_path}\n"
            "Generate it with:\n"
            "  python scripts/generate_real_bracket_step.py --overwrite",
            file=sys.stderr,
        )
        return 1

    package_path.parent.mkdir(parents=True, exist_ok=True)

    package_arg = _cli_path(package_path)
    step_arg = _cli_path(step_path)

    chain_pre_context = [
        ["import-step", step_arg, "--out", package_arg, "--overwrite"],
        ["extract-topology", package_arg, "--backend", "occ", "--overwrite"],
        ["build-aag", package_arg, "--overwrite"],
        ["recognize-features", package_arg, "--overwrite"],
    ]
    for command in chain_pre_context:
        _run_command(command, repo_root)

    resolved_context = _ensure_context(repo_root, package_path, context_path)
    context_arg = _cli_path(resolved_context)

    chain_post_context = [
        ["apply-context", package_arg, "--context", context_arg, "--overwrite"],
        ["summarize", package_arg, "--overwrite"],
        ["propose-patch", package_arg, "--intent", args.intent],
        ["update-validation-status", package_arg, "--overwrite"],
        ["validate", package_arg],
    ]
    for command in chain_post_context:
        _run_command(command, repo_root)

    _summarize_outputs(package_path)
    print(f"\nReal STEP demo complete: {package_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
