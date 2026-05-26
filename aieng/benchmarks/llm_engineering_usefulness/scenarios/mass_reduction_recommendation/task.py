"""inspect_ai Task definitions for the "mass_reduction_recommendation" scenario.

Different task shape from scenario 1: instead of spotting a cross-reference
defect, the model must read per-feature stress data and pick the safest of
four mass-reduction proposals. The decision requires multi-step reasoning
(read stresses, compare to yield, verify margins).

The fixture is engineered so the correct answer (A — thin the back_wall) is
unambiguous; deterministic substring scoring is therefore sufficient.

Run a real eval:

  inspect eval task.py@mass_reduction_recommendation_condition_b \\
      --model anthropic/kimi-for-coding --epochs 5

Run the harness against the mock provider (no API key):

  inspect eval task.py@mass_reduction_recommendation_condition_a \\
      --model mockllm/model
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

# sys.path bootstrap — same pattern as scenario 1's task.py; needed so the
# inspect CLI can import benchmarks.* and aieng.* without consulting pytest's
# pythonpath.
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
from benchmarks.llm_engineering_usefulness.scenarios.mass_reduction_recommendation.build_fixture import (
    build_recommendation_package,
)


_SCENARIO_DIR = Path(__file__).resolve().parent


_PROPOSALS = """\
Four proposed mass-reduction changes are under review:

  A) Thin the `back_wall` feature from 20 mm thickness to 10 mm.
  B) Remove the `central_rib` feature entirely.
  C) Enlarge the `mounting_hole` feature from 10 mm diameter to 15 mm.
  D) Reduce `mounting_bosses` count from 4 to 2.

You must choose exactly one. The numeric design requirements (mass-reduction
floor and minimum safety factor) are documented in `task/design_targets.yaml`
inside the package; read that resource for the acceptance criteria rather
than relying on guesses.

End your response with the literal line:

  Answer: <letter>

where <letter> is A, B, C, or D.
"""


_SYSTEM_PROMPT = (
    "You are a structural engineering assistant evaluating proposed "
    "design changes against a computed CAE result set. Your job is to "
    "recommend the change that most safely reduces mass while maintaining "
    "the stated safety factor. Reason from the stress data provided; do "
    "not invent values. Always end your response with a final answer line."
)


_USER_PROMPT_CONDITION_B = (
    "A .aieng package containing geometry, materials, mesh, the load case, "
    "computed metrics, per-feature stress data, and the acceptance criteria "
    "in `task/design_targets.yaml` is located at {package_path}.\n\n"
    "Use the available aieng tools to inspect the package (including the "
    "design targets), then choose the proposal that satisfies every "
    "acceptance criterion.\n\n"
    "{proposals}"
)


def _build_condition_a_input(package_path: Path) -> str:
    """Concatenate every relevant artifact as labeled text — Condition A's only input.

    Includes ``task/design_targets.yaml`` so Condition A receives the same
    numeric design requirements (mass-reduction floor, minimum safety factor)
    that Condition B can read via structured tools. Without this entry the
    A/B comparison would be unfair: B's tools would expose targets that A
    cannot see.
    """
    members_to_dump = [
        "manifest.json",
        "task/design_targets.yaml",
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
        "Each artifact is labeled with its path inside the package. The "
        "acceptance criteria for this task live in `task/design_targets.yaml`; "
        "read those first, then use the per-feature stress data to choose "
        "the safest proposed mass-reduction change.\n",
    ]
    with zipfile.ZipFile(package_path, "r") as zf:
        for name in members_to_dump:
            chunks.append(f"\n--- {name} ---\n")
            chunks.append(zf.read(name).decode("utf-8"))
    chunks.append("\n\n")
    chunks.append(_PROPOSALS)
    return "".join(chunks)


def _load_rubric() -> dict[str, Any]:
    return yaml.safe_load((_SCENARIO_DIR / "rubric.yaml").read_text(encoding="utf-8"))


def _extract_total_tokens(state: TaskState) -> int | None:
    """Read cumulative token usage off the TaskState defensively.

    Same defensive shape as scenario 1's task.py — see comment there for
    why we try state.token_usage first then state.output.usage.
    """
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
    """Token-efficiency scorer; same shape as scenario 1."""
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
def recommendation_rubric_scorer() -> Scorer:
    """Deterministic substring scorer for the mass-reduction recommendation.

    Returns ``Score.value`` in {"C", "P", "I"}:
        C — correct: total >= 0.6 AND no hallucination penalties
        P — partial: 0.3 <= total < 0.6, OR >= 0.6 with penalties applied
        I — incorrect: total < 0.3
    """
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
    """Always rebuild the fixture — same rationale as scenario 1."""
    if fixture_path:
        path = Path(fixture_path)
    else:
        path = _SCENARIO_DIR / "fixture.aieng"
    return build_recommendation_package(path)


def _dataset_condition_a(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_build_condition_a_input(package_path),
            target="A: thin back_wall (lowest stress, deepest safety margin)",
            id="mass_reduction_recommendation",
            metadata={"condition": "A", "scenario": "mass_reduction_recommendation"},
        )
    ]


def _dataset_condition_b(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_USER_PROMPT_CONDITION_B.format(
                package_path=str(package_path),
                proposals=_PROPOSALS,
            ),
            target="A: thin back_wall (lowest stress, deepest safety margin)",
            id="mass_reduction_recommendation",
            metadata={
                "condition": "B",
                "scenario": "mass_reduction_recommendation",
                "package_path": str(package_path),
            },
        )
    ]


@task
def mass_reduction_recommendation_condition_a(fixture_path: str | None = None) -> Task:
    """Condition A — raw artifact dump, no tools."""
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_dataset_condition_a(package_path),
        solver=[system_message(_SYSTEM_PROMPT), generate()],
        scorer=[recommendation_rubric_scorer(), token_efficiency_scorer()],
    )


@task
def mass_reduction_recommendation_condition_b(fixture_path: str | None = None) -> Task:
    """Condition B — package handle + AIENG tools, multi-turn agentic execution."""
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_dataset_condition_b(package_path),
        solver=[
            system_message(_SYSTEM_PROMPT),
            use_tools(*AIENG_TOOLS),
            generate(),
        ],
        scorer=[recommendation_rubric_scorer(), token_efficiency_scorer()],
    )
