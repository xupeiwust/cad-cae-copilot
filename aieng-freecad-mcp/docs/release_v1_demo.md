# v1.0.0 Composable Demo Walkthrough

v1.0 target: public composable `.aieng`-enhanced CAD/CAE execution demo.

## Core Principle

CAD and CAE are independent first-class capabilities.

- CAD does not automatically trigger CAE.
- CAE does not require prior CAD mutation.
- CAD->CAE is optional and explicit.
- Evidence is not a claim.
- Claim updates are explicit and evidence-backed.

## Five Composable Paths

### 1. CAD-only

Flow: `.aieng` patch -> guarded CAD edit -> artifact evidence -> trace.

Tool focus: `aieng_parse_patch`, `aieng_execute_patch`.

Not claimed: no CAE, no claim update, no safety verdict.

Run:

```bash
python scripts/run_v1_demo.py --path cad-only
```

### 2. CAE-only

Flow: simulation/result input -> post-processing evidence -> trace.

Tool focus: `aieng_postprocess_results`.

Not claimed: no CAD mutation, no claim update, no validation shortcut.

Run:

```bash
python scripts/run_v1_demo.py --path cae-only
```

### 3. Optional CAD->CAE

Flow: CAD patch -> explicit orchestration helper -> CAE/postprocess evidence.

Tool focus: `aieng_execute_patch`, `aieng_run_cad_to_cae_workflow`.

Not claimed: helper is not automatic; `run_solver=False` by default; no claim update.

Run:

```bash
python scripts/run_v1_demo.py --path cad-cae
```

### 4. Reference

Flow: build reference map -> geometry change -> mark affected refs `needs_review`.

Tool focus: `aieng_build_reference_map`, `aieng_mark_references_needing_review`.

Not claimed: mapping is traceability evidence only; no CAE/claim updates.

Run:

```bash
python scripts/run_v1_demo.py --path reference
```

### 5. Claim

Flow: evidence IDs + criteria -> explicit `aieng_update_claim` -> claim map update.

Tool focus: `aieng_update_claim` (only claim-map mutator).

Not claimed: evidence alone does not update claims.

Run:

```bash
python scripts/run_v1_demo.py --path claim
```

## Run All Paths

```bash
python scripts/run_v1_demo.py --path all
```

Legacy unified demo remains available:

```bash
python scripts/run_v1_end_to_end_demo.py
```

## Claim Discipline Checks

- `claims_advanced=false` for all tools except explicit claim update.
- `engineering_validation=false` for solver/postprocess evidence unless explicitly claim-evaluated.
- `claim_map.json` is immutable outside explicit claim update.
- Surrogate outputs are marked as estimates/mock evidence, not solver validation evidence.
