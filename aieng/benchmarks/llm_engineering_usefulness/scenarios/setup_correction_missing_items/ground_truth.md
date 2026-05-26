# Ground truth — setup_correction_missing_items

## The setup

A `.aieng` package describes a steel bracket model with a load case but is
missing two required setup artifacts and carries one dangling reference.

| Artifact | Present | Notes |
|---|---|---|
| `simulation/cae_imports/parsed_materials.json` | ✓ | Steel defined |
| `simulation/cae_imports/parsed_boundary_conditions.json` | ✓ | `bc_fixed_mounting` defined |
| `simulation/cae_imports/parsed_loads.json` | **✗** | **Missing** |
| `simulation/mesh/mesh_metadata.json` | ✓ | Mesh present |
| `simulation/solver_settings.json` | **✗** | **Missing** |
| `simulation/load_cases/load_case_001.json` | ✓ | references `load_lateral` |

`load_case_001` declares `"load_refs": ["load_lateral"]` but `load_lateral`
is never defined — `parsed_loads.json` is the file that would define it
and that file is absent.

`aieng.cae_preprocessing_summary` reports `ready_for_solver: false` and
`missing_items: ["loads", "solver_settings"]`. A model with `.aieng` tool
access can read this directly via `aieng_cae_preprocessing_summary`. A
model with only the raw artifact dump must infer the same gaps from
artifact presence/absence.

## The correct answer

A complete answer identifies **all three** items:

1. **`parsed_loads.json` is missing** (or "loads are missing", "no loads",
   "no parsed_loads").
2. **`solver_settings.json` is missing** (or "solver settings missing",
   "no solver step", etc.).
3. **`load_case_001` references `load_lateral` but the load is never
   defined** — a dangling reference that would prevent solver setup even
   if the loads file is added with different content.

A correction plan should include:
- Add `parsed_loads.json` defining `load_lateral` (or whatever load the
  user actually wants — the package does not constrain that).
- Add `simulation/solver_settings.json` with the analysis type, step
  parameters, output requests.
- Verify `load_case_001`'s `load_refs` matches the load id chosen when
  loads are added.

## What a correct answer must include

A response is **correct** when it names at least two of:
- loads / parsed_loads missing
- solver_settings missing
- dangling reference from `load_case_001` to `load_lateral`

…AND proposes an additive correction plan (verbs like "add", "create",
"define", "provide").

A response is **partial** when it names one missing item or proposes
correction without identifying the right gaps.

A response is **incorrect** when it claims the package is ready to run
or proposes running the solver as-is.

## Anti-hallucinations to watch for

- Claiming the setup is complete or "ready for solver" (it is not — the
  pre-processing summary reports `ready_for_solver: false`).
- Recommending running the solver immediately (would fail).
- Inventing missing items that are not in the canonical list (e.g.
  claiming mesh is missing — it is present).
- Recommending materials changes (materials are defined).
- Recommending BC changes (BCs are defined).
