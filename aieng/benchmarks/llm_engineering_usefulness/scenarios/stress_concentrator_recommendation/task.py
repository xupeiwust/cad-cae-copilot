"""inspect_ai Task definitions for the "stress_concentrator_recommendation" scenario.

Different task shape from scenarios 1 and 2: an *open-ended* engineering
recommendation. The model must (a) identify the high-stress feature,
(b) propose a reasonable response, and (c) not overstate certainty.

The fixture is engineered so the diagnosis is unambiguous (a single
feature is below the declared SF floor); the *recommendation* is
intentionally underspecified so the rubric can also reward acknowledged
uncertainty.

Run a real eval:

  inspect eval task.py@stress_concentrator_recommendation_condition_b \\
      --model anthropic/kimi-for-coding --epochs 10 --temperature 0

Mock-only smoke:

  inspect eval task.py@stress_concentrator_recommendation_condition_a \\
      --model mockllm/model
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

# sys.path bootstrap — same pattern as the other scenario task.py files.
_AIENG_ROOT = Path(__file__).resolve().parents[4]
for _candidate in (_AIENG_ROOT, _AIENG_ROOT / "src"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Scorer, Target, accuracy, mean, scorer
from inspect_ai.solver import TaskState, generate, system_message, use_tools

from benchmarks.llm_engineering_usefulness.tools import AIENG_TOOLS
from benchmarks.llm_engineering_usefulness.scenarios.stress_concentrator_recommendation.build_fixture import (
    build_concentrator_package,
)


_SCENARIO_DIR = Path(__file__).resolve().parent


_PROMPT_TASK = """\
The load case `load_case_001` has been solved against this package. The
declared minimum safety factor is 1.5. Inspect the result data and answer:

1. Which feature (if any) is the stress concentrator that violates the
   safety-factor constraint? Identify it by name.
2. What design change do you recommend to address it?
3. Briefly explain what would need to happen to confirm that your
   recommendation actually achieves the constraint.

Be specific. Cite stress values or safety factors from the package when
you reason. Do not claim that your proposal *will* solve the problem —
re-analysis is required to verify.
"""

_SYSTEM_PROMPT = (
    "You are a structural engineering assistant reviewing a solved CAE "
    "result against a declared safety-factor constraint. Your job is to "
    "identify any stress concentrator that violates the constraint and to "
    "propose a reasonable design response. Reason from the data; do not "
    "invent values; do not claim a fix is guaranteed without re-analysis."
)


_USER_PROMPT_CONDITION_B = (
    "A solved .aieng package is located at {package_path}.\n\n"
    "Use the available aieng tools to inspect the result data, then answer "
    "the task below.\n\n{task}"
)


def _build_condition_a_input(package_path: Path) -> str:
    members_to_dump = [
        "manifest.json",
        "graph/constraints.json",
        "simulation/cae_imports/parsed_materials.json",
        "simulation/cae_imports/parsed_boundary_conditions.json",
        "simulation/cae_imports/parsed_loads.json",
        "simulation/cae_imports/parsed_topology.json",
        "simulation/cae_imports/parsed_features.json",
        "simulation/mesh/mesh_metadata.json",
        "simulation/mesh/element_listing.json",
        "simulation/solver_settings.json",
        "simulation/load_cases/load_case_001.json",
        "results/computed_metrics.json",
        "results/stress_by_feature.json",
    ]
    chunks: list[str] = [
        "A solved CAE package is provided as raw artifact contents below. "
        "Each artifact is labeled with its path inside the package.\n",
    ]
    with zipfile.ZipFile(package_path, "r") as zf:
        for name in members_to_dump:
            chunks.append(f"\n--- {name} ---\n")
            chunks.append(zf.read(name).decode("utf-8"))
    chunks.append("\n\n")
    chunks.append(_PROMPT_TASK)
    return "".join(chunks)


def _load_rubric() -> dict[str, Any]:
    return yaml.safe_load((_SCENARIO_DIR / "rubric.yaml").read_text(encoding="utf-8"))


def _extract_total_tokens(state: TaskState) -> int | None:
    candidates: list[Any] = []
    state_usage = getattr(state, "token_usage", None)
    if state_usage is not None:
        candidates.append(state_usage)
    output = getattr(state, "output", None)
    if output is not None:
        output_usage = getattr(output, "usage", None)
        if output_usage is not None:
            candidates.append(output_usage)
    for usage in candidates:
        total = getattr(usage, "total_tokens", None)
        if isinstance(total, int) and total > 0:
            return total
        input_t = getattr(usage, "input_tokens", None) or 0
        output_t = getattr(usage, "output_tokens", None) or 0
        if input_t + output_t > 0:
            return int(input_t + output_t)
    return None


@scorer(metrics=[mean()])
def token_efficiency_scorer() -> Scorer:
    rubric = _load_rubric()
    budget = int(rubric.get("efficiency", {}).get("token_budget", 4000))

    async def score(state: TaskState, target: Target) -> Score:
        total = _extract_total_tokens(state)
        if total is None:
            return Score(value=0.0, explanation="token usage unavailable from TaskState")
        ratio = min(1.0, budget / total)
        return Score(
            value=ratio,
            explanation=f"used={total} budget={budget} ratio={ratio:.3f}",
        )

    return score


@scorer(metrics=[accuracy()])
def concentrator_rubric_scorer() -> Scorer:
    rubric = _load_rubric()
    criteria = rubric.get("criteria", [])
    penalties = rubric.get("hallucination_penalties", [])

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion or ""
        text = completion.lower()

        total = 0.0
        hits: list[str] = []
        for crit in criteria:
            for pattern in crit.get("patterns", []):
                if pattern.lower() in text:
                    total += float(crit.get("weight", 0))
                    hits.append(crit["id"])
                    break

        penalty_total = 0.0
        triggered: list[str] = []
        for p in penalties:
            if p["pattern"].lower() in text:
                penalty_total += float(p.get("penalty", 0))
                triggered.append(p["pattern"])

        adjusted = total - penalty_total
        if adjusted >= 0.6 and not triggered:
            verdict = "C"
        elif adjusted >= 0.3 or (total >= 0.6 and triggered):
            verdict = "P"
        else:
            verdict = "I"

        return Score(
            value=verdict,
            answer=completion,
            explanation=(
                f"hits={hits} score={total:.2f} penalty={penalty_total:.2f} "
                f"adjusted={adjusted:.2f} triggered={triggered}"
            ),
        )

    return score


def _ensure_fixture(fixture_path: str | None = None) -> Path:
    if fixture_path:
        path = Path(fixture_path)
    else:
        path = _SCENARIO_DIR / "fixture.aieng"
    return build_concentrator_package(path)


def _dataset_condition_a(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_build_condition_a_input(package_path),
            target="fillet_inner_corner SF 1.25; recommend increasing fillet radius; re-analysis required",
            id="stress_concentrator_recommendation",
            metadata={"condition": "A", "scenario": "stress_concentrator_recommendation"},
        )
    ]


def _dataset_condition_b(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_USER_PROMPT_CONDITION_B.format(
                package_path=str(package_path),
                task=_PROMPT_TASK,
            ),
            target="fillet_inner_corner SF 1.25; recommend increasing fillet radius; re-analysis required",
            id="stress_concentrator_recommendation",
            metadata={
                "condition": "B",
                "scenario": "stress_concentrator_recommendation",
                "package_path": str(package_path),
            },
        )
    ]


@task
def stress_concentrator_recommendation_condition_a(fixture_path: str | None = None) -> Task:
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_dataset_condition_a(package_path),
        solver=[system_message(_SYSTEM_PROMPT), generate()],
        scorer=[concentrator_rubric_scorer(), token_efficiency_scorer()],
    )


@task
def stress_concentrator_recommendation_condition_b(fixture_path: str | None = None) -> Task:
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_dataset_condition_b(package_path),
        solver=[
            system_message(_SYSTEM_PROMPT),
            use_tools(*AIENG_TOOLS),
            generate(),
        ],
        scorer=[concentrator_rubric_scorer(), token_efficiency_scorer()],
    )
