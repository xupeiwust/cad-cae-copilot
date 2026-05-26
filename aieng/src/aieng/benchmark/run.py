"""Canonical Phase 30 benchmark CLI.

Usage:
  python -m aieng.benchmark.run --condition B --scenario mass_reduction --trials 5
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


TaskFactory = Callable[[], Any]


def _scenario_registry() -> dict[str, dict[str, str]]:
    return {
        "diagnose_broken_cae_setup": {
            "A": "benchmarks.llm_engineering_usefulness.scenarios.diagnose_broken_cae_setup.task:diagnose_broken_cae_setup_condition_a",
            "B": "benchmarks.llm_engineering_usefulness.scenarios.diagnose_broken_cae_setup.task:diagnose_broken_cae_setup_condition_b",
        },
        "mass_reduction": {
            "A": "benchmarks.llm_engineering_usefulness.scenarios.mass_reduction_recommendation.task:mass_reduction_recommendation_condition_a",
            "B": "benchmarks.llm_engineering_usefulness.scenarios.mass_reduction_recommendation.task:mass_reduction_recommendation_condition_b",
        },
        "mass_reduction_recommendation": {
            "A": "benchmarks.llm_engineering_usefulness.scenarios.mass_reduction_recommendation.task:mass_reduction_recommendation_condition_a",
            "B": "benchmarks.llm_engineering_usefulness.scenarios.mass_reduction_recommendation.task:mass_reduction_recommendation_condition_b",
        },
        "stress_concentrator": {
            "A": "benchmarks.llm_engineering_usefulness.scenarios.stress_concentrator_recommendation.task:stress_concentrator_recommendation_condition_a",
            "B": "benchmarks.llm_engineering_usefulness.scenarios.stress_concentrator_recommendation.task:stress_concentrator_recommendation_condition_b",
        },
        "stress_concentrator_recommendation": {
            "A": "benchmarks.llm_engineering_usefulness.scenarios.stress_concentrator_recommendation.task:stress_concentrator_recommendation_condition_a",
            "B": "benchmarks.llm_engineering_usefulness.scenarios.stress_concentrator_recommendation.task:stress_concentrator_recommendation_condition_b",
        },
        "setup_correction_missing_items": {
            "A": "benchmarks.llm_engineering_usefulness.scenarios.setup_correction_missing_items.task:setup_correction_missing_items_condition_a",
            "B": "benchmarks.llm_engineering_usefulness.scenarios.setup_correction_missing_items.task:setup_correction_missing_items_condition_b",
        },
    }


def _load_factory(ref: str) -> TaskFactory:
    module_name, func_name = ref.split(":", 1)
    module = __import__(module_name, fromlist=[func_name])
    return getattr(module, func_name)


def _score_value_to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value == "C":
        return 1.0
    if value == "P":
        return 0.5
    if value == "I":
        return 0.0
    return None


def _mean_ci95(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "ci95_low": None, "ci95_high": None}
    mean = sum(values) / len(values)
    if len(values) == 1:
        return {"mean": mean, "ci95_low": mean, "ci95_high": mean}
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    half_width = 1.96 * math.sqrt(variance / len(values))
    return {"mean": mean, "ci95_low": mean - half_width, "ci95_high": mean + half_width}


def _extract_scores(logs: list[Any]) -> dict[str, Any]:
    by_scorer: dict[str, list[float]] = {}
    verdicts: dict[str, dict[str, int]] = {}
    samples_seen = 0
    for log in logs:
        for sample in getattr(log, "samples", None) or []:
            samples_seen += 1
            scores = getattr(sample, "scores", None) or {}
            for scorer_name, score in scores.items():
                value = getattr(score, "value", None)
                numeric = _score_value_to_float(value)
                if numeric is not None:
                    by_scorer.setdefault(scorer_name, []).append(numeric)
                if isinstance(value, str):
                    verdicts.setdefault(scorer_name, {})
                    verdicts[scorer_name][value] = verdicts[scorer_name].get(value, 0) + 1
    return {
        "sample_count": samples_seen,
        "scores": {name: _mean_ci95(values) for name, values in by_scorer.items()},
        "verdict_counts": verdicts,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run calibrated AIENG LLM usefulness benchmark scenarios")
    parser.add_argument("--condition", choices=["A", "B"], required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--model", default="mockllm/model")
    parser.add_argument("--out", help="Optional JSON output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = _scenario_registry()
    if args.scenario not in registry:
        print(f"FAIL unknown scenario: {args.scenario}", file=sys.stderr)
        print(f"Known scenarios: {', '.join(sorted(registry))}", file=sys.stderr)
        return 2

    try:
        from inspect_ai import eval as inspect_eval
    except ImportError:
        print("FAIL inspect_ai is not installed; install with pip install -e '.[benchmark]'", file=sys.stderr)
        return 2

    factory = _load_factory(registry[args.scenario][args.condition])
    task = factory()
    logs = inspect_eval(task, model=args.model, epochs=args.trials, display="none")
    result = {
        "run_id": datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ"),
        "scenario": args.scenario,
        "condition": args.condition,
        "model": args.model,
        "trials": args.trials,
        "summary": _extract_scores(logs),
        "honesty_note": "Scenario-specific benchmark result only; no general AIENG utility claim is implied.",
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
