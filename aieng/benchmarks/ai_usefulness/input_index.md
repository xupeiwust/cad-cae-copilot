# Input Index — AI Usefulness Benchmark

This file describes what to provide to the AI in each benchmark condition, and how
to prepare the inputs.

---

## Conditions

### Condition A — without `.aieng`

Provide the AI with raw source files **only**. Do not provide any `.aieng` package
resources, structured JSON/YAML resources, README_FOR_AI.md, or coverage categories.

| Track | Raw input to provide |
|-------|---------------------|
| A (CAD Understanding) | FCStd Document.xml text (from the FCStd zip), truncated to object definitions only |
| B (CAD Reconstruction) | FCStd Document.xml text with object names, types, and numeric properties |
| C (FEM Preprocessing) | FCStd Document.xml text, or STEP file geometry description (no annotations) |
| D (CAE Deck) | Raw solver deck text (`.inp` file for CalculiX, or equivalent) |

**How to extract Document.xml from an FCStd file:**

```bash
python -c "
import zipfile
with zipfile.ZipFile('examples/sample_bracket.FCStd') as z:
    print(z.read('Document.xml').decode())
"
```

### Condition B — with `.aieng`

First convert the source to a `.aieng` package:

```bash
aieng convert examples/sample_bracket.FCStd --out sample_bracket.aieng
```

Then provide the AI with the following package resources (extracted or provided inline):

| Resource | Always include | Track-specific |
|----------|:--------------:|:---------------:|
| `README_FOR_AI.md` | ✓ | |
| `provenance/conversion_manifest.json` | ✓ | |
| `validation/completeness_report.json` | ✓ | |
| `graph/feature_graph.json` | ✓ | A, B, C |
| `objects/object_registry.json` | ✓ | A, B |
| `manifest.json` | ✓ | |
| `simulation/setup.yaml` | | D |
| `simulation/cae_mapping.json` | | D |
| `task/external_tool_requirements.json` | | C |

**How to extract resources from a `.aieng` package:**

```bash
python -c "
import zipfile, json
with zipfile.ZipFile('sample_bracket.aieng') as z:
    for name in z.namelist():
        print(name)
"
```

Or extract all to a directory:

```bash
python -c "
import zipfile
with zipfile.ZipFile('sample_bracket.aieng') as z:
    z.extractall('sample_bracket_contents/')
"
```

---

## Reference inputs

### Tracks A and B

Primary reference: `examples/sample_bracket.FCStd` (included in the repository).

This is a synthetic FCStd fixture with four objects:
- `Plate` — `Part::Box` (base plate)
- `MountingHole_1`, `MountingHole_2` — `PartDesign::Hole`
- `Flange_Top` — `PartDesign::Pad`

After conversion, the package contains:
- 4 feature candidates in `graph/feature_graph.json`
- 4 objects in `objects/object_registry.json`
- All 15 coverage categories in `provenance/conversion_manifest.json`
- `geometry: missing`, `topology: missing` (offline mode)
- `object_registry: complete`, `features: partial`, `parameters: partial`

### Tracks C and D

For FEM preprocessing and CAE deck understanding, the reference input requires a
package that has been extended beyond the basic FreeCAD conversion. Options:

1. **Extend the bracket package** using existing CLI commands before benchmarking:
   ```bash
   aieng write-task-spec sample_bracket.aieng
   aieng write-external-tool-requirements sample_bracket.aieng
   aieng write-evidence-scaffold sample_bracket.aieng
   ```

2. **Use the STEP-based bracket package** (`examples/bracket.step` + `aieng import-step`
   + further CLI commands) for richer geometry information.

3. **Use a fully prepared benchmark pack** generated via:
   ```bash
   python scripts/prepare_real_benchmark_pack.py
   ```
   (requires the `[geometry]` extra: `pip install -e ".[geometry]"`)

---

## What to exclude during the benchmark session

Confirm the following are excluded before starting:

- [ ] MCP tool calls
- [ ] RAG or retrieval augmentation
- [ ] Skills, plugins, or LLM fine-tuning
- [ ] External CAD tool calls
- [ ] External CAE tool calls (CalculiX, Abaqus, Gmsh, etc.)
- [ ] Solver execution or result generation
- [ ] LLM API calls beyond prompting with the designated input files
- [ ] In Condition A: any `.aieng` package resources
- [ ] In Condition B: the raw FCStd, STEP, or solver deck files

---

## Notes on FreeCAD availability

The benchmark does **not** require FreeCAD to be installed. The reference converter
runs in offline mode (pure Python, FCStd zip parsing). If FreeCAD is installed,
the converter can additionally export STEP geometry, but this is not required for
the benchmark.
