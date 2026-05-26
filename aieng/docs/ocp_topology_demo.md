# Optional OCP Topology Demo

This page documents the **optional, experimental** OCP-based real STEP topology extraction demo for `.aieng`.

This is **separate** from the mock reference demo. The mock backend remains the default and requires no geometry dependency.

---

## Purpose

Demonstrate that `aieng extract-topology --backend occ` can parse real STEP geometry and produce a `geometry/topology_map.json` with `real_step_parsing: true` when OCP/CadQuery is installed.

This is a Phase 7B.2 experimental spike. Results are not production-certified.

---

## Requirements

- `aieng-format` installed (`pip install -e .` or equivalent)
- OCP/CadQuery runtime: `pip install cadquery`
- A **real** STEP file (`.step` or `.stp`) containing solid geometry from a CAD application

> **Note:** The `examples/bracket.step` fixture in this repository is a minimal mock fixture with no real geometry. It is used by the mock reference demo. For this OCP demo you need a real STEP file — one exported from a CAD system such as FreeCAD, Fusion 360, SolidWorks, or similar.

---

## Check backend availability

```bash
aieng geometry-backends
```

**When OCP is installed:**
```text
Geometry backends:
  mock: available
  occ: runtime detected (OCP/CadQuery) — experimental real STEP extraction available (Phase 7B.2)
```

**When OCP is not installed:**
```text
Geometry backends:
  mock: available
  occ: not available — No supported OCC runtime found. Install pythonocc-core or OCP/CadQuery.
```

If the `occ` line shows `not available`, install CadQuery and try again:
```bash
pip install cadquery
```

---

## Demo steps

### 1. Import STEP

```bash
aieng import-step path/to/model.step --out build/ocp_topology_demo.aieng --overwrite
```

### 2. Extract topology (OCP backend)

```bash
aieng extract-topology build/ocp_topology_demo.aieng --backend occ --overwrite
```

### 3. Update validation status

```bash
aieng update-validation-status build/ocp_topology_demo.aieng --overwrite
```

### 4. Validate

```bash
aieng validate build/ocp_topology_demo.aieng
```

---

## What to inspect

The `.aieng` package is a zip file. Inspect its contents with any zip tool or with Python:

```python
import zipfile, json, yaml
with zipfile.ZipFile("build/ocp_topology_demo.aieng") as zf:
    topo = json.loads(zf.read("geometry/topology_map.json"))
    status = yaml.safe_load(zf.read("validation/status.yaml"))
```

### geometry/topology_map.json

| Field | Expected value |
|-------|---------------|
| `metadata.extraction_backend` | `"occ"` |
| `metadata.runtime_provider` | `"OCP"` |
| `metadata.extraction_mode` | `"parsed_from_step"` |
| `metadata.real_step_parsing` | `true` |
| `metadata.phase` | `"7B.2"` |
| `entities` | List of `solid`, `face`, and `edge` entities from the real STEP file |

Face entities include `surface_type` (`"plane"`, `"cylinder"`, or `"other"`), `area`, `bounding_box`, and `normal`/`radius`/`axis` where applicable.

### validation/status.yaml

| Field | Expected value |
|-------|---------------|
| `topology_status.extraction_mode` | `"parsed_from_step"` |
| `topology_status.status` | `"experimental_real_extraction"` |
| `topology_status.real_step_parsing` | `true` |
| `topology_status.runtime_provider` | `"OCP"` |
| `topology_status.warning` | States geometry validity is not fully certified |

---

## Expected topology_map.json metadata

```json
{
  "metadata": {
    "extraction_backend": "occ",
    "runtime_provider": "OCP",
    "extraction_mode": "parsed_from_step",
    "real_step_parsing": true,
    "source_geometry": "geometry/normalized.step",
    "phase": "7B.2",
    "limitations": [
      "experimental OCP-based topology extraction",
      "stable IDs are deterministic only for this backend traversal order",
      "feature recognition remains separate and rule-based",
      "geometry validity is not fully certified"
    ]
  }
}
```

---

## Limitations

| Limitation | Detail |
|-----------|--------|
| Experimental only | Not production-certified; use the mock backend for stable pipelines |
| No persistent naming | IDs (`body_001`, `face_001`, ...) are assigned by traversal order; they change when geometry is modified |
| Deterministic traversal IDs only | Stable for the same file and backend version; not linked to STEP product names or B-rep persistent IDs |
| Partial geometry attributes | Some surface types beyond plane and cylinder are classified as `"other"`; `adjacent_entity_ids` and `edge_ids` are not populated |
| No geometry validity certification | Watertightness, self-intersections, degenerate faces, and manufacturing feasibility are not checked |
| Feature recognition is separate | The OCP backend emits topology IDs only; feature classification runs separately via `aieng recognize-features` (still rule-based and candidate-only) |
| No mesh or solver run | This demo extracts topology only; meshing and solving are not implemented in any phase |

---

## Running the optional demo script

A convenience script is provided that checks OCP availability and runs the demo chain if OCP is installed:

```bash
python scripts/run_ocp_topology_demo.py path/to/model.step
```

The script exits cleanly with a skip message if OCP is not installed. It does not modify any existing package or reference demo output.

**Output directory:** `build/ocp_topology_demo.aieng`

---

## Relationship to the mock reference demo

The mock reference demo ([docs/demo_walkthrough.md](demo_walkthrough.md)) uses `--backend mock` (the default). It requires no OCP dependency and is the primary reference scenario. This OCP demo is an **optional add-on** that exercises the experimental real-STEP extraction path for users who have CadQuery installed and want to compare topology output between mock and real backends.

| | Mock reference demo | OCP topology demo |
|-|---------------------|-------------------|
| Backend | `mock` (default) | `occ` (experimental) |
| STEP fixture | `examples/bracket.step` (mock fixture) | User-supplied real STEP |
| OCP required | No | Yes |
| Feature recognition | Yes (rule-based candidates) | Not in this demo |
| `real_step_parsing` | `false` | `true` |
| Production-certified | Format pipeline only | No |
