"""inspect_ai Task definitions for the "diagnose broken CAE setup" scenario.

Two tasks, one per condition. Both share the same prompt and target so the
only independent variable across conditions is the evidence-layer access.

- Condition A: the LLM receives the raw concatenated contents of the broken
  package's setup artifacts as text in its prompt. No tools.
- Condition B: the LLM receives only the package path and the AIENG tool
  surface (``aieng_inspect_package``, ``aieng_read_artifact``,
  ``aieng_cae_preprocessing_summary``). Multi-turn agentic execution.

Scoring is deterministic substring matching against rubric.yaml so the smoke
test has zero API dependency and a reliable score.

Run a real eval:

  inspect eval task.py@diagnose_broken_cae_setup_condition_b \\
      --model anthropic/claude-sonnet-4-6 \\
      --epochs 5

Run the harness end-to-end with the built-in mock provider (no API key):

  inspect eval task.py@diagnose_broken_cae_setup_condition_b \\
      --model mockllm/model
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

# Bootstrap sys.path so ``from benchmarks....`` and ``from aieng....`` resolve
# when the inspect CLI loads this file via importlib (which does NOT consult
# pytest's pythonpath). task.py lives four parents below the aieng repo root;
# the aieng package lives under that root's ``src/``.
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
from benchmarks.llm_engineering_usefulness.scenarios.diagnose_broken_cae_setup.build_fixture import (
    build_broken_package,
)


_SCENARIO_DIR = Path(__file__).resolve().parent


_SYSTEM_PROMPT = (
    "You are an engineering assistant inspecting a CAE setup. "
    "Your job is to identify any cross-reference inconsistencies between "
    "setup artifacts that would prevent a solver run from succeeding. "
    "Be specific: name the artifact, the field, and the inconsistency. "
    "If you cannot find a defect, say so plainly. Do not invent defects."
)

_USER_PROMPT_CONDITION_B = (
    "A .aieng package is located at {package_path}.\n\n"
    "Use the available aieng tools to inspect the package and diagnose any "
    "setup defect that would prevent the CalculiX solver from running. "
    "Name the specific artifact path, field, and the inconsistency."
)


def _build_condition_a_input(package_path: Path) -> str:
    """Concatenate every setup artifact as labeled text — Condition A's only input.

    The bulk artifacts (parsed_topology, parsed_features, element_listing,
    extra load cases) are intentionally included. They are not defects; their
    presence forces the model to navigate noise to find the single real
    cross-reference inconsistency. If the dump list excludes them, the
    scenario regresses to the original ceiling-prone small version.
    """
    members_to_dump = [
        "manifest.json",
        "graph/constraints.json",
        "graph/assembly_metadata.json",
        "simulation/cae_imports/parsed_materials.json",
        "simulation/cae_imports/parsed_boundary_conditions.json",
        "simulation/cae_imports/parsed_loads.json",
        "simulation/cae_imports/parsed_topology.json",
        "simulation/cae_imports/parsed_features.json",
        "simulation/mesh/mesh_metadata.json",
        "simulation/mesh/element_listing.json",
        "simulation/solver_settings.json",
        "simulation/load_cases/load_case_001.json",
        "simulation/load_cases/load_case_002.json",
        "simulation/load_cases/load_case_003.json",
    ]
    chunks: list[str] = [
        "A CAE setup is provided as raw artifact contents below. Each "
        "artifact is labeled with its path inside the package. Diagnose any "
        "cross-reference inconsistency that would prevent a CalculiX solver "
        "run. Name the specific artifact path, field, and the inconsistency.\n"
    ]
    with zipfile.ZipFile(package_path, "r") as zf:
        for name in members_to_dump:
            chunks.append(f"\n--- {name} ---\n")
            chunks.append(zf.read(name).decode("utf-8"))
    return "".join(chunks)


def _load_rubric() -> dict[str, Any]:
    return yaml.safe_load((_SCENARIO_DIR / "rubric.yaml").read_text(encoding="utf-8"))


def _extract_total_tokens(state: TaskState) -> int | None:
    """Read cumulative token usage off the TaskState defensively.

    inspect_ai exposes token usage in a few different shapes across versions
    and across single-turn vs multi-turn execution. We try:

    1. ``state.token_usage`` (sum across all model calls in this sample —
       what we actually want for Condition B agentic execution).
    2. ``state.output.usage`` (just the final turn — accurate for
       Condition A which is single-turn).

    Returns the integer total, or ``None`` if neither shape is available
    or the values are not positive.
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
    """Score the run's token cost against the per-scenario budget.

    ``Score.value`` is a numeric efficiency ratio in ``[0.0, 1.0]``:

        1.0 — trial completed at or under budget
        0.5 — trial used roughly twice the budget
        ~0.2 — trial used roughly five times the budget
        0.0 — token usage unavailable from the harness

    This is the second axis of the rubric. The benchmark therefore reports
    correctness *and* cost-efficiency as orthogonal measurements rather
    than collapsing both into one verdict. A scenario where Condition A
    and Condition B both score "C" but B costs 6× more is a finding the
    benchmark must surface — that is what this scorer is for.
    """
    rubric = _load_rubric()
    budget = int(rubric.get("efficiency", {}).get("token_budget", 2000))

    async def score(state: TaskState, target: Target) -> Score:
        total = _extract_total_tokens(state)
        if total is None:
            return Score(
                value=0.0,
                explanation="token usage unavailable from TaskState",
            )
        ratio = min(1.0, budget / total)
        return Score(
            value=ratio,
            explanation=f"used={total} budget={budget} ratio={ratio:.3f}",
        )

    return score


@scorer(metrics=[accuracy()])
def diagnose_rubric_scorer() -> Scorer:
    """Deterministic substring scorer driven by rubric.yaml.

    Returns ``Score.value`` in {"C", "P", "I"}:
        C — correct: total weighted hits >= 0.6 and no hallucination penalties
        P — partial: 0.3 <= total < 0.6, or >= 0.6 with penalties applied
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
        triggered_penalties: list[str] = []
        for p in penalties:
            if p["pattern"].lower() in text:
                penalty_total += float(p.get("penalty", 0))
                triggered_penalties.append(p["pattern"])

        adjusted = total - penalty_total
        if adjusted >= 0.6 and not triggered_penalties:
            verdict = "C"
        elif adjusted >= 0.3 or (total >= 0.6 and triggered_penalties):
            verdict = "P"
        else:
            verdict = "I"

        explanation = (
            f"hits={hits} score={total:.2f} penalty={penalty_total:.2f} "
            f"adjusted={adjusted:.2f} triggered={triggered_penalties}"
        )
        return Score(value=verdict, answer=completion, explanation=explanation)

    return score


def _build_dataset_condition_a(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_build_condition_a_input(package_path),
            target="Aluminum6061 is referenced by load_case_001 but not defined in parsed_materials",
            id="diagnose_broken_cae_setup",
            metadata={"condition": "A", "scenario": "diagnose_broken_cae_setup"},
        )
    ]


def _build_dataset_condition_b(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_USER_PROMPT_CONDITION_B.format(package_path=str(package_path)),
            target="Aluminum6061 is referenced by load_case_001 but not defined in parsed_materials",
            id="diagnose_broken_cae_setup",
            metadata={
                "condition": "B",
                "scenario": "diagnose_broken_cae_setup",
                "package_path": str(package_path),
            },
        )
    ]


def _ensure_fixture(fixture_path: str | None = None) -> Path:
    """Build the broken .aieng fixture, always rebuilding from primitives.

    Always rebuilds, not only when missing. The canonical artifact list lives
    in ``build_fixture.py``, and a stale on-disk fixture from a previous
    version of this scenario would silently feed wrong inputs to the eval
    (we hit this once: an earlier run wrote an 8-artifact fixture, the
    scaled scenario expected the 14-artifact form, and Condition A's raw
    dump raised KeyError on the missing entry). Build cost is sub-second;
    the safety is worth the negligible overhead.
    """
    if fixture_path:
        path = Path(fixture_path)
    else:
        path = _SCENARIO_DIR / "fixture.aieng"
    return build_broken_package(path)


@task
def diagnose_broken_cae_setup_condition_a(fixture_path: str | None = None) -> Task:
    """Condition A — raw artifact dump, no tools."""
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_build_dataset_condition_a(package_path),
        solver=[system_message(_SYSTEM_PROMPT), generate()],
        scorer=[diagnose_rubric_scorer(), token_efficiency_scorer()],
    )


@task
def diagnose_broken_cae_setup_condition_b(fixture_path: str | None = None) -> Task:
    """Condition B — package handle + AIENG tools, multi-turn agentic execution."""
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_build_dataset_condition_b(package_path),
        solver=[
            system_message(_SYSTEM_PROMPT),
            use_tools(*AIENG_TOOLS),
            generate(),
        ],
        scorer=[diagnose_rubric_scorer(), token_efficiency_scorer()],
    )
