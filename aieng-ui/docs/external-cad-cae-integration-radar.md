# External CAD/CAE Integration Radar + Adapter Contract

Status: **v0.13 planning artifact**  
Last checked: **2026-05-19**

AIENG should integrate with CAD/CAE tools rather than reimplement them. AIENG's
job is the safety/evidence layer: `.aieng` package semantics, approval gates,
stale evidence propagation, audit logs, claim boundaries, loop reports, decision
comparison/export, project health, and readiness guidance.

External CAD/CAE projects are treated as **untrusted execution backends** behind
AIENG's adapter contract. They may produce evidence, but they may not certify a
design or advance engineering claims.

## Integration radar

| Project | URL | Category | License | Activity / maturity | Core capability | Dependencies | Headless | Windows | Linux | CI testability | Risk | AIENG fit | Action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| existing `aieng_freecad_mcp` | sibling repo | CAD/FreeCAD/MCP | MIT | AIENG-owned, safety-aligned; current head at `2064906` during review | controlled FreeCAD inspection/edit/mesh/solver bridge, `.aieng` evidence writeback | FreeCAD, optional mesher/CalculiX | intended headless path; CI dry-run stubs exist | likely, via FreeCADCmd | likely | good dry-run coverage; real FreeCAD tests environment-dependent | medium external-tool risk, low product-fit risk | best first wrapper target | `integrate_now` |
| `tessalabs-space/freecad-mcp` | https://github.com/tessalabs-space/freecad-mcp | CAD/FreeCAD/MCP | MIT stated in README; GitHub API `NOASSERTION` | very new/small; 2 stars, 7 commits; pushed 2026-04-17 | broad typed engineering surface: parametric CAD, drawing, mass, sweeps, materials, BC tags, meshing, solver handoff | FreeCAD addon + FastMCP + optional Gmsh/solvers/renderers | README claims optional headless mode | yes path docs | yes path docs | smoke tests reportedly avoid FreeCAD | high breadth/immaturity risk | useful source of tool taxonomy and adapter ideas | `borrow_ideas` / `watch` |
| `bonninr/freecad_mcp` | https://github.com/bonninr/freecad_mcp | CAD/FreeCAD/MCP | MIT | 183 stars, 16 commits; pushed 2025-03-20 | simple FreeCAD MCP workbench / socket bridge for document interaction | FreeCAD module install; Python bridge | unclear; appears GUI/workbench oriented | yes install docs | yes install docs | uncertain | broad agent control surface; safety gates absent | useful minimal MCP bridge reference, not direct runtime | `borrow_ideas` |
| `neka-nat/freecad-mcp` | https://github.com/neka-nat/freecad-mcp | CAD/FreeCAD/MCP | MIT | active/popular; 966 stars, pushed 2026-05-13 | FreeCAD MCP server; influential addon/RPC pattern | FreeCAD addon + MCP server | not clearly documented in reviewed README | likely | likely | likely for server pieces | external state mutation via direct CAD control | good architectural reference | `watch` / `borrow_ideas` |
| `spkane/freecad-addon-robust-mcp-server` | https://github.com/spkane/freecad-addon-robust-mcp-server | CAD/FreeCAD/MCP | MIT | active; 87 stars, pushed 2026-05-11 | 150+ tools, XML-RPC/JSON-RPC/embedded modes, GUI + headless support, macros | FreeCAD, MCP bridge; optional Docker | yes, README claims headless modeling | likely | likely | better than GUI-only if Docker/headless is usable | large tool surface; macro execution is high risk | good adapter-contract reference, especially connection modes | `prototype` after AIENG wrapper |
| existing AIENG Gmsh/CalculiX runtime | `aieng-ui/backend/app/app_factory.py`, `aieng_bridge.py`, `copilot_loop.py` | structural CAE | project internal | already tested in backend; missing dependencies reported honestly | preflight, mesh generation bridge, solver run, FRD extraction, computed metrics, summaries | FreeCAD/Gmsh/CalculiX optional | yes for preflight; execution depends on binaries | partial | partial | good mocked/preflight tests; real solver tests environment-dependent | solver execution requires strict approval | best current structural path | `integrate_now` hardening |
| `calculix/pygccx` | https://github.com/calculix/pygccx | structural CAE / Gmsh / CalculiX | GPL-3.0 | 41 stars, 203 commits; pushed 2025-02-18 | Gmsh geometry/mesh, CCX input writing, direct solve, FRD/DAT postprocess, invariant stresses | Python 3.10+, Gmsh API, CCX, CGX | likely headless for model build/solve; CGX viewing not needed | possible but dependency-heavy | likely | feasible for deterministic small examples if deps installed | GPL compatibility and external binary complexity | strong technical fit for bracket/cantilever prototype; avoid vendoring | `prototype` |
| `spacether/pycalculix` | https://github.com/spacether/pycalculix | structural CAE / CalculiX | Apache-2.0 | mature but README says no longer actively maintained; latest release 2019 | 2D/axisymmetric FEA automation, trade studies; meshing via CalculiX/Gmsh | Python, NumPy, Matplotlib, CGX/Gmsh/CCX | background solve/mesh; not GUI CAD | yes install docs | yes/mac docs | moderate but old | maintenance risk | useful examples; less aligned with 3D CAD evidence layer | `watch` / `borrow_ideas` |
| `csml-rpi/Foam-Agent` | https://github.com/csml-rpi/Foam-Agent | CFD / OpenFOAM agent | MIT | active; 232 stars, pushed 2026-05-05; workshop project | end-to-end OpenFOAM pipeline: planning, meshing, case setup, execution, error correction, visualization; MCP/skill | OpenFOAM Foundation v10, Python, LangGraph/RAG, optional HPC/PyVista/ParaView | yes in Linux/Docker style workflows | likely via WSL/Docker only | yes | possible with Docker, heavy | high: CFD setup is case-specific and expensive | learn workflow decomposition; defer adapter | `defer` / `borrow_ideas` |
| `woog97/cfd-agent` | https://github.com/woog97/cfd-agent | CFD / OpenFOAM / ChatCFD-style | no asserted license in GitHub API | small; 12 stars; pushed 2025-12-31 | LLM-driven OpenFOAM simulation from uploaded case docs/mesh; Streamlit interface | OpenFOAM 2406, API keys, RAG/model deps | Linux-style OpenFOAM install | WSL likely | yes | low without API keys/OpenFOAM | license/API/dependency risk | observe only | `defer` |
| `010zx00x1/Awesome-Physical-Engineering-AI` | https://github.com/010zx00x1/Awesome-Physical-Engineering-AI | project index | no license | small but current; pushed 2026-05-12 | curated list of CAD/simulation/manufacturing AI tools and engineering agents | none | n/a | n/a | n/a | n/a | index quality varies | useful scouting list, not an adapter | `watch` |

## Candidate notes

### FreeCAD / MCP

**Best near-term path:** wrap AIENG's existing `aieng_freecad_mcp` first. It is
already aligned with `.aieng` evidence semantics, dry-run acceptance testing,
and claim discipline. External FreeCAD MCP projects are valuable references for
connection modes, typed tool surfaces, and headless patterns, but their raw tool
surfaces generally allow broad CAD mutation and macro execution. AIENG should
not expose those directly.

What to reuse:

- FreeCAD RPC/MCP connection patterns.
- Feature/property inspection approaches.
- Export patterns for STEP/STL/FCStd.
- Headless FreeCAD process management ideas.
- Material/BC tagging taxonomy where it maps to `.aieng` evidence.

What not to reuse directly:

- Open-ended macro execution without approval.
- Text-to-CAD generation as a product surface.
- One-prompt end-to-end CAD/mesh/solver flows without intermediate review.
- Any tool output that claims safety or design acceptance.

### Structural CAE / Gmsh / CalculiX

AIENG already has the right semantic pieces: preflight, solver-run gate,
FRD extraction, computed metrics import, result summaries, and stale evidence
handling. The gap is a deterministic, well-bounded structural fixture path that
can run when dependencies exist and skip honestly when they do not.

`pygccx` is the most interesting prototype candidate because it can build/mesh
with Gmsh, write CCX input, solve, and postprocess FRD/DAT. Its GPL-3.0 license
means AIENG should avoid vendoring or tight code copying unless the license
choice is explicit. A subprocess/optional dependency adapter is safer.

`pycalculix` is easier license-wise (Apache-2.0) but no longer actively
maintained and is more useful as a source of simple FEA examples than as a core
runtime dependency.

### CFD / OpenFOAM

OpenFOAM should be deferred. Foam-Agent and ChatCFD-style projects show useful
workflow patterns: planner -> input writer -> runner -> reviewer/fixer ->
visualization. However, CFD setup is highly case-specific, dependency-heavy,
often Linux/Docker/HPC oriented, and much harder to validate safely than a
small structural bracket/cantilever demo.

Safe CFD integration later would require:

- explicit case templates and geometry/mesh contracts;
- Docker/WSL/Linux dependency preflight;
- bounded execution budgets;
- residual/convergence evidence schema;
- field/mesh/result artifact manifests;
- strong claim-boundary language around convergence and validation.

## Recommended pilots

### Pilot A — FreeCAD feature inspection + parameter-edit adapter wrapper

Goal: wrap existing `aieng_freecad_mcp` and selected lessons from FreeCAD MCP
projects behind AIENG's adapter contract.

Scope:

- inspect FCStd/STEP-derived feature/property metadata;
- expose editable parameter handles only when `.aieng` marks them executable;
- apply one bounded parameter edit only through approval;
- write changed CAD artifacts back into `.aieng`;
- mark mesh, solver input, solver results, computed metrics, summaries, reports,
  and target comparisons stale.

Why first:

- highest product fit;
- reinforces Copilot loop workflow;
- uses existing AIENG-owned code and tests;
- makes CAD changes reviewable rather than autonomous.

### Pilot B — CalculiX structural rerun fixture

Goal: deterministic bracket/cantilever structural loop using existing AIENG
preflight/run/extract/metrics semantics, optionally prototyping `pygccx` as an
external backend.

Scope:

- fixed small fixture with known inputs;
- generate or reuse mesh/input deck;
- run CCX only when available and approved;
- parse `.frd` / `.dat`;
- write `results/computed_metrics.json`;
- refresh summaries and map design targets;
- skip honestly when CCX/Gmsh/FreeCAD is unavailable.

Why second:

- proves the evidence loop after CAD edits;
- keeps the demo structural and deterministic;
- avoids broad solver-platform expansion.

## Adapter contract

The following contract is implemented as non-executing Pydantic models in
`backend/app/external_adapters.py` and should be mirrored in any future frontend
types if exposed to users.

### 1. Capability manifest

```ts
type ExternalToolCapability = {
  id: string;
  label: string;
  category: "cad" | "mesh" | "solver" | "postprocess" | "report";
  mutates_package: boolean;
  mutates_external_model: boolean;
  runs_external_process: boolean;
  expensive: boolean;
  requires_approval: boolean;
  input_artifacts: string[];
  output_artifacts: string[];
  stale_artifacts_on_success: string[];
  claim_advancement: "none";
};
```

Rules:

- CAD mutation requires approval.
- Mesh generation requires approval if it runs external tools, is expensive, or
  overwrites artifacts.
- Solver execution always requires approval.
- Postprocess import may be an explicit user action but must not advance claims.
- `claim_advancement` must always be `"none"`.
- CAD mutation must declare stale artifacts.

### 2. Preflight

```ts
type AdapterPreflightResult = {
  ok: boolean;
  status: "ready" | "partial" | "not_ready" | "unavailable";
  missing_dependencies: string[];
  warnings: string[];
  errors: string[];
  estimated_outputs: string[];
  requires_approval: boolean;
};
```

Rules:

- Every external adapter must expose preflight before execution.
- Unavailable dependencies must be reported honestly.
- `status="unavailable"` must name missing dependencies.
- Preflight must not mutate packages, run solvers, or change external models.

### 3. Execution result

```ts
type AdapterExecutionResult = {
  ok: boolean;
  status: "completed" | "skipped" | "partial" | "error";
  changed_artifacts: string[];
  stale_artifacts: string[];
  warnings: string[];
  errors: string[];
  evidence_written: string[];
  claim_advancement: "none";
};
```

Rules:

- `error` status must include errors.
- `ok=true` cannot use `error` status.
- Output artifacts may become evidence but not certification.
- No execution result may imply claim acceptance.

### 4. Evidence writeback rules

- Every adapter output must write artifact/evidence metadata into `.aieng`.
- Adapter results may become evidence.
- Adapter results may not certify a design.
- No adapter may write or advance `ai/claim_map.json` automatically.
- Reports must preserve claim-boundary language.

### 5. Approval rules

Examples:

- CAD parameter edit: approval required.
- FreeCAD macro execution: approval required; avoid unless explicitly scoped.
- Mesh generation: approval required if external, expensive, or overwriting.
- Solver run: approval required.
- Postprocess import: explicit user action required; no claim advancement.

### 6. Stale propagation rules

Adapter manifests must declare stale artifacts on successful mutation.

Examples:

- CAD edit stales mesh, solver inputs, solver results, computed metrics, field
  summaries, CAE summaries, reports, and target comparisons.
- Mesh regeneration stales solver input/results/metrics/summary if overwritten.
- Solver rerun stales old result summary/metrics if overwritten.
- Metrics import stales target comparison summaries if those summaries exist.

## Safety boundaries

- AIENG remains the safety/evidence layer.
- External adapters are untrusted execution backends.
- No adapter may advance engineering claims.
- No hidden CAD mutation.
- No hidden solver run.
- All mutating or expensive operations require approval.
- Unavailable tools must be reported as unavailable, not faked.
- Generated/imported metrics are evidence, not certification.
- Human engineering review remains required.

## Roadmap

1. **Pilot A:** FreeCAD adapter wrapper for feature inspection and bounded
   parameter edit through `aieng_freecad_mcp`.
2. **Pilot B:** CalculiX structural rerun fixture using existing preflight,
   run, FRD extraction, computed metrics, and target mapping.
3. **Later:** OpenFOAM / CFD adapter after structural evidence workflow is
   stable and a CFD-specific evidence schema exists.

## Non-goals

- No new CAD system integration in v0.13.
- No OpenFOAM execution in v0.13.
- No SolidWorks/Onshape/Abaqus/Ansys adapters.
- No text-to-CAD product surface.
- No autonomous optimization loop.
- No geometry or mesh visual diff.
- No one-click auto-fix.
- No certification or claim advancement.

## Sources checked

- https://github.com/tessalabs-space/freecad-mcp
- https://github.com/bonninr/freecad_mcp
- https://github.com/neka-nat/freecad-mcp
- https://github.com/spkane/freecad-addon-robust-mcp-server
- https://github.com/calculix/pygccx
- https://github.com/spacether/pycalculix
- https://github.com/csml-rpi/Foam-Agent
- https://github.com/woog97/cfd-agent
- https://github.com/010zx00x1/Awesome-Physical-Engineering-AI
- local `aieng-ui`, `aieng`, and `aieng_freecad_mcp` repositories

## Pilot A: FreeCAD adapter capability manifest and preflight (v0.14)

The first piece of Pilot A is in place. It is **read-only**: it declares
what the FreeCAD adapter would do under AIENG's safety contract, and it
answers one question — *is the FreeCAD adapter usable in this
environment?* It does not run FreeCAD, does not mutate any package, and
does not import `freecad_mcp` at module-load time.

### What is implemented

- `backend/app/freecad_adapter.py` — static capability manifest plus a
  read-only preflight that checks the file system without invoking
  FreeCAD.
- `GET /api/adapters/freecad/preflight` — environment-level endpoint
  that returns capabilities, preflight result, environment snapshot
  (checked paths, headless-supported hint, CI flag), an explicit safety
  note, and a claim-boundary statement.
- Tests: `backend/tests/test_freecad_adapter.py` — 18 cases covering
  manifest contract, preflight states, claim-boundary presence,
  non-mutation guarantees, and HTTP route behavior. Tests never run
  FreeCAD.

### Capabilities declared

| Capability | Mutates package | Requires approval | Stale on success |
|---|---|---|---|
| `freecad.inspect_document` | no | no | — |
| `freecad.inspect_features` | no | no | — |
| `freecad.inspect_parameters` | no | no | — |
| `freecad.export_step` | yes (writes `cad/exports/model.step`) | **yes** | the exported STEP file |
| `freecad.edit_parameter` | yes | **yes** | `mesh/*`, `simulation/runs/*`, `results/*.json`, `reports/copilot_loop/*` |

`claim_advancement` is locked to `none` for every capability — the
v0.13 model rejects anything else.

### Preflight states

- `ready` — every check passed; `missing_dependencies == []`. The
  endpoint reports `ok: true`.
- `partial` — some FreeCAD infrastructure is present (e.g.
  `aieng_freecad_mcp/src` checkout) but at least one dependency is
  missing. The endpoint reports `ok: false` plus an explicit list of
  what is missing.
- `unavailable` — every check failed. The model enforces a non-empty
  `missing_dependencies` list, so the response is always self-explaining.

### What approval gives you

CAD-mutating capabilities (`freecad.export_step`,
`freecad.edit_parameter`) have `requires_approval: true` baked into
their manifest. When the runtime wires them in (a separate, future
task), the existing approval gate already used for `cad.edit_parameter`
will apply unchanged. Stale-artifact propagation is also declared
statically so the runtime can mark downstream evidence as stale
without depending on the adapter to remember.

### What is NOT implemented yet

- No FreeCAD execution surface — the adapter does not run FreeCAD,
  edit parameters, export STEP, or import the `freecad_mcp` Python
  package.
- No new runtime tool. Existing `cad.edit_parameter` is unchanged.
- No solver / mesh execution scope.
- No frontend surface in v0.14. The endpoint is reachable; UI
  consumption is deferred.

### Honest unavailable behavior

If `aieng_freecad_mcp` is not checked out, or FreeCADCmd is not on the
host, the endpoint returns 200 with a structured response: the missing
dependency labels are stable identifiers
(`freecad_mcp_root`, `freecad_mcp_root/src`,
`freecad_mcp.freecad_mcp`, `freecad_mcp.aieng_bridge`, `FreeCADCmd`)
that the UI can render directly. Missing FreeCAD never produces a 500.

### Pilot A next step (out of scope here)

The next safe slice is wrapping `freecad.inspect_features` as a
runtime tool that re-uses the existing `aieng_freecad_mcp` bridge,
gated by the preflight from this task. CAD mutation through this
adapter is explicitly out of scope until that read-only inspection
tool is itself proven, demonstrated, and accepted.

## Pilot A next slice: read-only feature inspection (v0.15)

The runtime/contract wiring for the read-only inspection slice now
exists. The CAD-mutation boundary remains intact.

### What is now supported

- A new runtime tool **`freecad.inspect_features`** that:
  - is registered in the runtime tool registry (`runtime.py` aliases
    cover "inspect features", "feature inspection", "提取特征");
  - calls the v0.14 preflight first;
  - delegates to a feature-inspection bridge seam in
    `freecad_adapter._default_freecad_inspect_bridge`;
  - writes two evidence artifacts into the project's `.aieng` package
    when a project_id is provided:
    - `simulation/cae_imports/parsed_features.json`
    - `graph/feature_graph.json`
  - returns a structured response (`status`, `preflight_status`,
    `evidence_written`, `feature_count`, `editable_parameter_count`,
    `claim_advancement: "none"`, `safety_note`, `claim_boundary`).
- A REST surface for the same operation:
  **`POST /api/projects/{project_id}/freecad/inspect-features`** —
  body fields `source_path` and `write_evidence` are optional.
- Both evidence artifacts carry provenance metadata:
  `{"source": "freecad.inspect_features", "generated_at": "...",
  "claim_advancement": "none"}`.
- Project Health Check now recognises this evidence:
  - `cad_context` becomes `passed` when either artifact is present;
  - `editable_parameters` becomes `passed` when the graph carries
    parameter names (the feature graph emits a flat
    `editable_parameters: [...]` list per feature for compatibility
    with the v0.9 health check);
  - the v0.9 health-action that targets `editable_parameters`
    disappears once the evidence exists.

### What is NOT supported

- **No real FreeCAD execution.** The default bridge intentionally
  raises a clear `RuntimeError`; the runtime tool converts that into
  an honest `status: skipped` with `reason: "bridge_unavailable"`.
  Tests inject a mock bridge to exercise the writeback path
  deterministically; a production bridge that wraps a real
  `aieng_freecad_mcp` reader is a future task.
- **No CAD edit.** The capability id `freecad.edit_parameter` from
  v0.14 still requires approval and is **not** wired to a runtime
  tool by this task.
- **No solver / mesh / postprocessing execution** is added.
- **No arbitrary FreeCAD command surface** is exposed.
- **No claim advancement.** Every code path locks
  `claim_advancement = "none"` and the response carries an explicit
  claim-boundary statement.

### Preflight gating

Before the bridge is called the runtime tool invokes
`preflight_freecad_adapter(settings)`:

| Preflight status | Tool outcome | Side effects |
|---|---|---|
| `unavailable` | `status: skipped`, `reason: freecad_adapter_unavailable`, missing-dep list surfaced | none — no bridge call, no evidence write |
| `partial` / `ready` | bridge is called; on success → `completed` and evidence is written | one atomic `.aieng` rewrite per evidence artifact (canonicalised manifest), CAD source members byte-identical |

If the bridge raises `FileNotFoundError`, `RuntimeError`, or any other
exception, the tool returns `error` / `skipped` honestly — never a 500
and never a faked success.

### Honest unavailable behaviour

The default bridge raises the v0.15 "no implementation wired" message;
this is converted to `status: skipped` so the runtime surface stays
demonstrable without FreeCAD installed. The preflight from v0.14
governs whether the bridge is even attempted, and missing FreeCAD /
missing `aieng_freecad_mcp` continues to surface stable missing-dep
labels (`freecad_mcp_root`, `freecad_mcp_root/src`,
`freecad_mcp.aieng_bridge`, `FreeCADCmd`).

### How this prepares for future approval-gated parameter edit

Wrapping `freecad.edit_parameter` as a real runtime tool is the next
safe slice after a production read-only bridge lands. The pieces it
will reuse are now in place:

- the **preflight gate** for environment readiness;
- the **bridge seam** convention (`_default_freecad_inspect_bridge`
  has a sibling shape for mutation);
- the **evidence/stale-artifact** declarations in the v0.14
  capability manifest;
- the **approval gate** that's already present in the closed-loop
  Copilot stepper for `cad.edit_parameter`;
- the **Project Health Check** signal so the workbench can report
  CAD readiness honestly.

When that mutation tool lands, it will plug into the existing
approval-gated `cad.edit_parameter` runtime path, declare
`freecad.edit_parameter` as the underlying capability, and rely on
the stale-artifact propagation already wired into the loop stepper.

## Pilot A v0.16 — real read-only bridge wiring

v0.15 wired the contract end-to-end with a default seam that always
raised `RuntimeError`. v0.16 replaces that seam with a small **discovery
layer** that tries known read-only candidate functions from
`aieng_freecad_mcp`. The bridge remains entirely optional.

### How discovery works

`_default_freecad_inspect_bridge(settings, source_path)` now:

1. Prepends `settings.freecad_mcp_root/src` to `sys.path` (idempotent
   — only if the directory exists; never removes anything from
   `sys.path`).
2. Iterates the `_FREECAD_BRIDGE_CANDIDATES` list of
   `(module, attr, signature_kind)` triples:
   - `freecad_mcp.aieng_bridge.inspect_features` — `path_only`
   - `freecad_mcp.aieng_bridge.read_features` — `path_only`
   - `freecad_mcp.feature_inspector.run_feature_inspection` —
     `path_and_cmd` (mirrors the existing geometry-inspector wrapper)
3. The first candidate whose module imports and whose attribute is a
   callable wins. The function is invoked with the registered
   signature shape; on success the result is forwarded to the
   normaliser unchanged (a bare list of features is tolerated and
   wrapped before normalisation).
4. When **no** candidate is importable, the layer raises
   `ModuleNotFoundError`, which `inspect_features` converts to
   `status: "skipped", reason: "bridge_unavailable"` with a clear
   warning. Missing FreeCAD never produces a 500.

### What the response carries

On success the response and the evidence-document provenance both
include the discovered provider label, e.g.

```json
{
  "status": "completed",
  "bridge": "freecad_mcp.aieng_bridge.inspect_features",
  "evidence_written": [
    "simulation/cae_imports/parsed_features.json",
    "graph/feature_graph.json"
  ],
  "claim_advancement": "none"
}
```

The provenance block inside each evidence artifact carries the same
`"bridge": "freecad_mcp.aieng_bridge.inspect_features"` field so
reviewers can see which reader produced the data.

### Error mapping (unchanged contract, hardened)

| Bridge raised                          | Tool returns                                      |
|----------------------------------------|---------------------------------------------------|
| `ModuleNotFoundError` / `ImportError`  | `status: skipped, reason: bridge_unavailable`     |
| `RuntimeError` from the bridge call     | `status: skipped, reason: bridge_unavailable`     |
| `FileNotFoundError`                    | `status: error, reason: source_not_found`         |
| Any other `Exception`                  | `status: error, reason: bridge_failed`            |
| Bridge returned `{features: []}`        | `status: partial`, no evidence written            |

All paths preserve `claim_advancement: "none"` and the explicit
claim-boundary statement.

### What v0.16 does NOT add

- **No real FreeCAD-driven implementation.** Today no
  `aieng_freecad_mcp` candidate exposes a read-only feature reader;
  the discovery layer therefore returns `skipped` on every machine
  until a sibling-repo task lands such a function. Tests prove the
  layer works by injecting fake modules into `sys.modules`.
- **No CAD mutation.** The discovery layer only resolves and calls
  read-only candidates declared in `_FREECAD_BRIDGE_CANDIDATES`.
- **No arbitrary FreeCAD command execution.** Only the registered
  attribute names are looked up; no `getattr(module, name_from_user)`
  pattern exists.
- **No solver / mesh / export / edit calls.** Tests explicitly
  monkey-patch those bridge entry points to raise so any accidental
  invocation would fail loudly.
- **No claim advancement.** Every code path locks
  `claim_advancement = "none"`.

### Adding a real reader later

When a safe read-only function is implemented in `aieng_freecad_mcp`,
the entire wiring is one line: append a new
`(module_name, attribute_name, signature_kind)` triple to
`_FREECAD_BRIDGE_CANDIDATES`. The rest of the path — preflight gate,
signature dispatch, error mapping, evidence writeback, project-health
integration, claim-boundary text — is already in place.

## Pilot A v0.17 — real read-only bridge in `aieng_freecad_mcp`

The sibling repo now provides
`freecad_mcp.aieng_bridge.inspect_features(source_path)` — the
preferred candidate the v0.16 discovery layer probes first.

- Lives in `src/freecad_mcp/aieng_bridge/feature_inspector.py`
  (re-exported from `aieng_bridge/__init__.py`).
- Runs a **fixed embedded FreeCAD script** in a controlled
  FreeCADCmd subprocess; caller input never enters the executed code
  — only the validated source path flows in through an env var.
- Opens the document, walks `Document.Objects`, captures safe scalar
  / Quantity / bool / short-string properties, classifies
  `editor_mode` per property, and closes the document
  **without saving** in a `finally`.
- Returns the v0.15/v0.16-compatible
  `{"status": "ok", "features": [{...}]}` shape, with feature
  parameters as a list of `{name, value, unit, kind, editable,
  editor_mode}` entries.
- Errors map cleanly:
  - missing source → `FileNotFoundError`
  - unsupported extension → `ValueError`
  - missing FreeCADCmd / timeout / missing result file / invalid
    JSON / script `status=error` → `RuntimeError`
- The aieng-ui v0.16 discovery layer maps `RuntimeError` /
  `ImportError` to `status: skipped, reason: bridge_unavailable`
  automatically, so a host without FreeCAD still produces a clean
  unavailable response — never a 500.

## Pilot A v0.18 — FreeCAD inspection UI surface

The read-only inspection pipeline is now reachable from the
workbench. The `Copilot Loop` panel renders a new
**FreeCAD feature inspection** card alongside the existing Design
Targets and Computed Metrics cards.

### What the buttons do

- **Inspect FreeCAD features** — calls
  `POST /api/projects/{id}/freecad/inspect-features`. Read-only: no
  CAD edit, no solver, no claim advancement. The response carries
  `status`, `preflight_status`, `bridge` provider label (if a real
  reader was discovered), `feature_count`,
  `editable_parameter_count`, `evidence_written` member list,
  `missing_dependencies`, warnings/errors, and an explicit
  `claim_boundary` statement.
- **Run adapter preflight** — calls
  `GET /api/adapters/freecad/preflight`. Displays the adapter status
  badge (`ready` / `partial` / `unavailable` / `not_ready`), the
  missing-dep list, and any warnings.

### UI states the card handles

- No project selected → empty-state message.
- Idle → buttons enabled.
- Loading → button label flips to "Inspecting…" / "Checking adapter…".
- `completed` with evidence written → green status badge, bridge
  provider, feature/parameter counts, evidence-files list, and a
  prompt "Run Project Health Check again" with a button that calls
  `rerunHealthCheckFromPrompt`.
- `skipped` (preflight unavailable / bridge_unavailable / no source)
  → grey badge, reason explained in plain English, no fake success.
- `partial` (e.g. bridge returned no features) → warning badge with
  a clear explanation.
- `error` (source not found / bridge failed) → red badge with an
  error list; never a 500 to the user.

### Project Health Check navigation

The v0.9 health-action infrastructure now routes two CAD-context
actions to the new card:

- `inspect_cad_features` (new in v0.18) — added when the
  `cad_context` check is warning. Target:
  `{"tab": "copilot_loop", "section": "freecad_inspection", "intent": "navigation"}`.
- `add_editable_params` (existing) — upgraded from `manual` to
  `navigate`. Same target.

Clicking either action's button in the Project Health card scrolls
the user to the FreeCAD Inspection card and briefly highlights it.
No mutation, no execution — pure navigation guidance, consistent
with v0.11.

### Safety boundaries (unchanged)

- The card never edits CAD, never runs solver or mesh, never advances
  claims. It only invokes the existing v0.15 read-only endpoint.
- Missing FreeCAD or missing bridge is surfaced honestly via the
  same `status: skipped` mapping the backend already produces.
- Claim-boundary text from the backend is rendered verbatim inside
  the result panel, alongside the safety note at the top of the
  card.


## FreeCAD inspection evidence viewer (v0.19)

### What it is

A read-only endpoint and corresponding UI state that lets the FreeCAD Inspection
card display evidence that was already generated by a previous inspection —
without requiring the user to re-run FreeCAD.

### Endpoint

```http
GET /api/projects/{project_id}/freecad/inspection-evidence
```

Behavior:
- Reads `simulation/cae_imports/parsed_features.json` and `graph/feature_graph.json` from the `.aieng` package.
- Does **not** run FreeCAD.
- Does **not** call the bridge.
- Does **not** call preflight.
- Does **not** write to the package.

Response:
- `exists: boolean` — whether any readable evidence was found.
- `status: "available" | "missing" | "invalid" | "partial"`.
- `feature_count`, `editable_parameter_count` — computed from the evidence.
- `bridge`, `source`, `generated_at` — extracted from provenance blocks.
- `evidence_artifacts` — list of artifact paths that were read.
- `warnings`, `errors` — structured messages.
- `claim_advancement: "none"`, `claim_boundary` — explicit safety statement.

### UI behavior

When the FreeCAD Inspection card mounts or the project changes, it calls the
evidence endpoint automatically and displays:

- **available** — green badge, bridge provider, feature/parameter counts,
  generation timestamp, artifact list.
- **missing** — grey badge, message: "No FreeCAD inspection evidence found yet.
  Run read-only inspection to generate feature/parameter evidence."
- **partial** — yellow badge, warning about which artifact is missing.
- **invalid** — red badge, errors about JSON parsing failures.

The manual **Inspect FreeCAD features** button remains. After a successful
inspection, the evidence display refreshes automatically.

### Safety boundaries

- No FreeCAD command is executed automatically on mount.
- No CAD mutation.
- No parameter edit.
- No export.
- No mesh generation.
- No solver execution.
- No preflight/bridge call from the evidence GET.
- No claim advancement.
- Missing or invalid evidence is shown honestly.

## Health action evidence refresh (v0.20)

### What changed

Clicking a Project Health recommended action that targets the FreeCAD Inspection
card now performs three things:

1. **Expands** the card if it was collapsed.
2. **Scrolls** the card into view and briefly highlights it.
3. **Refreshes** existing inspection evidence by calling
   `GET /api/projects/{project_id}/freecad/inspection-evidence`.

It does **not** run `POST /freecad/inspect-features`. FreeCAD is never executed
automatically. The user still decides whether to run a new inspection.

### Provenance / freshness display

When existing evidence is available, the card now shows provenance in a
two-column layout:

- **Generated** — timestamp from the evidence provenance block.
- **Source** — e.g. `freecad.inspect_features`.
- **Bridge** — e.g. `freecad_mcp.aieng_bridge.inspect_features`.
- **Features** — count from `parsed_features.json`.
- **Editable parameters** — count from `feature_graph.json`.
- **Claim advancement** — always `none`.
- **Evidence artifacts** — list of package paths.

Missing provenance fields render as "Unknown", never `undefined` or `null`.

### Real FreeCAD integration fixture (v0.22)

A sibling-repo opt-in test (`test_real_freecad_inspect_features.py`) validates the
read-only `inspect_features` bridge against a real `.FCStd` file. It asserts:

- Feature metadata is returned (id, type, parameters).
- The input file SHA-256 digest is unchanged after inspection.

This test is **skipped** when FreeCAD is not installed and does not run in CI.
Developers with FreeCAD can validate locally with:

```bash
AIENG_RUN_FREECAD_INTEGRATION=1 python -m pytest -q -k "real_freecad"
```

The fixture file is `examples/parametric_bracket/freecad/source.FCStd` (reused
from the parametric bracket example).

### Safety boundaries (unchanged)

- No FreeCAD command executed on mount or on navigation.
- No CAD mutation, no parameter edit, no export, no mesh, no solver.
- No preflight/bridge call during evidence refresh.
- No claim advancement.
- Missing/unknown provenance shown honestly.

## Pilot B: Structural adapter capability manifest and readiness card

### What is implemented

AIENG now includes a **non-executing structural adapter contract slice** plus a
Workbench **Structural adapter readiness** card.

Implemented pieces:

- backend capability manifest for:
  - `structural.prepare_solver_run`
  - `structural.generate_mesh`
  - `structural.run_solver`
  - `structural.extract_results`
- read-only preflight endpoint:
  - `GET /api/adapters/structural/preflight`
- frontend readiness card that can run the preflight explicitly and display:
  - `ready` / `partial` / `unavailable`
  - missing dependencies
  - checked paths
  - estimated outputs
  - per-capability approval / mutation / external-process / stale-artifact metadata
  - safety note and claim boundary

### What is not implemented

This pilot slice does **not**:

- generate mesh;
- run Gmsh;
- run CalculiX;
- run FreeCAD;
- parse `.frd` or `.dat` during the readiness check;
- write computed metrics;
- mutate `.aieng` packages;
- advance engineering claims.

### Tools checked by preflight

The structural adapter preflight currently checks for the presence of:

- `aieng_root`
- `freecad_mcp_root`
- `FreeCADCmd`
- `gmsh`
- `ccx`

Missing tools are shown honestly. `unavailable` is not treated as fake success,
and it is not treated as package corruption either; it only means the local host
is not ready for structural execution workflows.

### Why this card matters

This gives the Workbench a visible boundary between:

- **AIENG evidence/review logic**, which can still run without local solvers; and
- **external structural execution backends**, which may or may not be available
  on the current host.

That distinction is important for demos and for future approval-gated runtime
work. The user can now inspect structural readiness without accidentally running
any CAD/CAE tool.

### Current Workbench slice

The Workbench now exposes two Pilot B surfaces:

1. **Structural adapter readiness** ? environment-level preflight for
   `FreeCADCmd`, `gmsh`, `ccx`, `aieng_root`, and `freecad_mcp_root`.
2. **Structural fixture import + solver-run preflight review** ? project-level
   workflow that:
   - explicitly imports a CalculiX `.inp` deck into
     `simulation/runs/{run_id}/solver_input.inp`;
   - runs a read-only structural prepare preview;
   - reports whether mesh / solver settings / load case / input deck / `ccx`
     are all present.

This second surface still does **not** execute mesh generation or solver runs.
It is a review step that helps engineers see whether a future approval-gated
structural rerun is even possible on the current host and package.

### Future steps

Planned next steps for Pilot B remain:

1. mesh preflight / execution fixture behind approval;
2. solver-run fixture behind approval;
3. result extraction fixture;
4. computed metrics refresh and target-comparison refresh.

All of those later steps must preserve claim-boundary semantics and keep missing
external tools visible rather than hidden.
