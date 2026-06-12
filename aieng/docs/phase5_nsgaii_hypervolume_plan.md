# Phase 5 — NSGA-II / hypervolume multi-objective search (planning)

Status: **planning only (#115).** No implementation lands until the advisory
Pareto-front machinery in Phase 5 (#112, #113, #114) is merged and stable.
This document defines the scope, API sketch, integration points, and explicit
non-goals for a generative multi-objective search layer.

Companion to [`phase3_feature_shape_optimization_plan.md`](phase3_feature_shape_optimization_plan.md),
[`demo_catalog.md`](demo_catalog.md), and Epic #100 (Phase 5 — Multi-objective /
Pareto exploration).

---

## 1. Core principle: generate candidates, not just rank them

The existing Phase-5 Pareto work (#112–#114) answers: *"given the candidates I
already evaluated, which ones are non-dominated?"*.

This planning layer answers the next question: *"what candidate should I try
next when I want to improve coverage of the Pareto frontier?"*. It is a
**candidate proposer for multi-objective studies**, not a new solver or a
proven Pareto surface.

Key design decisions:

- **Reuse the existing single-candidate execution and evaluation pipeline.**
  Every proposed candidate is still executed through `opt.run_candidates` and
  evaluated through `opt.evaluate_candidates`. The search loop only decides
  which parameter vector to try next.
- **Stay derivative-free and deterministic.** NSGA-II is a genetic algorithm
  with clear, reproducible selection, crossover, and mutation operators. It
  requires no gradient information, so it works with black-box CAE-backed
  objective functions.
- **Use hypervolume as the convergence/quality indicator.** Hypervolume
  measures the dominated area (or volume) relative to a reference point. It
  captures both convergence and diversity in a single scalar, which is ideal
  for budget-limited agent decisions.

---

## 2. Explicit non-goals (the boundary)

Phase 5 search will **NOT** attempt:

- **Proven global Pareto optimality.** The output is always an *advisory
  frontier over evaluated candidates* with the same honesty boundary as #112.
- **Adaptive surrogate models.** No Gaussian-process, neural-network, or
  response-surface surrogates in the first cut. Every proposed candidate is
  evaluated by the real (mock or solver-backed) CAE pipeline.
- **Constraint handling beyond feasibility classification.** NSGA-II's
  constraint-domination mechanism will reuse the existing feasibility classes
  (`feasible`, `infeasible`, `failed`, `unknown`) already produced by
  `design_study_ranking`.
- **Many-objective optimization.** The MVP targets exactly two objectives,
  matching the current Pareto-front implementation. Three or more objectives
  are deferred.
- **Interactive human-in-the-loop preference articulation.** The first version
  runs with fixed reference points and budgets. Preference-based steering
  (e.g., "lighter is more important than stronger") is future work.
- **Production-certified Pareto sets.** As everywhere, acceptance remains
  approval-gated and advisory-only.

---

## 3. Proposed API

The search tool is an opt-in proposer that consumes an existing design-study
package and produces the next batch of candidate parameter vectors.

```python
def propose_nsga2_candidates(
    package_path: str | Path,
    *,
    population_size: int = 10,
    generations: int = 2,
    seed: int | None = None,
) -> dict[str, Any]:
    """Return the next population of candidate parameter vectors.

    The function is read-only with respect to the baseline: it writes candidate
    patch proposals to the package but does not execute or accept them.
    """


def hypervolume_indicator(
    front: list[dict[str, Any]],
    reference_point: list[float],
    objectives: list[dict[str, Any]],
) -> float:
    """Compute the dominated hypervolume of a 2-D Pareto front.

    Lower-is-better objectives are used as-is; higher-is-better objectives are
    negated internally so the same "smaller dominated region is better"
    interpretation holds.
    """
```

Suggested CLI hooks (future):

```bash
aieng opt propose-candidates --strategy nsga2 --population 10 --generations 2 pkg.aieng
aieng opt evaluate-front-quality --reference "mass=2.0,max_stress=300.0" pkg.aieng
```

---

## 4. Integration with existing Phase-5 artifacts

The search loop reads and writes the same artifacts already introduced by
#112–#114:

| Artifact | Role in search |
|---|---|
| `analysis/design_study_problem.json` | Supplies variables, objectives, constraints, baseline. |
| `analysis/design_study_candidate_ranking.json` | Seeds the initial population from already-evaluated candidates. |
| `analysis/pareto_front.json` | Provides the current non-dominated set and `objectives` for normalization. |
| `candidates/<cid>/analysis/evaluation.json` | Supplies objective metric values for fitness assignment. |
| `patches/design_candidates/<cid>.json` | Where new candidate parameter vectors are written (reuses Phase-1 patch format). |
| `diagnostics/optimization_decision_log.json` | Records search decisions, budget, reference point, and reason codes. |

Sequence:

```
opt.propose_nsga2_candidates
    ├─ read problem + current ranking + pareto_front
    ├─ seed population from evaluated feasible candidates
    ├─ run NSGA-II selection/crossover/mutation on variable vectors
    ├─ write new candidate patches (no execution)
    └─ log decision with hypervolume of current front

opt.run_candidates      → unchanged
opt.evaluate_candidates → unchanged
opt.rank_candidates     → unchanged (now computes updated Pareto front)
opt.explain_recommendation → unchanged (Pareto-aware advisory output)
```

---

## 5. Algorithm sketch (MVP)

1. **Encoding.** Each candidate is a real-valued vector of normalized
   variable values in `[0, 1]` (variables map back to their `[min, max]`
   ranges). Integer or discrete variables are handled with round-to-nearest
   during decoding.
2. **Initial population.** If evaluated candidates exist, use the
   non-dominated front plus a diversity sample as the initial population.
   Otherwise, sample uniformly with the existing sampler.
3. **Fitness.** NSGA-II's non-dominated sorting + crowding distance, applied
   to the two objective values after sense normalization (minimize/reduce
   unchanged, maximize/improve negated).
4. **Constraint handling.** Infeasible candidates are ranked below feasible
   ones using constraint-domination. Failed/unknown candidates are discarded.
5. **Operators.** Simulated-binary crossover (SBX) and polynomial mutation,
   both deterministic given a seed.
6. **Termination/budget.** Run for a fixed number of generations or until a
   generation's hypervolume improvement falls below a threshold.
7. **Output.** Return the decoded variable vectors of the final population as
   candidate proposals. Hypervolume of the current front is recorded in the
   decision log.

---

## 6. Hypervolume computation

For the two-objective MVP, hypervolume can be computed with the exact
2-D sweep algorithm:

1. Sort front points by the first objective (ascending after normalization).
2. Walk the sorted list and accumulate rectangles defined by each point and
   the reference point.
3. Return the total dominated area.

The reference point should be a **worse-is-acceptable point** supplied by the
problem or defaulted to the worst observed value plus a small margin. The
choice of reference point must be recorded in provenance because it directly
affects the absolute hypervolume value.

Future work: for more than two objectives, switch to a known hypervolume
approximator (e.g., WFG algorithm or Monte-Carlo sampling).

---

## 7. Honesty discipline

- The search is **exploration-only**. It does not claim to have found the true
  Pareto front, only a better-sampled advisory frontier.
- Every proposal is **traceable**: parent candidate IDs, generation index,
  mutation/crossover operator, and seed are recorded.
- **Budget-aware**: the decision log records `evaluations_consumed` and
  `evaluations_budget` so the agent can stop early.
- **Reference point explicit**: hypervolume values are meaningless without the
  reference point; both are stored.
- Acceptance remains **approval-gated**: the search loop never auto-accepts a
  frontier point.

---

## 8. Dependencies and ordering

| Prerequisite | Why |
|---|---|
| #112 merged | Stable `analysis/pareto_front.json` and two-objective dominance logic. |
| #113 merged | Pareto-aware recommendation/report so the agent can explain search output. |
| #114 merged | Mass-vs-stress demo provides the canonical test bed for the search loop. |
| #115 (this doc) approved | Shared understanding of scope before any code lands. |

---

## 9. Acceptance criteria for future implementation issue

When this plan is promoted to an implementation issue, it should:

- [ ] Implement `propose_nsga2_candidates` with deterministic SBX + polynomial mutation.
- [ ] Implement `hypervolume_indicator` for exactly two objectives.
- [ ] Seed the initial population from the existing Pareto front when available.
- [ ] Record search decisions in `analysis/optimization_decision_log.json`.
- [ ] Add a backend test/demo that runs two generations on the mass-vs-stress case.
- [ ] Demonstrate hypervolume improvement across generations.
- [ ] Assert no baseline modification and advisory-only claim policy.
