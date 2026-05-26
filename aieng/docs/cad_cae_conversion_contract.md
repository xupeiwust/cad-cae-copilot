# General CAD/CAE-to-`.aieng` Conversion Contract

This document defines the general contract that any CAD/CAE-to-`.aieng` converter must follow.

It is the partner of `docs/cad_cae_emitter_contract.md`. The emitter contract describes the broader CAD/CAE-side semantic export *and writeback* surface; this conversion contract is the narrower, converter-only specification that governs how a one-shot **CAD/CAE source -> `.aieng` package** conversion must be expressed.

## Core positioning (non-negotiable)

`.aieng` is a CAD/CAE-to-AI semantic conversion and packaging format.

It is **not** an automation runtime. It is **not** an agent framework. It does not execute CAD or CAE operations. It does not run solvers, meshers, optimizers, or CAD edits. It does not make engineering decisions.

A converter that follows this contract must:

1. Read a CAD/CAE source artifact (or set of artifacts).
2. Convert whatever information is actually available into structured `.aieng` resources.
3. Mark missing, unknown, partial, unsupported, or conflicting information explicitly.
4. Record its own capability profile and the per-conversion outcome in machine-readable form.
5. Refuse to fabricate engineering facts, solver evidence, mesh evidence, or geometry-modification evidence.
6. Refuse to call solvers, meshers, optimizers, or CAD edit operations as part of conversion.

Conversion is **read-only with respect to engineering decisions**. Writing structured semantic state, completeness state, and provenance is the converter's job. Deciding what to *do* with that state is the consumer's job.

## Capability levels

A converter declares which capability levels it can honestly support against a given source. Higher levels include lower-level capabilities where applicable, but a converter does not have to support all levels.

| Level | Name | What the converter promises | Typical `.aieng` resources |
|---:|---|---|---|
| L0 | Source / package metadata only | Attach source artifact references and basic package metadata | `manifest.json`, `geometry/source.*` (if any), `provenance/conversion_manifest.json`, `validation/completeness_report.json` |
| L1 | Geometry and topology extraction | Emit stable face / edge / body topology references from real source geometry | `geometry/topology_map.json`, optional `geometry/source.step` |
| L2 | Object registry and stable references | Emit cross-resource object index with `@aieng[...]` resolvable references | `objects/object_registry.json`, references inside the resources above |
| L3 | Feature-aware export | Emit feature candidates or confirmed features when source semantics are available or recoverable from named selections, feature trees, MBD/PMI, or naming heuristics | `graph/feature_graph.json`, optional `graph/aag.json`, optional `ai/protected_regions.json` |
| L4 | Editability metadata | Record `parameter_source`, `editability`, and `writeback_strategy` for editable parameters, **without** performing edits | `graph/feature_graph.json` editability fields, `graph/allowed_operations_catalog.json` |
| L5 | Round-trip writeback metadata | Describe what writeback strategy would apply (e.g. `cadquery_regeneration`, `freecad_parametric`) so external tools can later execute it, **without** the converter executing writeback | `graph/feature_graph.json` with `editability: executable_by_regeneration`, related allowed operations |

Critical rules at L4 and L5:

- The converter only **records** editability and writeback strategy. It does not perform the edit, regeneration, or optimization.
- Execution belongs to external CAD/CAE tools and to adapters built on top of `.aieng`. The converter is not allowed to run them.

A converter that does not support a level for a given source MUST NOT emit the resources for that level. It must instead record the absence as explicit missingness in `validation/completeness_report.json`.

## The conversion manifest

Every conversion produces one machine-readable manifest:

```
provenance/conversion_manifest.json
```

This is the converter's per-package report. It records:

1. The converter that ran (id, version, source system name).
2. The source artifact(s) consumed, including filename, byte size, and content hash.
3. **`coverage_categories` — the primary adaptive interface.** A per-category record of
   what this specific conversion run captured, inferred, or could not extract. Coverage
   categories are independent of any fixed capability level; they describe what was
   *actually found* in the source. See below for the full category list and status values.
4. The `.aieng` resources the converter emitted.
5. Unsupported or unavailable data items, recorded as `unsupported` / `missing` / `unknown` / `partial` with structured notes.
6. Uncertainty notes for any heuristic recognition (e.g. "object name 'MountingHole_1' was interpreted as a mounting-hole candidate; CAD did not annotated this explicitly").
7. A `claim_policy` block that mirrors the core boundary (best-effort conversion, missingness explicit, do-not-infer, unsupported-is-not-false, external-tools-execute, `.aieng` core does not execute external tools).
8. Optionally: `declared_capability_levels` / `achieved_capability_levels` as shorthand for implementations that also want to communicate in terms of L0–L5 levels.

### Coverage categories

The `coverage_categories` array is the primary output of a conversion run. Each entry
describes one semantic category, what was captured, and what was not.

**Category names** (must exactly match the schema enum):

| Category | Typical source |
|----------|---------------|
| `geometry` | B-rep STEP / native kernel export |
| `topology` | OCC topology extraction (face/edge/body IDs) |
| `object_registry` | Feature tree, part list, component hierarchy |
| `stable_references` | Persistent entity IDs from source (not heuristic slugs) |
| `features` | Feature tree, PMI/MBD annotations, naming heuristics |
| `parameters` | Parametric model values, property sheets |
| `assemblies` | Assembly structure, mate/constraint definitions |
| `materials` | Material cards, property assignments |
| `loads` | Applied loads, force/pressure/temperature distributions |
| `boundary_conditions` | Fixed supports, symmetry planes, thermal boundaries |
| `mesh` | Pre-existing mesh (e.g. from a CAE file) |
| `solver_deck` | Solver input deck (Abaqus `.inp`, Nastran `.bdf`, etc.) |
| `cad_cae_mappings` | Named-selection-to-solver-BC associations |
| `editability_metadata` | `parameter_source`, `editability`, `writeback_strategy` fields |
| `writeback_metadata` | Roundtrip rebuild strategy (L5 writeback contract) |

**Status values** (`status` field):

| Status | Meaning |
|--------|---------|
| `complete` | All expected content for this category was extracted |
| `partial` | Some content extracted; some items were unavailable |
| `inferred` | Content was inferred by heuristic, not confirmed by the source |
| `missing` | Category expected but not present in source or not extractable |
| `unsupported` | Converter does not support this category at all |
| `unavailable_in_source` | Source did not contain this category (not a converter limitation) |
| `unknown` | Converter could not determine whether content was present |

The schema is `schemas/conversion_manifest.schema.json`.

## The converter capabilities profile (optional)

A converter implementation MAY also publish a static capabilities profile separate from any single conversion, for example as a registry entry or a sidecar file consumed by `aieng converter-capabilities`.

The schema is `schemas/converter_capabilities.schema.json`.

This profile is a *generic* declaration of what a given converter supports, independent of any one source file. The per-conversion manifest still records what was *actually* achieved in that run.

## Source mode in `manifest.json`

A package produced by a converter sets `source_mode` accordingly:

- `step` — STEP file was imported as the geometry source.
- `definition` — package was created from a structured definition with no CAD source.
- `converter` — package was produced by a registered CAD/CAE-to-`.aieng` converter against a CAD-side source (FCStd, OnshapeJSON, NX session export, etc.). Details live in `provenance/conversion_manifest.json`.

`source_mode: converter` is a new value introduced by Phase 20. It is permitted alongside the existing `step` and `definition` values.

## Completeness category

`validation/completeness_report.json` carries a new category, `source_conversion`, that records:

- which converter produced the package;
- the maximum capability level the converter declared it could reach with the given source;
- the maximum capability level it actually reached;
- whether `provenance/conversion_manifest.json` is present.

This means an AI reading the completeness report alone (without opening the conversion manifest) can still see whether the package was converter-sourced, and at what fidelity.

## Forbidden converter behavior

A converter implementing this contract MUST NOT:

- run a mesher, solver, optimizer, or simulation;
- execute CAD edits, regenerate geometry, or rewrite the source file;
- propose engineering decisions (mass reduction, material change, etc.);
- mark solver, mesh, or geometry-modification claims as `pass`;
- silently fill missing engineering data with defaults;
- treat heuristic recognition (e.g. "the object is named 'hole'") as confirmed feature truth without flagging it as a candidate with uncertainty;
- conflate "source did not provide this" with "this is false" — the package must use `unsupported`, `missing`, `partial`, or `unknown` per the existing completeness/claim policy.

A converter MAY:

- read source CAD/CAE files;
- export source artifacts into `geometry/source.*` for traceability;
- emit topology, features, parameters, registry, and editability metadata at the levels it honestly supports;
- record per-conversion uncertainty and missingness;
- update `validation/completeness_report.json` to reflect what is now in the package.

## Validation expectations

After a converter writes the package, the standard verification chain still applies:

```bash
aieng write-completeness-report model.aieng --overwrite
aieng summarize model.aieng --overwrite
aieng validate model.aieng
```

The converter itself does not have to call these; an integration script or downstream pipeline can. The point is that converter-produced packages are not exempt from the validator. A converter that emits a package which fails `aieng validate` is buggy.

## Reference converters

Phase 20 ships one reference converter:

- **FreeCAD reference converter** (`src/aieng/converters/freecad.py`). Reads FCStd files. Operates in two modes:
  - *Offline mode* — parses the FCStd archive directly (FCStd is a zip with `Document.xml`); requires no FreeCAD installation. Supports L0 + L2 + L3-candidate based on Document.xml object names/types and parameters.
  - *Runtime mode* — uses the FreeCAD Python API when available; can additionally reach L1 (topology) by routing through the OCC backend on an exported STEP. Optional and gated by detection; no hard dependency.

The FreeCAD converter is a reference implementation. It is intentionally not a universal CAD emitter. Other converters (NX, SolidWorks, CATIA, Onshape, FCStd via a different parser, etc.) should follow the same contract but live in their own modules or external repositories.
