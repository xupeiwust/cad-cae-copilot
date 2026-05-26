# AIENG v0.2.x Multi-Repo Readiness Note

> Cold-reader snapshot of the AIENG ecosystem as of the v0.2.x line.
> This is a documentation checkpoint, not a release tag or engineering certification.

---

## 1. Executive summary

AIENG has moved from a schema/CLI prototype toward a benchmarked engineering-context system with:

- **Auditable `.aieng` packages** — evidence accounting, claim boundaries, trace/completeness reporting
- **Measured LLM benchmark evidence** — 4 CAE reasoning scenarios with scored results
- **Design target contracts** — `task/design_targets.yaml` with structured comparison results
- **CLI comparison surface** — `aieng compare-design-targets <package> --output json|text --write-summary`
- **UI display** — design target comparison table in `aieng-ui` CAE results panel
- **Runtime approval gates** — approval-gated runtime operations in `aieng-ui`

What this is **not**:

- Not an engineering certification
- Not automatic claim advancement
- Not a full CAD/CAE replacement

---

## 2. Current repository status

| Repo | Branch | Source-of-truth remote | Latest checked commit | Working tree | Notes |
|---|---|---|---|---|---|
| `aieng` | `main` | `github` (`github.com/armpro24-blip/aieng`) | `97b5d09` — `docs: checkpoint Phase 35 and benchmark stabilization` | Clean | Includes Phase 30 benchmark milestone, Phase 35 PR 1–4, Issue #59/#60 fixes, docs checkpoint |
| `aieng-ui` | `master` | `origin` (`github.com/armpro24-blip/aieng-ui`) | `c3259b8` — `fix(runtime): skip field summary when field regions are missing` | Clean (last verified) | 27 runtime tools, approval gates, design target comparison UI, field summary graceful skip |
| `aieng-freecad-mcp` | `main` | `origin` (`github.com/armpro24-blip/aieng-freecad-mcp`) | `1118944` — `feat(aieng): expose design target inspection tools` | Clean (last verified) | MCP bridge / adapter role, FreeCAD tool surface, read-only design target inspection |

All three repos were verified clean and in sync with GitHub at the time of this note.

---

## 3. What is now working

### Core `.aieng` package layer

- Package resources with validation
- Evidence / claim / trace / completeness accounting
- Claim boundaries and honesty reporting
- Design targets in `task/design_targets.yaml`
- Result summaries with `design_target_comparisons`
- CLI comparison: `aieng compare-design-targets <package>`

### Benchmarks

- **4 CAE reasoning scenarios** shipped in the benchmark suite
- **Scenario 4** (setup correction) shows measured correctness divergence:
  - Condition A (raw dump): 0.450
  - Condition B (structured `.aieng` access): 0.950
  - Model: `anthropic/kimi-for-coding`
  - n = 10, temperature = 0
- Token-efficiency gains observed on larger packages with structured access
- Honest caveats:
  - One model tested so far
  - One correctness-divergence scenario (Scenario 4)
  - Deterministic scorer
  - No engineering validity claim

### Design targets

- `task/design_targets.yaml` defines target contracts
- Legacy + modern field compatibility
- `design_target_comparisons` produced by CLI
- Comparison statuses:
  - `pass` — meets target based on available artifact evidence
  - `fail` — does not meet target based on available artifact evidence
  - `unknown` — evidence exists but required value is missing or unreadable
  - `not_evaluated` — no relevant evidence or policy-only target
- CLI options: `--output json|text`, `--write-summary`
- No `claim_map` mutation from comparison results

### UI / runtime

- Design target comparison display in `aieng-ui` CAE results panel
- Approval-gated runtime operations
- Mesh generation with honesty reporting
- Field summary graceful skip when `results/field_regions.json` is missing
- No automatic claim advancement

### MCP / FreeCAD adapter

- Runtime bridge role between AIENG and FreeCAD
- FreeCAD tool surface exposed via MCP
- **Read-only design target inspection** (new):
  - `aieng_read_design_targets` — reads `task/design_targets.yaml` from `.aieng` packages
  - `aieng_read_design_target_comparisons` — reads `results/result_summary.json#design_target_comparisons`
  - Works with zip and directory-form packages
  - Returns missing-resource states gracefully
  - Does not mutate package, CAD, or `claim_map.json`
  - Safe for agent preflight / evidence inspection
- Mutation-gating based on design targets remains future work

---

## 4. Measured evidence

| Evidence | Result | Scope |
|---|---|---|
| Scenario 4 setup correction | Condition A: 0.450 vs Condition B: 0.950 | Kimi, n=10, T=0 |
| Token efficiency | Structured access cheaper on larger packages | Scenarios measured in benchmark README |
| Targeted tests | Backend 174 passed, 2 skipped (`aieng-ui`) | Latest local run |
| Full suite health | `aieng`: 1582 passed, 15 skipped; `aieng-ui`: 174 passed, 2 skipped | Latest local runs |

Do not overstate: these are point-in-time measurements on specific scenarios, not generalizable engineering guarantees.

---

## 5. Honesty boundaries

- `.aieng` does **not** prove engineering validity.
- Pass/fail design target comparisons are **artifact-threshold checks**, not certification.
- `claim_map` is **not** advanced automatically.
- Preserved interfaces are **not** fully geometry-diff validated yet.
- Objective priority is currently policy / `not_evaluated`.
- Structured access does **not** always improve correctness.
- Structured access is **not** always cheaper on tiny packages.
- AI does **not** replace CAE judgment.

---

## 6. Deferred work

- Design target UI polish / richer UX
- Real geometry-diff preservation checking
- Objective-priority resolution logic
- Second-model benchmark evaluation
- Stochastic benchmark trials
- LLM-graded rubric for open-ended reasoning
- Design-target-aware mutation gating in MCP
- Richer MCP planning based on target priority
- Release tag / demo package, if desired

---

## 7. Recommended next milestones

1. **Design-target-aware mutation gating** — use `aieng_read_design_targets` context to gate/advise CAD mutation proposals
2. **Real preserve-diff evidence resource** — validate geometry preservation with diff artifacts
3. **Second-model benchmark run** — repeat Scenario 4 with another model to check generalization
4. **v0.2.x release tag / demo package** — package a stable demo snapshot
5. **UI polish for design-target comparisons** — richer status display, filtering, export

---

## 8. Quick verification commands

These are verification commands, not mandatory release commands.

```bash
# aieng
cd aieng
git status --short --branch
python -m pytest -q
aieng compare-design-targets path/to/package.aieng --output json

# aieng-ui backend
cd ../aieng-ui/backend
python -m pytest tests/test_api.py -q

# aieng-ui frontend
cd ../frontend
npx tsc --noEmit
npm run build
```

---

## Optional docs links

- [`README.md`](../README.md) — outward-facing project overview
- [`docs/design_targets.md`](design_targets.md) — design target contract details
- [`docs/roadmap.md`](roadmap.md) — planned phases and milestones
- [`benchmarks/llm_engineering_usefulness/README.md`](../benchmarks/llm_engineering_usefulness/README.md) — benchmark methodology
