# Agentic CAD/CAE Blueprint

> Working draft. This document describes the long-term direction for `.aieng`, CAD/CAE adapters, and agent-assisted engineering workflows. It should evolve as the project matures.

---

## 1. Vision

`.aieng` aims to make CAD/CAE engineering projects **agent-readable, agent-actionable, and audit-friendly**.

It does this by turning raw engineering artifacts into repository-like semantic and evidence packages, while MCP adapters provide controlled execution paths into CAD/CAE tools.

In simple terms:

```text
.aieng = engineering context and evidence layer
MCP adapters = controlled execution layer
CAD/CAE tools = modeling, meshing, solving, visualization environments
Agents = assistants that inspect, propose, execute bounded operations, and support review
```

The goal is not to build an uncontrolled autonomous CAD/CAE agent.

The goal is to help agents understand engineering context, perform bounded actions, record evidence, and support human review.

---

## 2. Repository Analogy

A software agent understands a codebase by reading files, tests, logs, docs, history, and issues.

CAD/CAE projects are often harder for agents because key information is hidden inside binary CAD files, solver decks, screenshots, meshes, or human design intent.

`.aieng` adds a repository-like layer around CAD/CAE projects.

| Software Repository | `.aieng` Engineering Package |
|---|---|
| README / docs | task specs, design intent, context |
| source files | CAD/CAE resources and artifacts |
| config files | parameters, constraints, manifest |
| tests | evidence records and acceptance criteria |
| CI logs | tool traces, solver traces, execution logs |
| issues / review comments | missingness, unsupported states, `needs_review` |
| pull requests | patch proposals and controlled edits |
| commit history | provenance and trace records |
| test status | claim map, updated only through explicit review |

This analogy is useful, but not perfect.

In CAD/CAE:

```text
solver ran != design is valid
mesh exists != mesh is acceptable
CAD artifact exists != geometry is valid
visualization exists != engineering validation passed
evidence exists != claim passed
```

Evidence supports review. It is not automatically a claim.

---

## 3. Core Product Layers

### 3.1 `.aieng`: Engineering Context Layer

`.aieng` is the semantic and evidence package layer.

It should contain or reference:

- resources and artifacts
- parameters
- constraints
- feature or resource mappings
- reference mappings
- evidence records
- provenance records
- tool traces
- missingness
- unsupported states
- `needs_review` states
- claim map

`.aieng` should remain CAD/CAE-tool agnostic.

It should not become FreeCAD-specific.

### 3.2 MCP Adapters: Controlled Execution Layer

MCP adapters connect agents to specific engineering tools.

Examples:

- FreeCAD adapter
- mesh adapter
- solver adapter
- post-processing adapter
- visualization adapter

Adapters may:

- inspect CAD/CAE files
- apply bounded parameter edits
- export artifacts
- generate mesh evidence
- run solvers when explicitly requested
- extract deterministic metrics
- write evidence and trace records

Adapters must not silently turn execution into engineering truth.

### 3.3 Agent Product Layer

The user-facing layer can include:

- CAD Copilot
- CAE Copilot
- simulation assistant
- design optimization assistant
- natural-language modeling assistant
- engineering review assistant

These products use `.aieng` and MCP adapters as the safe technical foundation.

---

## 4. Main Workflows

## 4.1 `.aieng`-First Workflow

This is the preferred workflow for auditable engineering edits.

```text
user intent
    ↓
agent creates structured patch proposal
    ↓
.aieng constraints and references are checked
    ↓
MCP adapter performs bounded operation
    ↓
CAD/CAE artifacts are generated
    ↓
evidence and trace are written
    ↓
affected references are marked needs_review
    ↓
claim_map remains unchanged unless explicitly updated
```

Example patch proposal:

```json
{
  "operation": "modify_parameter",
  "target": "feat_base_plate_001",
  "parameter": "thickness",
  "from": 4.0,
  "to": 5.0,
  "unit": "mm",
  "reason": "increase stiffness near mounting load path"
}
```

This workflow is best for:

- parameter edits
- guarded CAD updates
- traceable evidence generation
- reviewable engineering changes
- future multi-tool support

---

## 4.2 CAD/CAE-First Ingestion Workflow

This workflow starts from existing CAD/CAE files.

```text
existing CAD/CAE artifacts
    ↓
adapter inspection
    ↓
parameter/resource extraction
    ↓
feature and reference mapping
    ↓
missingness and unsupported information recorded
    ↓
.aieng package created or updated
```

This is useful for legacy files or projects that do not already have `.aieng` context.

However, extracted information may be incomplete or inferred.

The package should clearly mark:

- inferred information
- uncertain mappings
- unsupported features
- missing design intent
- items needing review

---

## 4.3 Hybrid Agent Loop

The long-term workflow combines both directions.

```text
.aieng describes current engineering context
    ↓
agent proposes a bounded patch
    ↓
MCP adapter executes the patch
    ↓
adapter inspects the result
    ↓
.aieng records evidence, trace, and missingness
    ↓
debug pipeline checks the modified artifact
    ↓
agent summarizes impact
    ↓
human or explicit review process decides next step
```

This is the foundation for a reliable CAD/CAE Copilot.

---

## 5. CAD Copilot Direction

A CAD Copilot should help users understand and modify CAD models without requiring them to be CAD experts.

Possible capabilities:

- read CAD project context
- explain model structure
- list editable parameters
- identify protected features
- explain constraints
- propose bounded edits
- apply approved parameter changes
- export modified CAD artifacts
- compare old and new values
- record evidence and trace
- mark affected references as `needs_review`

Example user request:

```text
Make the bracket slightly thicker around the mounting area.
```

Good agent behavior:

```text
This request is not yet a bounded CAD edit.

Possible controlled edits:
1. increase base plate thickness from 4 mm to 5 mm
2. increase mounting hole fillet radius from 2 mm to 3 mm
3. add a rib with specified dimensions

No CAD change has been made yet.
```

The agent should not perform ambiguous CAD mutation without clarification.

---

## 6. CAE Copilot Direction

A CAE Copilot should help users prepare, run, and interpret simulations.

Possible capabilities:

- check whether materials are defined
- check boundary conditions
- check loads
- generate mesh evidence
- export solver decks
- run solvers when explicitly requested
- extract deterministic result metrics
- generate post-processing artifacts
- identify high-stress or high-displacement regions
- compare before/after evidence

However:

```text
solver success does not mean design validity
result metric does not mean requirement satisfaction
visualization does not mean engineering validation
```

CAE outputs should be recorded as evidence for review, not as automatic claims.

---

## 7. Design Suggestion and Optimization Direction

A future design assistant may suggest where to add material, remove material, increase thickness, add ribs, or change fillets.

A safe optimization loop should look like this:

```text
read CAD/CAE context
    ↓
read simulation evidence
    ↓
identify candidate weak or overbuilt regions
    ↓
propose bounded design edits
    ↓
user approves one edit
    ↓
adapter applies edit
    ↓
debug pipeline checks result
    ↓
optional CAE rerun if explicitly requested
    ↓
compare before/after evidence
    ↓
review before any claim update
```

Examples of bounded suggestions:

- increase thickness from 4 mm to 5 mm
- add rib with explicit dimensions
- increase fillet radius from 2 mm to 3 mm
- reduce thickness in a low-stress region within stated constraints

The assistant may suggest options, but it should not automatically optimize and validate the design end-to-end.

---

## 8. Natural-Language Modeling Direction

Natural-language modeling is a long-term goal.

The safer workflow is:

```text
natural language request
    ↓
structured design intent
    ↓
feature plan
    ↓
patch proposal
    ↓
user confirmation
    ↓
controlled CAD adapter execution
    ↓
debug and review
```

Example:

```text
I need a simple mounting bracket with two holes and a stiffening rib.
```

The agent should translate this into a structured proposal:

- base plate dimensions
- hole count and diameter
- hole spacing
- rib dimensions
- material assumptions
- missing information
- unsupported details
- required confirmations

Then the user or reviewer can approve bounded generation.

Natural language should not directly become arbitrary CAD mutation.

---

## 9. Engineering Debug Pipeline

After CAD/CAE changes, the system needs a debug and review process.

This is similar to CI for software, but stricter because engineering evidence is not automatically truth.

### Level 0: Execution Debug

Checks whether the tool ran.

- command executed
- exit code
- stdout/stderr summary
- script hash
- output artifact exists
- trace written
- `claims_advanced: false`

### Level 1: CAD Regeneration Debug

Checks whether the CAD operation completed.

- document opened
- parameter changed
- old/new values captured
- recompute succeeded
- output FCStd saved
- source file not modified in place

### Level 2: Geometry Sanity Debug

Checks whether the geometry is obviously broken.

- shape exists
- volume is positive
- bounding box is reasonable
- expected objects still exist
- invalid topology is reported
- mass or volume delta is within expected range

### Level 3: Reference and Intent Debug

Checks semantic consistency.

- feature graph still maps to CAD objects
- affected references marked `needs_review`
- protected features unchanged
- missing mappings reported
- unsupported mappings reported

### Level 4: Mesh / CAE Readiness Debug

Checks whether simulation setup can proceed.

- mesh generated
- mesh quality metrics available
- boundary condition regions identifiable
- materials present
- loads present
- solver deck exportable

### Level 5: Solver / Result Debug

Runs only when explicitly requested.

- solver ran
- convergence status recorded
- warnings/errors recorded
- result files produced
- metrics extracted

### Level 6: Claim Review

Claim updates require explicit evidence-backed review.

Required inputs should include:

- claim id
- evidence id
- acceptance criteria
- comparison result
- rationale
- missing/unsupported/uncertain information

Only this level may update `results/claim_map.json`.

---

## 10. Agent Runtime Confirmation Policy

The agent should not ask for confirmation before every internal step.

Instead, use boundary-based confirmation.

### No step-by-step confirmation needed for:

- read-only inspection
- loading `.aieng` context
- reading parameters and constraints
- checking references
- checking missingness
- summarizing available capabilities

### Explicit bounded request is required for:

- CAD mutation
- artifact export
- evidence writeback
- reference `needs_review` updates
- solver execution
- claim update

### Clarification is required for:

- ambiguous design goals
- missing constraints
- unsupported operations
- protected feature changes
- uncertain mappings
- requests such as “make it stronger” or “make it lighter”

### Always explicit:

- CAE execution
- solver run
- claim update
- changes to `results/claim_map.json`

Principle:

```text
ordinary internal checks can be automatic;
crossing engineering-risk boundaries requires explicit approval.
```

---

## 11. Multi-CAD/CAE Adapter Strategy

FreeCAD is the first adapter, not the semantic model.

`.aieng` should support future adapters for tools such as:

- FreeCAD
- OpenCascade-based tools
- Gmsh
- CalculiX
- Code_Aster
- Abaqus
- Ansys
- OpenFOAM
- Blender as visualization or mesh adapter
- other CAD/CAE systems

FreeCAD-specific details should remain adapter-local.

Examples:

- `FREECAD_HOME`
- FCStd handling
- FreeCAD executable detection
- FreeCAD object names
- FreeCAD Python snippets
- FreeCAD adapter execution behavior

Generic `.aieng` concepts should remain tool-agnostic:

- resource
- artifact
- parameter
- constraint
- operation
- tool
- adapter
- evidence
- provenance
- reference
- claim
- missingness
- unsupported state
- `needs_review`

Adapter-specific metadata may appear in evidence or provenance, but it must not become required for interpreting `.aieng`.

---

## 12. Product Roadmap

### Phase 1: Engineering Repository Layer

Build `.aieng` as an agent-readable semantic/evidence package.

Status: in progress.

### Phase 2: Controlled CAD Adapter

Support guarded CAD inspection, parameter edits, artifact export, evidence, trace, and `needs_review`.

Status: current MVP.

### Phase 3: CAD Debug Pipeline

Add checks for recompute, shape validity, geometry sanity, reference integrity, and artifact diffs.

Status: next major direction.

### Phase 4: CAE Adapter and Simulation Pipeline

Support mesh generation, solver deck export, solver execution, result extraction, and simulation evidence.

Status: future.

### Phase 5: Design Suggestion Assistant

Use CAD/CAE evidence to suggest bounded design improvements such as thickening, light-weighting, rib additions, or fillet changes.

Status: future.

### Phase 6: Natural-Language Modeling Assistant

Convert user intent into structured design specs, feature plans, and patch proposals.

Status: future.

### Phase 7: Multi-Tool Engineering Workspace

Support multiple CAD/CAE adapters while keeping `.aieng` as the shared semantic/evidence layer.

Status: future.

---

## 13. Non-Negotiable Boundaries

- `.aieng` must remain CAD/CAE-tool agnostic.
- FreeCAD is one adapter backend, not the semantic model.
- Evidence is not a claim.
- Artifacts are not claims.
- Solver output is not engineering validation.
- Visual output is not engineering validation.
- Claim updates require explicit evidence-backed operations.
- Execution tools must default to `"claims_advanced": false`.
- Missing, unsupported, uncertain, and `needs_review` states must be explicit.
- CAD and CAE workflows must remain independently usable.
- Automatic CAD-to-CAE-to-claim workflows are not supported.

---

## 14. aieng-cad-copilot Skill Direction

This section describes a future **Agent Product Layer** Skill that guides agent behavior when working with CAD/CAE projects. It sits above both `.aieng` and `aieng_freecad_mcp` (or any future adapter). It is a documented product direction only — no implementation or packaging yet.

> Public-facing positioning of `.aieng` and product demonstration guidance lives in [`../../aieng/docs/public-positioning.md`](../../aieng/docs/public-positioning.md). The Skill direction here is independent of maintaining a separate gallery repository.

### 14.1 Purpose

The Skill helps agents work with CAD/CAE projects using `.aieng` packages and MCP adapters. It turns vague user requests into structured engineering intent, proposes bounded changes, and ensures execution stays within guard boundaries.

The Skill is **not** an execution engine. It does not contain arbitrary CAD code, arbitrary Python, or shell execution paths. All geometry mutation, meshing, solving, and artifact export still happen through MCP adapters.

### 14.2 What the Skill Should Help Agents Do

- Understand user engineering intent from natural language
- Load and inspect `.aieng` context (manifest, feature graph, constraints, evidence, trace, claim map)
- Identify editable parameters, protected features, constraints, references, evidence, missingness, and unsupported states
- Convert vague requests (for example, "make it stronger") into structured design intent with explicit options
- Propose bounded patch proposals that reference feature IDs and declare expected effects
- Call MCP adapters for controlled execution
- Inspect output artifacts and verify evidence and trace were recorded
- Mark or check `needs_review` on affected references after geometry changes
- Keep `claims_advanced: false` in all execution paths
- Avoid automatic claim updates — only explicit evidence-backed claim updates are allowed

### 14.3 Core Workflows

**.aieng-first workflow:**

```text
user intent
    ↓
agent loads .aieng context
    ↓
structured patch proposal
    ↓
guard checks against feature graph and constraints
    ↓
MCP adapter performs bounded operation
    ↓
evidence and trace written to .aieng
    ↓
affected references marked needs_review
    ↓
claim_map unchanged unless explicit review
```

**CAD/CAE-first ingestion workflow:**

```text
existing CAD/CAE files
    ↓
adapter inspection and conversion
    ↓
inferred .aieng context created
    ↓
missingness, unsupported, and needs_review recorded explicitly
    ↓
agent works from the structured package
```

**Hybrid loop:**

```text
.aieng describes current engineering context
    ↓
agent proposes bounded patch
    ↓
MCP adapter executes
    ↓
adapter inspects result
    ↓
.aieng records evidence, trace, and missingness
    ↓
debug pipeline checks modified artifact
    ↓
agent summarizes impact
    ↓
human or explicit review decides next step
```

### 14.4 Demo / Benchmark Value

A future benchmark could compare three conditions:

1. **Raw CAD only** — agent works directly with STEP/FCStd files
2. **CAD + .aieng** — agent works with a structured `.aieng` package
3. **CAD + .aieng + Skill** — agent uses the Skill to guide inspection, proposal, and execution

Evaluation criteria:

- Identifies correct editable parameters from the feature graph
- Avoids protected features and respects constraints
- Executes bounded edits through MCP adapters, not arbitrary mutation
- Records evidence and trace after execution
- Marks affected references as `needs_review`
- Never advances claims automatically
- Explains impact clearly with old/new values and expected validation steps

### 14.5 Non-Goals

The Skill must not:

- perform arbitrary CAD mutation directly
- execute arbitrary Python or shell commands
- automatically chain CAD → CAE → claim update
- automatically run solvers or treat solver output as validation
- automatically update claim status without explicit evidence-backed review
- introduce FreeCAD-specific fields into `.aieng` schemas
- replace engineering review or human judgment

### 14.6 Future Repo / Package Location

The Skill may eventually live in a separate repository or packaged Skill directory, for example:

```text
aieng-cad-copilot/
├── skill.md or SKILL.md
├── prompts/
├── planners/
└── validators/
```

For now this is only a documented product direction. No Skill package, source code, or tests are created yet.

---

## 15. Summary

The long-term goal is to make CAD/CAE engineering projects more like well-structured software repositories for agents:

```text
inspectable
actionable
debuggable
reviewable
auditable
```

Agents should be able to read engineering context, propose bounded changes, execute controlled operations through adapters, run debug and evidence pipelines, and support review.

They should not silently convert execution into engineering truth.

The central product idea is:

```text
agent-readable engineering context
+ controlled CAD/CAE execution
+ evidence and trace
+ debug pipeline
+ explicit review
= safer agent-assisted engineering
```
