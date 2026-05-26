from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(REPO_ROOT / "src")

import sys

if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from aieng.benchmarking import BenchmarkPaths, BenchmarkRunConfig, ProviderConfig, run_benchmark


class _HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_dotenv_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_wrapping_quotes(value.strip())
        loaded[key] = value
        if key not in os.environ:
            os.environ[key] = value
    return loaded


def _resolve_env_backed_value(cli_value: Optional[str], env_name: str) -> Optional[str]:
    if cli_value is not None:
        return cli_value
    return os.getenv(env_name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real_bracket_001 benchmark with a general LLM.\n\n"
            "Examples:\n"
            "  python scripts/run_benchmark.py --provider anthropic --model claude-3-7-sonnet-latest --condition both\n"
            "  python scripts/run_benchmark.py --provider openai-compatible --base-url https://example.invalid/v1 --model my-model --condition B\n"
            "  python scripts/run_benchmark.py --dry-run\n\n"
            "Configuration may also come from a .env file via BENCHMARK_PROVIDER, BENCHMARK_MODEL,\n"
            "BENCHMARK_BASE_URL, BENCHMARK_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY."
        ),
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("--condition", default="both", help="A, B, or both")
    parser.add_argument("--provider", default=None, help="anthropic or openai-compatible; falls back to BENCHMARK_PROVIDER")
    parser.add_argument("--model", default=None, help="Model name to use; falls back to BENCHMARK_MODEL")
    parser.add_argument("--api-key", default=None, help="Optional API key override; falls back to BENCHMARK_API_KEY")
    parser.add_argument("--api-key-env", default=None, help="Environment variable name holding the API key")
    parser.add_argument("--base-url", default=None, help="Required for openai-compatible providers; falls back to BENCHMARK_BASE_URL")
    parser.add_argument("--env-file", default=".env", help="Optional dotenv file to load before resolving defaults")
    parser.add_argument("--dry-run", action="store_true", help="Print input and token estimates without calling the model")
    parser.add_argument("--question-file", default="benchmark_runs/real_bracket_001/questions.md")
    parser.add_argument("--rubric-file", default="benchmarks/scoring_rubric.md")
    parser.add_argument("--condition-a-path", default="examples/real_bracket.step")
    parser.add_argument("--condition-b-index", default="benchmark_runs/real_bracket_001/aieng_input_index.md")
    parser.add_argument("--condition-b-source", default="build/real_bracket_001.aieng")
    parser.add_argument("--results-dir", default="benchmarks/results")
    parser.add_argument("--schema-file", default="benchmarks/results.schema.json")
    parser.add_argument("--output", default=None, help="Optional explicit output path")
    parser.add_argument("--input-price-per-million-tokens", type=float, default=None)
    parser.add_argument("--output-price-per-million-tokens", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=12288)
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature for provider calls")
    parser.add_argument("--top-p", type=float, default=1.0, help="Top-p sampling parameter for provider calls")
    parser.add_argument("--seed", type=int, default=None, help="Optional fixed random seed when supported by the provider")
    return parser


def _paths_from_args(repo_root: Path, args: argparse.Namespace) -> BenchmarkPaths:
    return BenchmarkPaths(
        benchmark_scenario="real_bracket_001",
        question_file=repo_root / args.question_file,
        rubric_file=repo_root / args.rubric_file,
        condition_a_path=repo_root / args.condition_a_path,
        condition_b_index_file=repo_root / args.condition_b_index,
        condition_b_source=repo_root / args.condition_b_source,
        results_dir=repo_root / args.results_dir,
        schema_file=repo_root / args.schema_file,
    )


def _provider_config_from_args(args: argparse.Namespace) -> ProviderConfig:
    return ProviderConfig(
        provider=_resolve_env_backed_value(args.provider, "BENCHMARK_PROVIDER") or "",
        model=_resolve_env_backed_value(args.model, "BENCHMARK_MODEL") or "",
        api_key=_resolve_env_backed_value(args.api_key, "BENCHMARK_API_KEY"),
        api_key_env=_resolve_env_backed_value(args.api_key_env, "BENCHMARK_API_KEY_ENV"),
        base_url=_resolve_env_backed_value(args.base_url, "BENCHMARK_BASE_URL"),
        input_price_per_million_tokens=args.input_price_per_million_tokens,
        output_price_per_million_tokens=args.output_price_per_million_tokens,
        max_output_tokens=args.max_output_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        seed=args.seed,
    )


def _prepare_condition_b(repo_root: Path) -> None:
    command = [sys.executable, "scripts/run_real_step_demo.py"]
    completed = subprocess.run(command, cwd=repo_root, text=True)
    if completed.returncode != 0:
        raise SystemExit(f"condition B preparation failed with exit code {completed.returncode}")


def _print_progress(message: str) -> None:
    print(f"[progress] {message}", flush=True)


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = REPO_ROOT / env_file
    _load_dotenv_file(env_file)
    provider_config = _provider_config_from_args(args)
    if not provider_config.provider:
        parser.error("provider is required (pass --provider or set BENCHMARK_PROVIDER in .env)")
    if not provider_config.model:
        parser.error("model is required (pass --model or set BENCHMARK_MODEL in .env)")

    result = run_benchmark(
        paths=_paths_from_args(REPO_ROOT, args),
        config=BenchmarkRunConfig(
            condition=args.condition,
            provider=provider_config,
            dry_run=args.dry_run,
            output_path=Path(args.output) if args.output else None,
        ),
        provider=None,
        prepare_condition_b=(lambda _: _prepare_condition_b(REPO_ROOT)),
        progress=_print_progress,
    )

    if args.dry_run:
        for note in result.get("dry_run_notes", []):
            print("DRY-RUN NOTE:", note)
        print(json.dumps(result, indent=2))
        return 0

    print("Benchmark run complete")
    print("run_id:", result["run_id"])
    print("provider:", result["provider"])
    print("model:", result["model"])
    if "B" in result["conditions"] and "A" in result["conditions"]:
        print("delta_usefulness:", result["totals"]["delta_usefulness"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
