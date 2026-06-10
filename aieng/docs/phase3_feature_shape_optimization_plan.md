# Phase 3 — Feature-level shape optimization (planning)

Status: **planning only (#46).** No implementation lands until Phase 1 is stable
and Phase 2 (#45) is at least scoped. This document defines the *scope and
boundary* of feature-level shape optimization — explicitly what it does and,
just as importantly, what it deliberately does **not** attempt.

Companion to [`agent_guided_optimization_direction.md`](agent_guided_optimization_direction.md)
(§3 Phase 3) and [`phase2_iterative_optimization_plan.md`](phase2_iterative_optimization_plan.md).

---

## 1. Core principle: "shape" through stable feature parameters, not free nodes

The headline decision: **feature-level shape optimization reuses the parameter
optimization framework unchanged.** A "shape" change is expressed as a change to
a named, editable CAD feature parameter — exactly the variables Phase 1 already
samples, executes, evaluates, ranks, and accepts.

This is the safe, reproducible path: every shape variant is a deterministic
`cad.edit_parameter`-style edit of a named constant in `geometry/source.py`, with
a `regression_diff` proving only the intended feature changed. It is **not** a
new geometry engine.

So Phase 3 adds essentially **no new search/eval/rank machinery** — it adds
**recognition of which feature parameters are shape-bearing**, and guidance for
the agent to treat them as optimization variables.

---

## 2. Explicit non-goals (the boundary)

Phase 3 (and the early versions generally) will **NOT** attempt:

- **Arbitrary boundary-node movement.** Moving individual mesh/BREP boundary
  nodes is out — it breaks reproducibility, has no stable parameter identity, and
  cannot be expressed as a named feature edit.
- **Free-form / NURBS control-point optimization (FFD).** Deforming control
  nets or free-form lattices is explicitly deferred. The existing free-form
  faces (loft/sweep/spline) keep their surface class for *selection*, but their
  control geometry is **not** an optimization variable in Phase 3.
- **Adjoint / shape-gradient methods.** No continuous shape sensitivity / adjoint
  solvers. Phase 3 stays in the discrete "edit a named parameter, re-evaluate"
  regime.
- **Topology change as a shape variable.** Adding/removing features (holes,
  ribs) is a topology edit, not a sizing of an existing feature — out of scope
  here (topology work is Phase 4, within the existing SIMP safe scope).
- **Production-certified shape results.** As everywhere: advisory candidate
  exploration with CAE-backed evidence, approval-gated acceptance only.

Stating these now prevents scope-creep toward a freeform optimizer that the
project's honesty posture cannot back.

---

## 3. Supported feature parameters (the Phase-3 variable catalog)

These are stable, named feature parameters already surfaced by the editable-
parameter index (`build_parameter_index` / `cad.list_editable_parameters`). Phase
3 recognizes them as *shape-bearing* and lets the optimizer drive them:

| Feature parameter | Shape effect | Notes |
|---|---|---|
| **Fillet radius** | edge rounding / stress-relief | classic stress-vs-mass shape knob; ideal first target |
| **Hole / slot diameter** | opening size | already a Phase-1 sizing var; shape-relevant for stress concentration |
| **Hole / slot position** | feature location | x/y offset constants; must respect edge-distance manufacturing rules |
| **Rib height / thickness** | stiffener profile | sizing of an existing stiffener |
| **Gusset dimensions** | bracket reinforcement profile | width/height/thickness constants |
| **Chamfer size** | edge break | same class as fillet |
| **Wall taper / draft** (if parameterized) | wall profile | only when expressed as a named constant |

Recognition heuristic: a parameter is shape-bearing when its
`cad_parameter_name` / `semantic_role` matches this catalog (fillet/chamfer/
radius/position/rib/gusset/taper). This reuses the same tokenization the
`/modify` slot-binding and parameter index already do — no new parser.

Constraints stay the same as Phase 1 (max_stress, max_deflection,
min_safety_factor, mass/volume limits) plus the **manufacturing rules** the
Engineering-Mode critique already encodes (min wall ≥ 3 mm CNC, hole-edge
distance ≥ 2× radius, internal corner radius ≥ 2 mm). A shape candidate that
violates a manufacturing rule is infeasible — reuse `cad.critique` findings as
constraint evidence rather than inventing new checks.

---

## 4. How it reuses the existing pipeline (no new framework)

```
opt.propose_candidates  →  same sampler, over shape-bearing feature parameters
opt.run_candidates      →  same executor; each shape variant is a deterministic
                           named-constant edit + re-execute (regression_diff proves
                           only the targeted feature changed)
opt.evaluate_candidates →  same evaluator; + cad.critique manufacturing findings
                           folded in as constraint evidence
opt.rank_candidates     →  unchanged
opt.explain_recommendation / opt.accept_candidate / opt.write_report → unchanged
```

The only genuinely new work:
1. **Tag shape-bearing parameters** in the variable resolution step (a flag on
   each variable, e.g. `shape_bearing: true`, derived from the catalog above).
2. **Fold `cad.critique` manufacturing findings into constraint evidence** so a
   shape edit that creates a too-thin wall or too-close hole is correctly
   `infeasible`, not silently feasible.
3. Optional: a `regression_diff`-aware guard so a shape edit flagged
   `collateral_change` (it moved parts it shouldn't) is treated as a failed
   candidate (`candidate_build_failed`), not accepted.

---

## 5. Honesty discipline (unchanged)

- "Feature-level shape exploration via stable parameters", not "shape
  optimization" in the freeform sense. Be explicit that the design space is the
  set of named feature parameters, not the full geometry.
- Advisory ranking; CAE-backed evidence; approval-gated acceptance; baseline
  never overwritten.
- Manufacturing-rule feasibility comes from the existing deterministic critique,
  not a new unvalidated check.

---

## 6. Entry criteria

Do not start until:
1. Phase 1 is stable on `main` — **met.**
2. Phase 2's adaptive proposer exists (Phase 3 shape vars are most useful with an
   iterative loop; with only open-loop sampling they still work but explore less
   efficiently). Phase 3 can technically run on the Phase-1 open loop, so it is
   **not hard-blocked** on Phase 2 — but sequencing after Phase 2 is preferred.
3. The editable-parameter index reliably surfaces fillet/chamfer/position
   constants on real engineering parts (verify on a bracket/housing that these
   appear as editable parameters with correct ranges).

No new reason codes are strictly required; reuse `constraint_violation`
(manufacturing-rule failures), `candidate_build_failed` (collateral/regression),
and the existing feasibility vocabulary. If a "shape edit moved protected
interface" case needs its own signal, add `protected_parameter` (already in the
shared vocabulary) usage there.
