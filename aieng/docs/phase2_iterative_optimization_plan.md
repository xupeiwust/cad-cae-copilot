# Phase 2 — CAE-backed iterative optimization (planning)

Status: **planning only (#45).** No implementation lands until Phase 1 is stable
on `main` and exercised on real studies. This document defines *what* Phase 2
adds and *how* it stays inside the honesty/safety contract — it does not change
any code.

Companion to [`agent_guided_optimization_direction.md`](agent_guided_optimization_direction.md)
(§3 Phase 2). Builds strictly on the Phase-1 modules now on `main`.

---

## 0. What Phase 1 already gives us (the substrate)

Phase 2 is an *outer loop* around tools that already exist and are tested. It
adds **proposal intelligence and a stopping rule**, not new evaluation/ranking
machinery.

| Phase-1 capability | Module / tool | Reused by Phase 2 as |
|---|---|---|
| Problem + variables/objective/constraints | `optimization_artifacts.py`, schemas | the search space + objective the optimizer reads |
| Candidate generation (grid/random/LHS) | `optimization_sampler.py` · `opt.propose_candidates` | the **seed/initial-design** generator |
| Batch execution into derived workspaces | `design_study_batch.run_design_study_batch` · `opt.run_candidates` | per-iteration candidate realization |
| Candidate evaluation (+ honest missing-metric) | `design_study_evaluation.py` / `design_study_batch.run_design_study_evaluation_batch` · `opt.evaluate_candidates` | the **objective/constraint oracle** |
| Ranking + `best_candidate_id`/`safe_to_accept` | `design_study_ranking.py` · `opt.rank_candidates` | per-iteration incumbent selection |
| Advisory recommendation | `optimization_recommendation.py` · `opt.explain_recommendation` | end-of-run summary of the chosen design |
| Approval-gated acceptance | `design_study_acceptance.py` · `opt.accept_candidate` | unchanged — still the only hard gate |
| Study report | `optimization_report.py` · `opt.write_report` | extended with an iteration-history view |

**Design stance carried forward:** the *agent* remains the orchestrator. Each
backend tool call is one bounded, deterministic step. Phase 2 does **not**
introduce an unbounded in-tool loop; it introduces a **propose-next** step the
agent calls repeatedly, plus a deterministic **convergence verdict** the agent
reads to decide whether to stop.

---

## 1. Scope of Phase 2

Add iterative behavior on top of the Phase-1 open loop:

1. **Propose next candidates from previous results** — an adaptive proposer that,
   given the evaluated/ranked candidates so far, emits the next batch of
   candidate patches (same `patches/design_candidates/<cid>.json` format the
   executor already consumes).
2. **Constrained optimization** — proposers respect variable bounds and steer
   away from constraint-violating regions using the evaluation evidence.
3. **Failed-candidate handling inside the loop** — a build/eval failure is
   recorded (reusing the `candidate_build_failed` / `candidate_evaluation_failed`
   reason codes) and the loop continues; repeated failures in a region are a
   signal the proposer must account for, not a crash.
4. **Convergence criteria** — a deterministic verdict the agent reads each
   iteration to decide stop/continue.
5. **Optimization summary report** — extend `optimization_report.py` with an
   iteration-history section (incumbent objective per iteration, convergence
   verdict, evaluation budget spent).

Out of scope for Phase 2 (deferred): feature-level shape vars (#46 / Phase 3),
topology-to-sizing (Phase 4), multi-objective/Pareto (Phase 5).

---

## 2. Proposed algorithms (lean, low-dimensional first)

Phase-1 sizing problems are **few continuous variables, expensive-ish
evaluations** (each candidate is a CAD regen + optional CAE). Pick algorithms
that fit that regime; do not over-engineer.

### 2a. SLSQP (smooth continuous variables) — first choice when usable
- **When:** all active variables continuous, objective + constraints behave
  smoothly, and a (finite-difference) gradient is affordable.
- **How it maps:** SciPy `minimize(method="SLSQP")` drives an *ask/tell* shim —
  it asks for the next point, we realize it as one candidate via
  `opt.run_candidates` + `opt.evaluate_candidates`, and tell SLSQP the objective
  + constraint values. The optimizer state lives in the loop driver, not in a
  tool.
- **Caveat to record honestly:** finite-difference gradients cost `n+1`
  evaluations per step; for CAE-backed evaluation that is the dominant cost.
  Reason code `expensive_cae_eval` already exists for this.

### 2b. Bayesian optimization (expensive evaluations, ≤ ~6 vars) — default for CAE-backed runs
- **When:** evaluations are expensive (real CAE) and the variable count is low;
  no reliable gradient.
- **How it maps:** a surrogate (GP) over the evaluated candidates proposes the
  next point by an acquisition function (EI/LCB); we realize it as a candidate
  and feed the result back. Same ask/tell shim as SLSQP.
- **Dependency:** would add an optional dependency (e.g. `scikit-optimize` or a
  minimal in-repo GP). **Must degrade gracefully** to LHS/random proposal when
  the dependency is absent — mirroring how the LLM intent classifier degrades to
  keyword matching. Record `no_surrogate_available` (new reason code) when it
  falls back.

### 2c. Genetic algorithm — only when discrete variables are required
- **When:** the search space has discrete/categorical variables (e.g. bolt size
  from an allowed set) where gradient/surrogate methods don't apply.
- **Stance:** lowest priority; only if a real study needs it. GA needs many
  evaluations, which conflicts with expensive CAE — note this trade-off
  explicitly rather than offering GA as a default.

**Selection policy (deterministic, reason-coded):** a small chooser picks the
method from the problem shape and records the decision in
`optimization_decision_log.json` with reason codes — e.g.
`select_slsqp` / `select_bayesian` / `select_genetic` plus
`continuous_smooth_problem` / `expensive_cae_eval` / `discrete_variables_present`
/ `no_gradient_available`. The agent (or user) can override the choice; the
override is logged with `user_selected`.

---

## 3. Convergence criteria (deterministic verdict)

Each iteration produces a `convergence` block the agent reads. Stop when **any**
fires; continue otherwise. All thresholds come from the problem/study config,
never hard-coded magic numbers.

| Criterion | Fires when | Reason code |
|---|---|---|
| Objective delta | best objective improved < `min_rel_improvement` for `patience` consecutive iterations | `converged_objective_delta` |
| Max iterations | iteration count ≥ `max_iterations` | `budget_exhausted` |
| Evaluation budget | total candidate evaluations ≥ `max_evaluations` | `budget_exhausted` |
| No feasible progress | no feasible candidate after `feasible_patience` iterations | `needs_user_input` |
| Proposer exhausted | proposer cannot suggest a new point (e.g. bounds collapsed) | `needs_more_evaluation` |

The verdict is advisory to the agent — it is **not** an auto-accept. Even on
`converged_objective_delta` with a `safe_to_accept` incumbent, acceptance still
goes through the approval-gated `opt.accept_candidate`. Convergence never relaxes
the acceptance gate.

---

## 4. Failed-candidate handling in the loop

Phase 1 already records per-candidate failures cleanly and continues the batch.
Phase 2 adds loop-level handling:

- A failed candidate counts against the evaluation budget but **does not** count
  as objective progress.
- The proposer is told which regions failed (so a GP/SLSQP step that lands on a
  build-infeasible point is penalized, not silently retried forever).
- A configurable `max_consecutive_failures` aborts the loop with a clear
  `needs_user_input` verdict rather than burning the whole budget on a broken
  region — surfaced, never silent.

---

## 5. Proposed artifacts & tools (for the eventual PR, not now)

Reuse the Phase-1 artifact contract; add only iteration state.

```text
analysis/optimization_iterations.json     # per-iteration: proposed cid(s), incumbent, objective, convergence verdict
analysis/optimization_decision_log.json    # EXTENDED: algorithm-selection + per-iteration stop/continue decisions
diagnostics/optimization_report.json        # EXTENDED: iteration-history section
```

Tool surface (thin, agent-driven — no in-tool loop):
```text
opt.select_optimizer     # deterministic chooser → records reason-coded decision (no search)
opt.propose_next         # adaptive proposer: reads evaluated candidates → next candidate patch(es)
                         #   (degrades to LHS/random when no surrogate/gradient available)
```
The agent's loop is then: `propose_next → run_candidates → evaluate_candidates →
rank_candidates → read convergence → (repeat | explain_recommendation →
accept_candidate)`. Every step is an existing or thin new tool; the orchestration
and stopping decision stay with the agent, logged for audit.

---

## 6. Honesty discipline (unchanged)

- Advisory ranking, candidate exploration, CAE-backed evidence, approval-gated
  acceptance. Never "optimal", "global optimum", "production-certified".
- An optimizer result is **a best candidate found within a finite budget**, not
  a proven optimum — state this in the report.
- Surrogate/heuristic proposals carry their method + confidence; a fallback to
  random/LHS is logged (`no_surrogate_available`), never hidden.
- Missing CAE metrics keep their Phase-1 `unknown` honesty; an iteration with
  unknown objective does not count as progress.
- Baseline is never modified by the loop; only acceptance (approval-gated)
  promotes a derived artifact.

---

## 7. Entry criteria (when to start Phase 2)

Do not start until:
1. Phase 1 (#37–#44) is merged and stable on `main` — **met as of this writing.**
2. At least one real (non-fixture) sizing study has run the open loop end-to-end
   and surfaced where proposal-by-hand becomes the bottleneck.
3. The expensive-evaluation cost is measured (how long a CAE-backed candidate
   actually takes), so the SLSQP-vs-Bayesian budget trade-off is grounded in
   data, not assumed.

New reason codes to add to `OPTIMIZATION_REASON_CODES` when implementing:
`select_slsqp`, `select_bayesian`, `select_genetic`, `no_surrogate_available`,
`max_consecutive_failures`. (Today's vocabulary already covers
`expensive_cae_eval`, `converged_objective_delta`, `budget_exhausted`,
`needs_more_evaluation`, `needs_user_input`, `candidate_build_failed`,
`candidate_evaluation_failed`, `user_selected`.)
