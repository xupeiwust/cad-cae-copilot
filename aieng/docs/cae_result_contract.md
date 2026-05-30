# Solver-neutral CAE result contract

CAE result mapping is **decoupled from any specific solver**. CalculiX is only the
first adapter — not the core abstraction. Any solver (Code_Aster, Elmer, FEniCSx,
a remote/cloud solver, or a mock) plugs in by emitting the same *neutral* files.

## Three-layer architecture

```
any solver output (.frd/.rmed/.vtu/.json/…)
        │
        ▼
  solver adapter / normalizer        ← solver-specific parsing lives ONLY here
        │   writes the neutral contract artifacts:
        ▼
  analysis/computed_metrics.json   (normalized scalar extrema per load case)
  analysis/field_regions.json      (normalized spatial regions / clusters)
        │
        ▼
  Shape IR mapper  (cae_result_map) ← solver-NEUTRAL; reads only neutral + geometry
        │   topology_map.json + registry/object_registry.json
        ▼
  analysis/cae_result_map.json     (results ↔ topology entities ↔ source_ir_node)
        │
        ▼
  Shape IR / object_registry / future topology optimization
```

1. **Solver runner** — executes the analysis, produces solver-native output.
   (CalculiX runner: `cae.run_solver` → `.frd`.)
2. **Result normalizer / adapter** — translates native output into the neutral
   artifacts below. *All* solver-specific naming/parsing stays here. The CalculiX
   adapter is `converters/cae_result_contract.py` (`normalize_calculix_*`,
   `write_normalized_cae_artifacts`).
3. **Shape IR mapper** — `converters/cae_result_map.py::map_cae_results(...)`
   consumes **only** the neutral artifacts + `topology_map.json` +
   `registry/object_registry.json`. It never reads `.frd/.dat/.inp` and knows no
   solver's naming. This is what makes the mapping solver-neutral.

A non-CalculiX solver can either ship its own adapter, or emit
`analysis/computed_metrics.json` + `analysis/field_regions.json` directly.

## Artifacts & schemas

### `analysis/computed_metrics.json` — normalized scalar results

```jsonc
{
  "format": "aieng.cae.computed_metrics",
  "schema_version": "0.1",
  "contract_version": "0.1",
  "solver": { "name": "calculix", "version": "2.20", "adapter": "calculix_frd_v1" },
  "load_cases": [
    { "id": "lc1", "results": [
        { "result_type": "stress",       "metric": "max_von_mises_stress",
          "max": 245.0, "min": null, "average": null, "unit": "MPa" },
        { "result_type": "displacement", "metric": "max_displacement",
          "max": 0.82,  "min": null, "average": null, "unit": "mm" }
    ] }
  ],
  "warnings": []
}
```
`result_type` is the neutral category (`stress` / `displacement` / `deflection` /
`strain` / …). `metric` keeps the solver's original metric name for provenance.
`min`/`average` are `null` when the source reports extrema only.

### `analysis/field_regions.json` — normalized spatial regions

```jsonc
{
  "format": "aieng.cae.field_regions",
  "schema_version": "0.1",
  "contract_version": "0.1",
  "solver": { "name": "calculix", "version": null, "adapter": "calculix_frd_v1" },
  "regions": [
    { "id": "region_001",
      "result_type": "stress",
      "load_case_id": "lc1",
      "center": { "x": 13.0, "y": 0.0, "z": 18.0 },
      "bbox": [10, -3, 6, 16, 3, 26],            // optional
      "value": { "peak": 245.0, "min": null, "max": 245.0, "unit": "MPa" },
      "node_count": 40,
      "source_metadata": { "feature_ref": null, "native_field": "S" }
    }
  ],
  "warnings": []
}
```
Unlike the CalculiX-native `results/field_regions.json` (one FRD field per file),
the neutral file holds **all** result types in one `regions` array, each tagged
with its own `result_type`.

### `analysis/cae_result_map.json` — mapping back to Shape IR

```jsonc
{
  "format": "aieng.cae_result_map",
  "contract_version": "0.1",
  "solver": { "name": "calculix", "version": "2.20", "adapter": "calculix_frd_v1" },
  "units": { "stress": "MPa", "displacement": "mm" },
  "load_cases": ["lc1"],
  "overall":   [ { "load_case_id", "result_type", "metric", "max", "min", "average", "unit" } ],
  "mapped_results": [
    { "load_case_id": "lc1", "result_type": "stress", "region_id": "region_001",
      "value": 245.0, "unit": "MPa", "location": { "x", "y", "z" },
      "affected_topology_entities": ["body_002", "face_010", "face_011"],
      "source_ir_node": "post", "node_linkage": "name_match",
      "mapping_method": "bbox_contains", "confidence": "high" }
  ],
  "unmapped_regions": [ { "region_id", "result_type", "location", "reason" } ],
  "summary": { "mapped_count", "unmapped_count", "resolved_to_node" },
  "provenance": {
    "solver_name", "solver_version", "adapter",
    "computed_metrics_schema", "field_regions_schema",
    "mapping_methods": ["bbox_contains", "nearest_center"],
    "unsupported_or_uncertain": [ { "region_id", "reason" } ],
    "artifact_source": "neutral" | "calculix_normalized"
  }
}
```

**Mapping** ties a region's `center` to a topology body (bbox containment, else
nearest centre), then to a Shape IR node via the object registry. `confidence`:
`high` (contained + exact node linkage) / `medium` (nearest / weaker linkage) /
`low` (region known but node not unique, e.g. fused mesh). Regions with no nearby
geometry are reported in `unmapped_regions` — never silently dropped.

## Provenance

Every neutral artifact carries a `solver` block (`name`, `version`, `adapter`),
a `schema_version`, and a `contract_version`. The result map additionally records
the `mapping_methods` used, `unsupported_or_uncertain` regions, and whether the
inputs were already neutral or normalized from a legacy CalculiX package
(`artifact_source`).

## Adding a new solver

1. Run the solver (outside aieng — aieng executes no solver/mesher itself for
   non-CalculiX backends; it imports/references evidence).
2. Write an adapter that emits `analysis/computed_metrics.json` and
   `analysis/field_regions.json` in the neutral shapes above (mirror
   `normalize_calculix_*`). Set `solver.name` / `solver.adapter`.
3. Call `cae.map_results` (or `write_cae_result_map`) — the same neutral mapper
   produces `analysis/cae_result_map.json`. No mapper changes required.

The generic/fake-solver fixture in `tests/test_cae_result_map.py`
(`solver.name = "generic_fake"`) proves the mapping path is solver-neutral.

## Backward compatibility

Legacy CalculiX packages (only `results/computed_metrics.json` +
`results/field_regions.json`, no `analysis/*`) are still supported: the loader
normalizes them on the fly, and `write_cae_result_map` persists the neutral
`analysis/*` artifacts. `map_cae_results(...)` itself only ever sees neutral data.
