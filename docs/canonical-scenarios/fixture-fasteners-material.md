# Fixture Plate: Holes, Fasteners, and Material Semantics

This canonical scenario exercises manufacturing semantics without claiming
physical joint behavior. It is a CI-regression pack around hole recognition,
`bd_warehouse` standard-part recognition, BOM export, and explicit material
assignment.

## Scenario Intent

The target model is a small fixture plate with:

- a machined base plate;
- a four-position M6 bolt pattern;
- real `bd_warehouse.fastener.SocketHeadCapScrew` objects, not string-only
  placeholders;
- standard-part metadata promoted into the feature graph;
- BOM lines that aggregate repeated standard parts;
- a named base plate with an explicit material assignment.

This is a semantics and packaging scenario. It does not model bolt preload,
thread engagement, contact pressure, procurement validity, or joint strength.

## Entrypoints

- `aieng-ui/backend/tests/test_cad_generation.py::test_execute_build123d_code_with_bd_warehouse_fastener`
- `aieng-ui/backend/tests/test_cad_generation.py::test_execute_build123d_bd_warehouse_clearance_hole_bolt_pattern`
- `aieng-ui/backend/tests/test_standards_bridge.py::test_generate_bom_csv_export_matches_schema`
- `aieng-ui/docs/standard_part_semantics.md`

## Lightweight Verification

```bash
python -m pytest aieng-ui/backend/tests/test_cad_generation.py::test_execute_build123d_code_with_bd_warehouse_fastener aieng-ui/backend/tests/test_cad_generation.py::test_execute_build123d_bd_warehouse_clearance_hole_bolt_pattern -q
python -m pytest aieng-ui/backend/tests/test_standards_bridge.py::test_generate_bom_csv_export_matches_schema -q
```

The build123d/bd_warehouse tests are skip-gated by `pytest.importorskip` when
the real CAD dependencies are unavailable. The BOM export check is pure package
metadata and should run in normal CI.

## Expected Artifacts

- `geometry/generated.step`
- `graph/feature_graph.json`
- `reports/bom.csv`
- `reports/bom.json`

The feature graph should include `standard_part` entries with:

- `standard_part: true`
- `source_library: "bd_warehouse"`
- `canonical_type` such as `screw`
- `designation` such as `M6-1`

The BOM should aggregate repeated M6 screws while preserving material on the
base plate when provided.

## Honesty Boundaries

- Standard-part semantics are CAD/package evidence, not proof of preload,
  contact, fatigue life, supplier equivalence, or procurement validity.
- Clearance-hole and bolt-pattern recognition do not imply that assembly
  constraints or solver contact pairs exist.
- Missing material must be reported as missing or blank; it must not be guessed.
- This pack is suitable for regression and demos, not production sign-off.
