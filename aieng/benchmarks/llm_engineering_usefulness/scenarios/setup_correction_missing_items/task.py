"""inspect_ai Task definitions for the "setup_correction_missing_items" scenario.

The model is asked to itemise what is missing or inconsistent in a CAE
setup and propose an additive correction plan. The scenario is the
clearest favourable case for `.aieng` access:

  - Condition B can call ``aieng_cae_preprocessing_summary`` and read
    ``missing_items`` + ``ready_for_solver`` directly.
  - Condition A must infer the same gaps from the *absence* of artifacts
    in the dumped contents (no positive signal — the model is reading
    negative space).

The scenario therefore tests whether structured tool access materially
helps for a question where the answer is most easily expressed as
"what is NOT in the package".

Run a real eval:

  inspect eval task.py@setup_correction_missing_items_condition_b \\
      --model anthropic/kimi-for-coding --epochs 10 --temperature 0

Mock smoke:

  inspect eval task.py@setup_correction_missing_items_condition_a \\
      --model mockllm/model
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

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
from benchmarks.llm_engineering_usefulness.scenarios.setup_correction_missing_items.build_fixture import (
    build_setup_correction_package,
)


_SCENARIO_DIR = Path(__file__).resolve().parent


_PROMPT_TASK = """\
Audit this CAE setup. The package contains a load case that someone
wants to solve.

Specifically answer:

1. What is missing or inconsistent in the setup? Be exhaustive — list
   every gap you can find with reference to the affected artifact path.
2. What is the minimum additive plan to make the setup runnable?
3. State plainly whether the package, as-is, is ready for the solver.
"""

_SYSTEM_PROMPT = (
    "You are an engineering assistant auditing a CAE setup. Your job is "
    "to identify missing or inconsistent setup items and propose an "
    "additive correction plan. Reason from artifact presence/absence and "
    "from cross-references between artifacts. Do not declare the setup "
    "ready unless every required artifact is present and every reference "
    "resolves."
)


_USER_PROMPT_CONDITION_B = (
    "A .aieng package is located at {package_path}.\n\n"
    "Use the available aieng tools to audit it, then answer the task "
    "below.\n\n{task}"
)


def _build_condition_a_input(package_path: Path) -> str:
    """Dump every member that is actually present in the fixture.

    We discover the members at runtime so the absence of
    parsed_loads.json and solver_settings.json is naturally visible
    (Condition A sees the manifest's resources list and the actual
    contents, but no entry for the missing artifacts).
    """
    chunks: list[str] = [
        "A CAE setup package is provided as raw artifact contents below. "
        "Each artifact present in the package is labeled with its path. "
        "If you do not see an artifact path in the dump, the artifact is "
        "not present in the package.\n",
    ]
    with zipfile.ZipFile(package_path, "r") as zf:
        for name in sorted(zf.namelist()):
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
    budget = int(rubric.get("efficiency", {}).get("token_budget", 3000))

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


_NEGATION_RE = re.compile(
    r"\b(not|no|never|don'?t|doesn'?t|isn'?t|aren'?t|wasn'?t|weren'?t|"
    r"can'?t|cannot|won'?t|wouldn'?t|shouldn'?t|couldn'?t|didn'?t|"
    r"hasn'?t|haven'?t|hadn'?t)\b"
)


def _penalty_triggered(text: str, pattern: str) -> bool:
    """Return True if *any* occurrence of ``pattern`` in ``text`` lacks
    negation in the preceding window and is not explicitly falsified.
    """
    pattern_lower = pattern.lower()
    start = 0
    while True:
        idx = text.find(pattern_lower, start)
        if idx == -1:
            break

        window_start = max(0, idx - 40)
        window = text[window_start:idx]
        negated = _NEGATION_RE.search(window) is not None

        # Special case: "ready for solver" followed by ": false" is negated.
        if not negated and pattern_lower == "ready for solver":
            after = text[idx + len(pattern_lower) : idx + len(pattern_lower) + 12]
            if ": false" in after or ":false" in after:
                negated = True

        if not negated:
            return True

        start = idx + 1

    return False


@scorer(metrics=[accuracy()])
def setup_correction_rubric_scorer() -> Scorer:
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
            if _penalty_triggered(text, p["pattern"]):
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
    return build_setup_correction_package(path)


def _dataset_condition_a(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_build_condition_a_input(package_path),
            target="loads missing; solver_settings missing; load_case_001 references undefined load_lateral",
            id="setup_correction_missing_items",
            metadata={"condition": "A", "scenario": "setup_correction_missing_items"},
        )
    ]


def _dataset_condition_b(package_path: Path) -> list[Sample]:
    return [
        Sample(
            input=_USER_PROMPT_CONDITION_B.format(
                package_path=str(package_path),
                task=_PROMPT_TASK,
            ),
            target="loads missing; solver_settings missing; load_case_001 references undefined load_lateral",
            id="setup_correction_missing_items",
            metadata={
                "condition": "B",
                "scenario": "setup_correction_missing_items",
                "package_path": str(package_path),
            },
        )
    ]


@task
def setup_correction_missing_items_condition_a(fixture_path: str | None = None) -> Task:
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_dataset_condition_a(package_path),
        solver=[system_message(_SYSTEM_PROMPT), generate()],
        scorer=[setup_correction_rubric_scorer(), token_efficiency_scorer()],
    )


@task
def setup_correction_missing_items_condition_b(fixture_path: str | None = None) -> Task:
    package_path = _ensure_fixture(fixture_path)
    return Task(
        dataset=_dataset_condition_b(package_path),
        solver=[
            system_message(_SYSTEM_PROMPT),
            use_tools(*AIENG_TOOLS),
            generate(),
        ],
        scorer=[setup_correction_rubric_scorer(), token_efficiency_scorer()],
    )
