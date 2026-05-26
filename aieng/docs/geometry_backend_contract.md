# Geometry Backend Contract

This document defines the contract that all geometry backends must satisfy when producing a `geometry/topology_map.json` for an `.aieng` package.

---

## Purpose

A geometry backend converts source geometry resources — specifically `geometry/normalized.step` bytes — into a topology map that the rest of the `.aieng` pipeline can reference by stable ID.

The backend's responsibility is narrow:

- Extract or generate topology and geometric facts from the input geometry bytes.
- Emit stable, typed entity IDs that downstream resources (feature graphs, constraints, simulation setup, patches) can reference.

The backend must not decide engineering intent. It must not classify features, assign materials, infer load paths, identify protected regions, or make simulation assumptions. Those decisions belong to later pipeline stages:

- **Feature classification** happens in `aieng recognize-features`, which reads `geometry/topology_map.json` and applies rule-based heuristics.
- **Engineering context** is supplied by the user via `aieng apply-context` and a YAML file.
- **Simulation intent** is a user concern, not a geometry-parsing concern.

---

## Current backend status

| Backend | Name | Status | Real STEP parsing |
|---------|------|--------|------------------|
| `MockGeometryBackend` | `mock` | Implemented — default | No |
| `OCCGeometryBackend` | `occ` | Experimental (Phase 7B.2): OCP/CadQuery-based real STEP extraction | Yes, when OCP installed |

The `mock` backend is always available and is the default for all commands. No CAD kernel dependency is required for the default install.

Phase 7B.1 added `detect_occ_runtime()` and `aieng geometry-backends`. Phase 7B.2 implements real STEP extraction in `OCCGeometryBackend` using OCP (CadQuery). The implementation is a spike — experimental and not production-certified. Feature recognition remains separate (rule-based). pythonocc-core is detected but not yet implemented; OCP/CadQuery is required for real extraction. Install: `pip install cadquery`. The `[geometry]` optional extra in `pyproject.toml` is declared but not populated due to cross-platform install variability.

---

## Backend interface

All geometry backends must satisfy the `GeometryBackend` Protocol defined in `src/aieng/geometry/backend.py`:

```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class GeometryBackend(Protocol):
    name: str

    def extract_topology(self, normalized_step_bytes: bytes) -> dict[str, Any]:
        """Return a topology map dict for normalized STEP bytes.

        The returned dict must conform to schemas/topology_map.schema.json.
        """
```

**`name`** must be a non-empty string that uniquely identifies the backend (e.g. `"mock"`, `"occ"`). It is used in `SUPPORTED_BACKENDS`, the `--backend` CLI flag, and topology map metadata.

**`extract_topology`** receives the raw bytes of `geometry/normalized.step` and returns a dict conforming to `schemas/topology_map.schema.json`. The dict must be JSON-serializable.

Backends are selected by name at call time via `get_backend(name)` or the `--backend` CLI flag on `aieng extract-topology`. The default backend when no name is specified is `MockGeometryBackend`.

---

## Supported backends today

### `mock` (default)

Implemented in `MockGeometryBackend`. Does not read or parse `normalized_step_bytes`. Returns a deterministic fixed bracket-like topology map containing one solid body, six planar faces, four cylindrical faces, and two edges. Stable IDs are hard-coded. This backend is suitable for testing `.aieng` format semantics and the downstream pipeline; it does not reflect real geometry.

### `occ` (experimental — Phase 7B.2)

Implemented in `OCCGeometryBackend`. In Phase 7B.2, `extract_topology()` calls `detect_occ_runtime()` and branches:
- No OCC runtime → raises `NotImplementedError` with a `pip install cadquery` hint.
- pythonocc-core detected (but not OCP) → raises `NotImplementedError` explaining that Phase 7B.2 requires OCP/CadQuery.
- OCP detected → calls `_extract_topology_ocp()`, which performs real STEP extraction using `STEPControl_Reader`, `TopExp_Explorer`, and face geometry adapters.

All OCP imports are lazy (inside function bodies). The default backend remains `mock`. This implementation is an experimental spike and must not be treated as production-certified geometry validation.

---

## Required topology_map.json output shape

The dict returned by `extract_topology` must conform to `schemas/topology_map.schema.json`. The top-level shape is:

```json
{
  "format_version": "0.1.0",
  "metadata": { ... },
  "entities": [ ... ]
}
```

**`format_version`** must be the string `"0.1.0"`. It is validated by `aieng validate` against the schema `const` constraint.

**`metadata`** must be a JSON object. It is optional in the schema but required by this contract for all backends. See [Required metadata fields](#required-metadata-fields).

**`entities`** must be a non-empty JSON array of topology entity objects. Each entity must have at minimum an `"id"` string and a `"type"` string from the allowed set. See [Entity requirements](#entity-requirements).

---

## Required metadata fields

Every backend must include a `metadata` object containing at least the following fields:

```json
{
  "metadata": {
    "extraction_backend": "mock",
    "extraction_mode": "mock_generated",
    "real_step_parsing": false,
    "source_geometry": "geometry/normalized.step"
  }
}
```

| Field | Type | Required value rules |
|-------|------|---------------------|
| `extraction_backend` | string | The backend `name` value (e.g. `"mock"`, `"occ"`) |
| `extraction_mode` | string | `"mock_generated"` for mock; `"parsed_from_step"` for real backends |
| `real_step_parsing` | boolean | `false` for mock; `true` for any backend that actually parses STEP bytes |
| `source_geometry` | string | Path within the package; must be `"geometry/normalized.step"` |

For real backends (Phase 7B and later):

- `real_step_parsing` must be `true`.
- `extraction_mode` must not be `"mock_generated"`.
- `extractor` (optional convenience field) should name the implementing class.

Additional metadata fields such as `limitations`, `kernel_version`, `kernel_id`, `extraction_timestamp`, and `confidence` are allowed and encouraged. The schema permits `additionalProperties: true` on the metadata object.

`aieng validate` performs soft WARN-level checks: it warns if `extraction_backend` is not a string or if `real_step_parsing` is not a boolean. These are not FAIL-level errors so that packages produced before Phase 7A remain valid.

---

## Entity requirements

### Allowed entity types

The `"type"` field of each entity must be one of the following values, as defined in `schemas/topology_map.schema.json`:

| Type | Description |
|------|-------------|
| `solid` | A closed volumetric body |
| `shell` | An open or closed shell (collection of faces) |
| `face` | A bounded surface region |
| `wire` | A closed or open loop of edges |
| `edge` | A bounded curve segment |
| `vertex` | A point |

### Required fields by type

The validator (`aieng validate`) enforces type-specific required fields:

| Type | Required fields |
|------|----------------|
| `solid` | `id`, `type`, `bounding_box` |
| `shell` | `id`, `type`, `bounding_box` |
| `face` | `id`, `type`, `surface_type`, `bounding_box`, `area` |
| `edge` | `id`, `type`, `bounding_box` |
| `wire` | `id`, `type`, `bounding_box` |
| `vertex` | `id`, `type`, `bounding_box` |

### Surface-type-specific fields for faces

| `surface_type` | Additional required fields |
|----------------|--------------------------|
| `plane` | `normal` — 3-element numeric array `[nx, ny, nz]` |
| `cylinder` | `radius` — positive number; `axis` — 3-element numeric array |
| other | No additional requirements beyond `surface_type` being present |

### Adjacency

Backends should populate `adjacent_entity_ids` where topology adjacency is known. This enables downstream feature recognition to identify connected components. Adjacency must only reference IDs that exist in the same `entities` array; the validator enforces this constraint.

### What backends should populate when available

For **faces**:
- `id`, `type`, `surface_type`, `area`, `bounding_box`
- `normal` for planes, `radius` and `axis` for cylinders
- `body_id` referencing the containing solid
- `adjacent_entity_ids` listing adjacent face and edge IDs
- `edge_ids` listing bounding edge IDs

For **edges**:
- `id`, `type`, `curve_type`, `bounding_box`
- `body_id` referencing the containing solid
- `adjacent_entity_ids` listing adjacent face IDs

For **solids**:
- `id`, `type`, `bounding_box`
- `name` (optional but helpful for AI readability)
- `face_ids` listing contained face IDs

---

## Stable ID expectations

IDs must be stable for a given input and backend version, meaning that calling `extract_topology` twice on the same bytes must produce the same IDs. IDs must not be random, UUID-based, or dependent on arbitrary iteration order.

For v0.1.0, the stability guarantee is:

- **Mock backend**: IDs are hard-coded strings (e.g. `"face_base_top"`, `"body_001"`). They never change for a given backend version.
- **Real backends (future)**: IDs should combine entity type, an ordered index from a stable traversal, and a geometric signature (e.g. surface type, bounding-box centroid rounded to a tolerance). The exact normalization strategy is a Phase 7B design decision.

Stable IDs across major geometry edits (e.g. adding or removing a hole) are a future goal and are not guaranteed in v0.1.0. Feature-graph and constraint resources that reference topology IDs will need to be regenerated when topology changes significantly.

All entity IDs within a single topology map must be unique. The validator enforces this.

---

## Geometry reference rules

The topology map is the bridge between raw geometry and the rest of the `.aieng` pipeline. All downstream resources must reference IDs from `geometry/topology_map.json`:

- **Feature graphs** (`graph/feature_graph.json`) must reference topology entity IDs via `geometry_refs`. The validator checks that all referenced IDs exist in the topology map.
- **Constraints** (`graph/constraints.json`) target feature IDs (not raw topology IDs), because constraints operate on engineering features, not geometry primitives.
- **Simulation setup** (`simulation/setup.yaml`) references feature IDs for boundary conditions and loads.
- **Protected regions** (`ai/protected_regions.json`) reference feature IDs.

**Backends must not emit feature IDs.** Topology IDs are geometry primitives (faces, edges, bodies). Feature IDs are assigned by the feature recognition step. Mixing these would couple the backend to engineering intent, which is explicitly out of scope.

---

## Mock backend limitations

`MockGeometryBackend` is a fixture for format validation and pipeline testing. It has the following known limitations:

- It does not read or interpret `normalized_step_bytes`. Any STEP content (including invalid bytes) produces the same output.
- It emits a fixed bracket-like topology: one solid, six planar faces, four cylindrical faces, and two edges. This topology does not correspond to real bracket geometry.
- IDs are meaningful by convention only (`face_base_top`, `face_hole_001_cyl`) and are not derived from CAD kernel persistent naming.
- The mock topology is useful for testing `.aieng` format semantics, cross-resource ID integrity, feature recognition heuristics, and downstream command behavior. It is not useful for evaluating real geometry understanding.

---

## Phase 7B.2 OCC backend spike

The `OCCGeometryBackend` has been implemented as an experimental spike in Phase 7B.2. It is not production-certified.

### What it does (Phase 7B.2)

- Accepts `normalized_step_bytes: bytes`, writes to a temp file, reads with `OCP.STEPControl.STEPControl_Reader`.
- Traverses solids, faces, and edges using `OCP.TopExp.TopExp_Explorer`.
- For each solid: emits `id`, `type`, `bounding_box` (if computable).
- For each face: emits `id`, `type`, `body_id`, `bounding_box`, `area` (via `BRepGProp`), `surface_type` (`plane`/`cylinder`/`other` via `GeomAdaptor_Surface`), `normal` for planes, `radius` and `axis` for cylinders.
- For each edge: emits `id`, `type`, `bounding_box`.
- Sets metadata: `extraction_backend: "occ"`, `runtime_provider: "OCP"`, `extraction_mode: "parsed_from_step"`, `real_step_parsing: true`, `phase: "7B.2"`, `limitations: [...]`.
- Requires `pip install cadquery`. Not included in core install. pythonocc-core is detected but raises `NotImplementedError` (use OCP/CadQuery instead).

### Required metadata for Phase 7B.2 OCP extraction

```json
{
  "metadata": {
    "extraction_backend": "occ",
    "runtime_provider": "OCP",
    "extraction_mode": "parsed_from_step",
    "real_step_parsing": true,
    "source_geometry": "geometry/normalized.step",
    "phase": "7B.2",
    "limitations": [...]
  }
}
```

### Phase 7B.2 limitations

- **Deterministic traversal IDs only.** IDs (`body_001`, `face_001`, ...) are assigned in `TopExp_Explorer` traversal order. They are stable for the same file and backend version but are not derived from CAD kernel persistent naming and will change if geometry is modified.
- **No persistent naming.** IDs are not linked to STEP product names or B-rep persistent IDs.
- **Partial surface and edge attributes.** Properties are omitted rather than invented when the OCP API call fails. Not all surface types beyond plane, cylinder, and "other" are classified.
- **No adjacency data.** `adjacent_entity_ids` and `edge_ids` are not populated in Phase 7B.2.
- **Feature recognition is separate.** The backend emits topology IDs only. Feature classification (holes, base plate, ribs) remains in `aieng recognize-features`.
- **Geometry validity is not certified.** The backend reads STEP and traverses topology. It does not check watertightness, self-intersections, degenerate faces, or manufacturing feasibility.
- **Not production-grade.** This is a spike implementation. Real production use requires persistent naming, adjacency, validated stability across kernel versions, and integration testing on a broad STEP corpus.

### What the OCC backend must not do (unchanged)

See [What a backend must not do](#what-a-backend-must-not-do). The Phase 7B.2 implementation respects all of these constraints.

---

## Error handling rules

| Situation | Required behavior |
|-----------|------------------|
| Backend name not in `SUPPORTED_BACKENDS` | Raise `ValueError` with message containing the unknown name and listing supported backends |
| Backend not yet implemented (e.g. OCC placeholder) | Raise `NotImplementedError` with a message identifying the backend as a placeholder |
| STEP bytes are invalid (real backends only) | Raise a descriptive exception; do not return a partial or empty topology map |
| STEP bytes are empty (real backends only) | Raise `ValueError` with a message indicating empty input |
| Mock backend: any STEP bytes | Always succeed; STEP bytes are ignored |

The CLI handler for `aieng extract-topology` catches `NotImplementedError` and returns exit code 2 with a `FAIL` message. It also catches `ValueError` and `FileNotFoundError` for the same treatment. Any unhandled exception from a backend propagates as an unexpected error.

---

## Testing requirements

### Mock backend (mandatory, already implemented)

Tests must verify:

- `MockGeometryBackend().extract_topology(b"any")` returns a dict with `format_version == "0.1.0"`.
- `metadata.extraction_backend == "mock"`.
- `metadata.real_step_parsing is False`.
- `metadata.extraction_mode == "mock_generated"`.
- `metadata.source_geometry == "geometry/normalized.step"`.
- All returned entities have non-empty string IDs.
- All returned entity IDs are unique.
- The returned dict conforms to `schemas/topology_map.schema.json`.
- Two calls with different input bytes produce the same entities.

### OCC backend (updated Phase 7B.2)

Tests must verify:

- When no OCC runtime is installed: raises `NotImplementedError` containing `"OCC"` and an install hint (`"cadquery"` or `"install"`).
- When pythonocc-core is detected (not OCP): raises `NotImplementedError` mentioning `"pythonocc-core"` and instructing the user to install CadQuery.
- When OCP is installed: `extract_topology(bytes)` succeeds and returns a dict conforming to the schema.
- OCP imports are lazy — importing `aieng.geometry.backend` must not trigger any `OCP.*` module imports.

### OCC backend real implementation (Phase 7B)

When Phase 7B implements real STEP parsing, tests must additionally verify:

- `metadata.real_step_parsing is True`.
- `metadata.extraction_mode == "parsed_from_step"`.
- Output conforms to `schemas/topology_map.schema.json`.
- Two calls on the same bytes produce identical entity IDs.
- At least one solid entity is present for a single-body STEP file.
- Face entities have `surface_type`, `bounding_box`, and `area`.
- Cylindrical faces have `radius` and `axis`.
- Planar faces have `normal`.
- Tests are guarded by `pytest.importorskip` for the OCC dependency.

### `get_backend` (mandatory, already implemented)

Tests must verify:

- `get_backend("mock")` returns a `MockGeometryBackend`.
- `get_backend("occ")` returns an `OCCGeometryBackend`.
- `get_backend("unknown")` raises `ValueError` listing supported backends.

---

## What a backend must not do

A geometry backend must not:

- **Infer design intent.** It must not decide whether a cylindrical face is a bolt hole, a pin locator, or a bearing bore.
- **Classify engineering features.** Feature classification (base plate, hole pattern, rib) belongs to `recognize-features`.
- **Assign protected regions.** Protection decisions are user-provided via `apply-context`.
- **Assign material properties.** Material is user-provided context, not a geometry property.
- **Invent simulation setup.** Boundary conditions, loads, and targets are user-provided.
- **Claim geometry validity without evidence.** A backend must not assert that geometry is watertight, manufacturable, or solver-ready unless it actually checks these properties.
- **Run a mesher or solver.** Meshing and solving are explicit downstream steps.
- **Emit feature IDs.** Only topology IDs are in scope for a backend.
- **Return partial results silently.** If parsing fails, the backend must raise an exception, not return an empty or truncated topology map.
- **Mutate the input bytes.** The backend receives bytes as read-only input.

---

## Future extensions

The following capabilities may be added in later phases without breaking this contract:

- **Persistent naming** — a stable naming convention that maps OCC entity indices to human-readable names derived from STEP `PRODUCT_DEFINITION` or BREP naming, for use when topology IDs must survive minor geometry edits.
- **Confidence scores** — a numeric confidence field on entity metadata (e.g. `"surface_type_confidence": 0.95`) to indicate uncertainty from real-geometry heuristics.
- **Multiple body support** — topology maps today assume a single dominant body. Future backends may enumerate multiple solids and index them.
- **Visual index integration** — backends may emit visual selection hints (e.g. face centroid, display color index) that link topology entities to glTF mesh nodes for Phase 8.
- **Normalization layer** — a post-processing step that converts raw CAD kernel IDs to stable `.aieng` topology IDs, ensuring consistency across kernel versions.
- **Backend versioning** — `metadata.backend_version` to record the backend release, enabling reproducibility checks.
