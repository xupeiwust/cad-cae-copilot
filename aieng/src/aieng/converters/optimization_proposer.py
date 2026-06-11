"""Deterministic local-refinement proposer for the iterative loop (#62).

Phase 1 generates the *initial* design (grid/random/LHS). Phase 2 needs to
propose the *next* batch from previous results. This module supports two
strategies under the same ``propose_next_candidates`` entry:

- **trust_region** — sample around the current incumbent within a radius that
  shrinks each iteration. Best for continuous/integer variables.
- **genetic** — population-based evolutionary search with selection, crossover,
  and mutation, seeded from the incumbent. Designed for mixed spaces with
  discrete/categorical variables; also works for purely continuous/integer
  spaces when requested explicitly.

When there is no feasible incumbent, the proposer falls back to whole-domain
Latin hypercube sampling (reusing ``optimization_sampler``) and records the
fallback.

Deterministic given a seed. Baseline is never modified.
"""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from random import Random
from typing import Any

from aieng.converters.optimization_sampler import (
    SAMPLE_CANDIDATES_DIR,
    _denormalise_variable_value,
    _filter_safe_variables,
    _normalise_variable_value,
    latin_hypercube_sample,
)

DESIGN_STUDY_CANDIDATE_RANKING_PATH = "analysis/design_study_candidate_ranking.json"
OPTIMIZATION_VARIABLES_PATH = "analysis/optimization_variables.json"
OPTIMIZATION_ITERATIONS_PATH = "analysis/optimization_iterations.json"
DESIGN_CANDIDATES_DIR = SAMPLE_CANDIDATES_DIR  # "patches/design_candidates/"

_BOUNDED_TYPES = {"continuous", "integer"}
_DISCRETE_TYPES = {"discrete", "categorical"}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_json(zf: zipfile.ZipFile, name: str, names: set[str]) -> Any:
    if name in names:
        try:
            return json.loads(zf.read(name))
        except Exception:  # noqa: BLE001
            return None
    return None


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def _replace_members(package_path: Path, members: dict[str, bytes]) -> None:
    tmp = package_path.with_suffix(".optprop.tmp.aieng")
    try:
        with (
            zipfile.ZipFile(package_path, "r") as src,
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
        ):
            for item in src.infolist():
                if item.filename not in members:
                    dst.writestr(item, src.read(item.filename))
            for name, data in members.items():
                dst.writestr(name, data)
        tmp.replace(package_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _incumbent_variable_values(
    zf: zipfile.ZipFile, names: set[str], incumbent_id: str | None,
) -> dict[str, Any]:
    """Read the incumbent candidate's {variable_id: value} from its patch."""
    if not incumbent_id:
        return {}
    patch = _read_json(zf, f"{DESIGN_CANDIDATES_DIR}{incumbent_id}.json", names)
    values: dict[str, Any] = {}
    if isinstance(patch, dict):
        for ch in patch.get("variable_changes") or []:
            if isinstance(ch, dict) and ch.get("variable_id") is not None:
                values[ch["variable_id"]] = ch.get("new_value")
    return values


def _refine_value(var: dict[str, Any], center: float | None, radius_frac: float,
                  rng: Random) -> Any:
    """Sample one value in a shrunk window around ``center``, clamped to bounds."""
    lo = _num(var.get("min_value"))
    hi = _num(var.get("max_value"))
    vtype = var.get("type", "continuous")
    if lo is None or hi is None or hi <= lo:
        # unbounded/degenerate — keep center (or midpoint) without inventing a range
        return center if center is not None else lo
    if center is None:
        center = (lo + hi) / 2.0
    half = radius_frac * (hi - lo) / 2.0
    win_lo = max(lo, center - half)
    win_hi = min(hi, center + half)
    raw = rng.uniform(win_lo, win_hi)
    if vtype == "integer":
        return int(round(raw))
    return round(raw, 6)


# ── genetic algorithm proposer ───────────────────────────────────────────────


def _has_discrete_variables(safe_vars: list[dict[str, Any]]) -> bool:
    return any(var.get("type") in _DISCRETE_TYPES for var in safe_vars)


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _encode_incumbent(safe_vars: list[dict[str, Any]],
                      incumbent_values: dict[str, Any]) -> list[float] | None:
    """Encode the incumbent into the normalised genome space, if available."""
    if not incumbent_values:
        return None
    genome: list[float] = []
    for var in safe_vars:
        frac = _normalise_variable_value(var, incumbent_values.get(var["id"]))
        genome.append(frac)
    return genome


def _decode_genome(safe_vars: list[dict[str, Any]], genome: list[float]) -> list[dict[str, Any]]:
    """Decode a normalised genome into typed variable changes."""
    return [
        {
            "variable_id": var["id"],
            "new_value": _denormalise_variable_value(var, frac),
        }
        for var, frac in zip(safe_vars, genome)
    ]


def _tournament_select(population: list[list[float]], fitness: list[float],
                       rng: Random, *, tournament_size: int = 3) -> list[float]:
    best = rng.randrange(len(population))
    for _ in range(tournament_size - 1):
        contender = rng.randrange(len(population))
        if fitness[contender] > fitness[best]:
            best = contender
    return population[best][:]


def _uniform_crossover(parent_a: list[float], parent_b: list[float],
                       rng: Random) -> tuple[list[float], list[float]]:
    child_a: list[float] = []
    child_b: list[float] = []
    for a, b in zip(parent_a, parent_b):
        if rng.random() < 0.5:
            child_a.append(a)
            child_b.append(b)
        else:
            child_a.append(b)
            child_b.append(a)
    return child_a, child_b


def _mutate(genome: list[float], rng: Random, rate: float) -> None:
    for i in range(len(genome)):
        if rng.random() < rate:
            genome[i] = rng.random()


def _genetic_fitness(
    population: list[list[float]],
    incumbent_genome: list[float] | None,
    radius_frac: float,
) -> list[float]:
    """Fitness combining population diversity and incumbent proximity.

    Higher fitness = better. Diversity is the mean Euclidean distance to every
    other individual. Proximity rewards individuals inside the current trust
    region around the incumbent. When no incumbent is available, diversity is
    the only objective, so the algorithm still explores the whole domain.
    """
    n = len(population)
    if n <= 1:
        return [1.0] * n

    max_dist = math.sqrt(len(population[0]))
    radius = radius_frac * max_dist
    scores: list[float] = []
    for i, individual in enumerate(population):
        diversity = sum(
            _distance(individual, population[j]) for j in range(n) if j != i
        ) / (n - 1)
        if incumbent_genome is None:
            scores.append(diversity)
            continue
        dist_to_inc = _distance(individual, incumbent_genome)
        proximity_bonus = (
            max(0.0, radius - dist_to_inc) / max(radius, 1e-9)
            if radius > 0
            else 0.0
        )
        scores.append(diversity + 0.5 * proximity_bonus)
    return scores


def _genetic_propose(
    safe_vars: list[dict[str, Any]],
    *,
    count: int,
    seed: int,
    incumbent_values: dict[str, Any],
    iteration: int,
    shrink: float,
    crossover_rate: float = 0.8,
    mutation_rate: float = 0.15,
) -> tuple[list[dict[str, Any]], float]:
    """Generate ``count`` candidate patches via genetic algorithm.

    The incumbent is seeded into the initial population. Evolution uses
    tournament selection, uniform crossover, and per-gene mutation in
    normalised gene space. The radius fraction (``shrink ** iteration``)
    biases the search toward the incumbent as iterations progress.
    """
    rng = Random(seed)
    n_vars = len(safe_vars)
    incumbent_genome = _encode_incumbent(safe_vars, incumbent_values)
    radius_frac = float(shrink) ** max(0, iteration)

    pop_size = max(count * 2, 4)
    population: list[list[float]] = []
    if incumbent_genome is not None:
        population.append(incumbent_genome[:])
    while len(population) < pop_size:
        population.append([rng.random() for _ in range(n_vars)])

    generations = max(1, count)
    elitism = max(1, pop_size // 10)
    for _ in range(generations):
        fitness = _genetic_fitness(population, incumbent_genome, radius_frac)
        ranked = sorted(range(pop_size), key=lambda i: fitness[i], reverse=True)
        new_population: list[list[float]] = [
            population[i][:] for i in ranked[:elitism]
        ]
        while len(new_population) < pop_size:
            parent_a = _tournament_select(population, fitness, rng)
            parent_b = _tournament_select(population, fitness, rng)
            if rng.random() < crossover_rate:
                child_a, child_b = _uniform_crossover(parent_a, parent_b, rng)
            else:
                child_a, child_b = parent_a[:], parent_b[:]
            _mutate(child_a, rng, mutation_rate)
            _mutate(child_b, rng, mutation_rate)
            new_population.append(child_a)
            if len(new_population) < pop_size:
                new_population.append(child_b)
        population = new_population

    final_fitness = _genetic_fitness(population, incumbent_genome, radius_frac)
    ranked = sorted(range(pop_size), key=lambda i: final_fitness[i], reverse=True)

    candidates: list[dict[str, Any]] = []
    for idx, rank in enumerate(ranked[:count]):
        genome = population[rank]
        changes = _decode_genome(safe_vars, genome)
        candidates.append({
            "format": "aieng.design_candidate_patch",
            "candidate_id": f"cand_genetic_{iteration + 1}_{idx:03d}",
            "variable_changes": changes,
            "reasoning": (
                f"Genetic algorithm proposer (iteration {iteration + 1}, "
                f"radius {radius_frac:.3f})."
            ),
        })
    return candidates, radius_frac


def _trust_region_propose(
    safe_vars: list[dict[str, Any]],
    *,
    count: int,
    seed: int,
    incumbent_values: dict[str, Any],
    incumbent_id: str,
    iteration: int,
    shrink: float,
) -> tuple[list[dict[str, Any]], float]:
    """Generate ``count`` candidate patches via trust-region local refinement."""
    radius_frac = float(shrink) ** max(0, iteration)
    rng = Random(seed)
    candidates: list[dict[str, Any]] = []
    for i in range(count):
        changes = []
        for var in safe_vars:
            vid = var["id"]
            center = _num(incumbent_values.get(vid))
            val = _refine_value(var, center, radius_frac, rng)
            changes.append({"variable_id": vid, "new_value": val})
        candidates.append({
            "format": "aieng.design_candidate_patch",
            "candidate_id": f"cand_iter{iteration + 1}_{i:03d}",
            "variable_changes": changes,
            "reasoning": (
                f"Local refinement around incumbent {incumbent_id} "
                f"(iteration {iteration + 1}, radius {radius_frac:.3f})."
            ),
        })
    return candidates, radius_frac


# ── public entrypoint ────────────────────────────────────────────────────────


def propose_next_candidates(
    package_path: str | Path,
    *,
    count: int = 4,
    shrink: float = 0.5,
    seed: int = 0,
    strategy: str = "auto",
) -> dict[str, Any]:
    """Propose the next batch of candidates for an optimization study.

    Parameters
    ----------
    package_path:
        Path to the .aieng package containing ranking, variables, and history.
    count:
        Number of candidate patches to emit.
    shrink:
        Per-iteration trust-region shrink factor (used by trust_region and
        genetic strategies).
    seed:
        Random seed for reproducibility.
    strategy:
        ``"auto"`` selects genetic when discrete/categorical variables are
        present and an incumbent is available; otherwise it uses trust-region
        refinement for continuous/integer spaces or LHS fallback when no
        incumbent exists. ``"genetic"`` forces the genetic algorithm.
        ``"trust_region"`` forces the existing trust-region refinement.

    Writes candidate patches to ``patches/design_candidates/<cid>.json`` and
    returns a summary. Baseline never modified.
    """
    pkg = Path(package_path)
    if not pkg.exists():
        return {"status": "error", "code": "package_not_found", "message": "package not found",
                "baseline_modified": False}
    if count < 1:
        return {"status": "error", "code": "bad_input", "message": "count must be >= 1",
                "baseline_modified": False}

    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            names = set(zf.namelist())
            ranking = _read_json(zf, DESIGN_STUDY_CANDIDATE_RANKING_PATH, names)
            variables_doc = _read_json(zf, OPTIMIZATION_VARIABLES_PATH, names)
            history = _read_json(zf, OPTIMIZATION_ITERATIONS_PATH, names)
            existing_ids = {
                n[len(DESIGN_CANDIDATES_DIR):-len(".json")]
                for n in names
                if n.startswith(DESIGN_CANDIDATES_DIR) and n.endswith(".json")
            }
            incumbent_values: dict[str, Any] = {}
            incumbent_id = None
            if isinstance(ranking, dict):
                incumbent_id = ranking.get("best_candidate_id")
                incumbent_values = _incumbent_variable_values(zf, names, incumbent_id)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "read_failed",
                "message": f"{type(exc).__name__}: {exc}", "baseline_modified": False}

    if not isinstance(variables_doc, dict):
        return {"status": "error", "code": "missing_variables",
                "message": f"{OPTIMIZATION_VARIABLES_PATH} not found", "baseline_modified": False}
    safe_vars = _filter_safe_variables(variables_doc.get("variables") or [])
    if not safe_vars:
        return {"status": "error", "code": "no_variables",
                "message": "no safe-to-modify variables to refine", "baseline_modified": False}

    iteration = (
        len(history.get("iterations") or []) if isinstance(history, dict) else 0
    )
    reason_codes: list[str] = []
    strategy_key = strategy.lower().replace("-", "_")

    discrete_present = _has_discrete_variables(safe_vars)
    has_incumbent = bool(incumbent_id and incumbent_values)

    use_genetic = False
    if strategy_key == "genetic":
        use_genetic = True
    elif strategy_key == "auto" and discrete_present and has_incumbent:
        use_genetic = True
    elif strategy_key == "auto" and discrete_present and not has_incumbent:
        # No incumbent to seed GA — fall back to LHS so we don't drift randomly.
        use_genetic = False

    # ── no feasible incumbent → whole-domain LHS fallback ────────────────────
    if not has_incumbent and not use_genetic:
        reason_codes.append("no_incumbent_fallback")
        candidates = latin_hypercube_sample(safe_vars, count=count, seed=seed)
        used_strategy = "lhs_fallback"
        radius_frac = 1.0
    elif use_genetic:
        # ── genetic algorithm local refinement ──────────────────────────────
        reason_codes.append("select_genetic")
        if discrete_present:
            reason_codes.append("discrete_variables_present")
        if iteration > 0:
            reason_codes.append("trust_region_shrink")
        candidates, radius_frac = _genetic_propose(
            safe_vars,
            count=count,
            seed=seed,
            incumbent_values=incumbent_values,
            iteration=iteration,
            shrink=shrink,
        )
        used_strategy = "genetic"
    else:
        # ── trust-region local refinement ───────────────────────────────────
        reason_codes.append("local_refinement")
        radius_frac = float(shrink) ** max(0, iteration)
        if iteration > 0:
            reason_codes.append("trust_region_shrink")
        if not incumbent_id:
            # Should not happen (caught above), but keep type checker happy.
            return {"status": "error", "code": "no_incumbent",
                    "message": "trust_region strategy requires an incumbent", "baseline_modified": False}
        candidates, radius_frac = _trust_region_propose(
            safe_vars,
            count=count,
            seed=seed,
            incumbent_values=incumbent_values,
            incumbent_id=incumbent_id,
            iteration=iteration,
            shrink=shrink,
        )
        used_strategy = "trust_region"

    if not candidates:
        return {"status": "error", "code": "proposer_exhausted",
                "message": "proposer produced no candidates", "proposer_exhausted": True,
                "baseline_modified": False}

    # de-dup ids against existing candidates on disk
    members: dict[str, bytes] = {}
    written_ids: list[str] = []
    for cand in candidates:
        cid = cand["candidate_id"]
        suffix = 0
        base = cid
        while cid in existing_ids:
            suffix += 1
            cid = f"{base}_{suffix}"
        existing_ids.add(cid)
        cand["candidate_id"] = cid
        members[f"{DESIGN_CANDIDATES_DIR}{cid}.json"] = _dumps(cand)
        written_ids.append(cid)

    _replace_members(pkg, members)

    return {
        "status": "ok",
        "strategy": used_strategy,
        "iteration": iteration + 1,
        "radius_fraction": radius_frac,
        "incumbent_candidate_id": incumbent_id,
        "reason_codes": reason_codes,
        "candidate_ids": written_ids,
        "candidate_count": len(written_ids),
        "baseline_modified": False,
        "claim_advancement": "none",
        "artifacts": list(members.keys()),
    }
