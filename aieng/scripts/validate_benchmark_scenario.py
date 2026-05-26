"""Validate a Phase 21 AI usefulness benchmark scenario directory.

Does NOT call external AI APIs. Checks:

1. All required scenario files exist.
2. ``example_result.json`` validates against ``results.schema.json``.
3. If ``condition_b.aieng`` is present, it has all 15 coverage_categories and passes
   the validator.

Usage::

    python scripts/validate_benchmark_scenario.py \\
        benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding

    # Also validate the package (if condition_b.aieng is present):
    python scripts/validate_benchmark_scenario.py \\
        benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding \\
        --validate-package

    # Generate condition_b.aieng first if missing:
    python scripts/validate_benchmark_scenario.py \\
        benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding \\
        --generate-package examples/sample_bracket.FCStd
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

_REQUIRED_FILES = [
    "README.md",
    "condition_a.md",
    "condition_b_index.md",
    "questions.md",
    "expected_scoring.md",
    "example_result.json",
]

_EXPECTED_COVERAGE_CATEGORIES = frozenset([
    "geometry", "topology", "object_registry", "stable_references",
    "features", "parameters", "assemblies", "materials", "loads",
    "boundary_conditions", "mesh", "solver_deck", "cad_cae_mappings",
    "editability_metadata", "writeback_metadata",
])


def _check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(f"FAIL  {message}")


def validate_scenario(scenario_dir: Path, *, validate_package: bool = False) -> list[str]:
    """Return a list of error strings. Empty list means all checks passed."""
    errors: list[str] = []

    if not scenario_dir.is_dir():
        return [f"FAIL  scenario directory does not exist: {scenario_dir}"]

    # 1. Required files
    for filename in _REQUIRED_FILES:
        _check(
            (scenario_dir / filename).exists(),
            f"required file missing: {scenario_dir / filename}",
            errors,
        )

    # 2. example_result.json validates against results.schema.json
    result_file = scenario_dir / "example_result.json"
    schema_file = scenario_dir.parents[1] / "results.schema.json"
    if result_file.exists() and schema_file.exists():
        try:
            result = json.loads(result_file.read_text(encoding="utf-8"))
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"FAIL  JSON parse error: {exc}")
            result = None
            schema = None

        if result is not None and schema is not None:
            try:
                import jsonschema
                validator = jsonschema.Draft202012Validator(schema)
                schema_errors = sorted(
                    validator.iter_errors(result), key=lambda e: list(e.path)
                )
                for err in schema_errors:
                    errors.append(f"FAIL  schema validation: {err.message} (path: {list(err.path)})")
                if not schema_errors:
                    pass  # schema valid
            except ImportError:
                # jsonschema not installed — do a manual field check instead
                for field in ("run_id", "timestamp_utc", "benchmark_scenario", "track",
                              "condition_a_scores", "condition_b_scores"):
                    _check(field in result, f"example_result.json missing field: {field}", errors)
                _check(
                    result.get("benchmark_scenario") == "ai_usefulness_v1",
                    "benchmark_scenario must be 'ai_usefulness_v1'",
                    errors,
                )
    elif result_file.exists() and not schema_file.exists():
        errors.append(f"FAIL  results.schema.json not found at: {schema_file}")

    # 3. questions.md references Track A
    questions_file = scenario_dir / "questions.md"
    if questions_file.exists():
        text = questions_file.read_text(encoding="utf-8").lower()
        _check(
            "track" in text or "q1" in text or "q2" in text,
            "questions.md appears to have no questions (expected Q1, Q2, ... or Track A header)",
            errors,
        )
        _check(
            "excluded" in text or "mcp" in text,
            "questions.md should list excluded capabilities",
            errors,
        )

    # 4. condition_a.md contains source input
    condition_a = scenario_dir / "condition_a.md"
    if condition_a.exists():
        text = condition_a.read_text(encoding="utf-8")
        _check(
            len(text) > 200,
            "condition_a.md appears too short to be a useful source input",
            errors,
        )

    # 5. condition_b_index.md lists at least one required resource
    condition_b_index = scenario_dir / "condition_b_index.md"
    if condition_b_index.exists():
        text = condition_b_index.read_text(encoding="utf-8")
        _check(
            "`" in text,
            "condition_b_index.md must list at least one resource in backticks",
            errors,
        )

    # 6. Optional: validate condition_b.aieng if present
    package_path = scenario_dir / "condition_b.aieng"
    if validate_package:
        if not package_path.exists():
            errors.append(
                f"FAIL  condition_b.aieng not found at {package_path}. "
                "Generate it with: aieng convert <source.FCStd> --out condition_b.aieng"
            )
        else:
            _validate_package(package_path, errors)

    return errors


def _validate_package(package_path: Path, errors: list[str]) -> None:
    try:
        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
            _check(
                "provenance/conversion_manifest.json" in names,
                "condition_b.aieng missing provenance/conversion_manifest.json",
                errors,
            )
            if "provenance/conversion_manifest.json" in names:
                manifest = json.loads(archive.read("provenance/conversion_manifest.json"))
                categories = {e["category"] for e in manifest.get("coverage_categories", [])}
                missing_cats = _EXPECTED_COVERAGE_CATEGORIES - categories
                _check(
                    not missing_cats,
                    f"condition_b.aieng coverage_categories missing: {sorted(missing_cats)}",
                    errors,
                )
    except zipfile.BadZipFile:
        errors.append(f"FAIL  condition_b.aieng is not a valid zip archive: {package_path}")
        return

    # Use aieng validator if available
    try:
        from aieng.validate import validate_package
        result = validate_package(package_path)
        fails = [m for m in result.messages if m.level.value == "FAIL"]
        _check(
            not fails,
            f"condition_b.aieng validator FAILs: {[m.text for m in fails]}",
            errors,
        )
    except ImportError:
        pass  # aieng not importable in this context


def generate_condition_b(source_path: Path, scenario_dir: Path) -> Path:
    """Generate condition_b.aieng from a CAD source file."""
    out = scenario_dir / "condition_b.aieng"
    try:
        from aieng.converters.cli_runners import convert_source
    except ImportError as exc:
        print(f"ERROR  aieng not importable: {exc}", file=sys.stderr)
        sys.exit(1)
    convert_source(
        source_path=source_path,
        out=out,
        model_id=scenario_dir.name,
        overwrite=True,
        runtime_mode="offline",
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Phase 21 AI usefulness benchmark scenario directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "scenario_dir",
        type=Path,
        help="Path to the scenario directory (e.g. benchmarks/ai_usefulness/scenarios/sample_bracket_cad_understanding)",
    )
    parser.add_argument(
        "--validate-package",
        action="store_true",
        help="Also validate condition_b.aieng if present (checks coverage_categories and validator)",
    )
    parser.add_argument(
        "--generate-package",
        metavar="SOURCE",
        type=Path,
        help="Generate condition_b.aieng from SOURCE before validating",
    )
    args = parser.parse_args(argv)

    scenario_dir = args.scenario_dir.resolve()

    if args.generate_package:
        print(f"Generating condition_b.aieng from {args.generate_package} ...")
        out = generate_condition_b(args.generate_package, scenario_dir)
        print(f"  Written: {out}")
        args.validate_package = True

    print(f"Validating scenario: {scenario_dir}")
    errors = validate_scenario(scenario_dir, validate_package=args.validate_package)

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(f"\nFAIL  {len(errors)} check(s) failed.", file=sys.stderr)
        return 1

    print(f"PASS  All checks passed for: {scenario_dir.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
