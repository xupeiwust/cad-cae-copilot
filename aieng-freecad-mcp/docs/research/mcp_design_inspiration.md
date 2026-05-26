# MCP Design Inspiration for aieng-freecad-mcp

Date: 2026-05-13
Based on: [docs/research/github_mcp_landscape.md](./github_mcp_landscape.md)

## 1) Executive summary

This survey confirms a strong strategic position for `aieng-freecad-mcp`.

Many MCP servers provide host control and automation. Very few provide strict engineering boundary discipline:

- evidence separated from claim status,
- explicit claim update operations,
- provenance writeback,
- guarded mutation with transparent unsupported/needs_review states,
- standalone mode plus optional semantic package enhancement.

Best path forward is not feature parity. Best path is selective adoption of high-signal patterns (inspection depth, side-effect cataloging, visual evidence artifacts, runtime capability reporting, dry-run metadata) while preserving strict policy boundaries.

## 2) Surveyed projects table

| Project | Repo URL | Stars* | Host/domain | Tools exposed | Execution model | Read-only support | Mutating support | Guardrails | Evidence/provenance support | Tests/CI visible | Fit | Recommended action |
|---|---|---:|---|---|---|---|---|---|---|---|---|---|
| Blender MCP | https://github.com/ahujasid/blender-mcp | 21.6k | Blender | Scene inspect/edit, screenshot, `execute_blender_code` | Addon + MCP bridge | Yes | Yes | Warning on arbitrary code tool | Telemetry, not engineering evidence policy | Actions visible | Medium | Adapt idea (visual loop only) |
| FreeCAD MCP (neka-nat) | https://github.com/neka-nat/freecad-mcp | 937 | FreeCAD | CAD ops, views, FEM run, execute code | FreeCAD addon + RPC + MCP | Yes | Yes | Remote IP allowlist, but includes arbitrary code tool | No claim/evidence policy separation | Limited visibility | High | Adapt idea |
| FreeCAD MCP (contextform) | https://github.com/contextform/freecad-mcp | 72 | FreeCAD | Part/PartDesign/view/script operations | Bridge/service | Some | Yes | Convenience-centric | No explicit engineering evidence policy | `tests/` present | Medium | Monitor |
| KiCad MCP (Seeed) | https://github.com/Seeed-Studio/kicad-mcp-server | 37 | EDA | Schematic/PCB/netlist/ERC/DRC/edit/export | Python + kicad-cli | Strong | Yes | Explicit editing limitations | Validation output but no claims ledger | `tests/` present | High | Adopt/adapt ideas |
| KiCad MCP (mixelpixx) | https://github.com/mixelpixx/KiCAD-MCP-Server | 996 | EDA | Broad design automation + routing + exports | Node/Python hybrid | Strong | Strong | Disclaimers and docs; broad scope | Logs/traceability aids, no claim policy analog | `tests/`, `.github` | Medium | Monitor/adapt selective ideas |
| CadQuery MCP (rishigundakaram) | https://github.com/rishigundakaram/cadquery-mcp-server | 12 | Parametric CAD | Verify, generate stub, STEP/STL/SVG | Python server | Moderate | Moderate | Script shape conventions | PASS/FAIL verify semantics only | `tests/` + evals | High | Adapt idea |
| CadQuery MCP (bertvanbrakel) | https://github.com/bertvanbrakel/mcp-cadquery | 16 | Parametric CAD | Execute script, scan library, search, export | SSE/stdio | Moderate | Yes | Broad script execution surface | No claim policy discipline | Testing emphasized | Medium | Adapt with stricter guards |
| ParaView MCP | https://github.com/LLNL/paraview_mcp | 44 | Scientific visualization | Pipeline control + viewport feedback | ParaView + MCP | Strong | Visualization mutation | Runtime caveat disclaimer | Visualization-focused evidence only | Limited visibility | High (post-processing) | Adapt idea |
| VTK MCP | https://github.com/Kitware/vtk-mcp | 6 | VTK docs/search | Class info + search tools | stdio/http | Strong | Minimal | Narrow API with clear boundaries | Not claim/evidence focused | Good test matrix + CI | High | Adopt/adapt quality practices |
| PyVista MCP | https://github.com/pyvista/pyvista-mcp-server | 6 | Visualization | Simple HTML visualization tool | Python MCP | Basic | Basic | Narrow scope | Artifact-only posture | Basic hygiene | Medium | Monitor |
| OpenFOAM MCP | https://github.com/webworn/openfoam-mcp-server | 94 | CFD | Tool-rich CFD + educational assistant features | C++ server + OpenFOAM integration | Some | Yes | Rich docs, broad autonomy framing | No explicit evidence-vs-claim separation | `.github`, `tests/` | Medium-low | Monitor; avoid autonomy pattern |
| EnergyPlus MCP | https://github.com/LBNL-ETA/EnergyPlus-MCP | 86 | Building simulation | 35 tools across inspect/modify/sim/results | Python + Docker/devcontainer | Strong | Strong | Good transport/auth fail-closed patterns | No explicit claim map policy | Tests documented | High | Adapt idea |
| SolidWorks MCP | https://github.com/eyfel/mcp-server-solidworks | 84 | Proprietary CAD | Context streams + adapter architecture docs | Python + C# adapter + COM bridge | Likely | Likely | Security/filter logic mentioned | No evidence/claim policy visible | Unknown | Medium | Monitor/adapt architecture |
| Onshape MCP | https://github.com/BLamy/onshape-mcp | 11 | Cloud CAD | Minimal public details | TypeScript package | Unknown | Unknown | Not enough detail | Unknown | Unknown | Low | Monitor |
| Abaqus MCP | https://github.com/jianzhichun/abaqus-mcp-server | 70 | Abaqus GUI | Execute script in GUI + message log scrape | GUI automation via pywinauto | Weak | Strong but fragile | Explicit GUI fragility notes | No evidence/claim discipline | Single test visible | Low | Avoid |
| OpenSCAD MCP | https://github.com/jhacksman/OpenSCAD-MCP-Server | 150 | OpenSCAD/image-to-3D | Multi-stage generation/export pipelines | Python server + external services | Moderate | Strong | Approval workflow present but broad autonomy | No engineering claim policy separation | Many test scripts | Low-medium | Monitor selective UX ideas |

*Stars observed on 2026-05-13.

## 3) Useful design patterns to consider

### A. Read-only inspection depth

- Structured object tree and feature/parameter table summaries.
- Explicit capability-dependent inspection behavior (return unsupported/missing, not silence).
- Netlist-like dependency tracing pattern (from KiCad style), adapted to CAD feature dependency and CAE target linkage.

### B. Side-effect catalog (machine-readable)

Adopt a registry that describes per-tool side effects and runtime prerequisites.

Suggested fields:

- `read_only`
- `mutates_cad`
- `mutates_package`
- `writes_artifacts`
- `writes_evidence`
- `writes_trace`
- `may_update_claim_map`
- `requires_freecad`
- `requires_solver`
- `supports_dry_run`
- `supports_standalone`
- `supports_aieng_enhanced`

### C. Visual feedback as evidence artifacts

- CAD screenshot/SVG/thumbnail export for inspection checkpoints.
- Optional CAE/post-processing quicklook artifacts (field snapshots, scalar overlays).
- Persist as evidence artifacts only; never interpret visual quality as claim status.

### D. Dry-run and explicit apply

- Introduce dry-run previews for mutating operations.
- Return planned side effects before mutation.
- Keep final mutation as explicit user action.

### E. Runtime capability reporting

- Stronger capability report for host app, workbenches, solvers, meshers, headless support.
- Fail-open for tests: missing optional runtime should produce `unavailable_runtime`/`unsupported`, not test collapse.

### F. Post-processing adapters

- VTK/ParaView/PyVista-inspired post-processing adapter path.
- Keep adapter output as deterministic artifacts + extracted observations.

### G. Adapter abstraction for future hosts

- Host-specific adapters under a common contract (FreeCAD now, CadQuery/ParaView later).
- Preserve `.aieng` semantics above adapter layer (host-agnostic package truth).

## 4) Risky patterns to avoid

- Arbitrary Python execution tools (`execute_code`, `execute_*_script`) as normal public API.
- Arbitrary shell execution tools.
- Autonomous CAD→CAE→claim pipelines with hidden orchestration.
- Implicit claim advancement after artifact generation.
- Solver success interpreted as claim pass.
- Visual quality interpreted as engineering validation.
- Hidden file/package mutation without side-effect metadata.
- Weak/no explicit unsupported/missing/not_found/needs_review states.
- Broad mutating tools with ambiguous effect boundaries.

## 5) Project-by-project notes

### Blender MCP (ahujasid)

- What we can learn: screenshot feedback loop and bridge ergonomics.
- What to avoid: arbitrary code execution path.
- Fit: medium.
- Action: adapt visual-loop idea only.

### FreeCAD MCP (neka-nat)

- What we can learn: practical FreeCAD host integration and remote controls.
- What to avoid: `execute_code` pathway.
- Fit: high.
- Action: adapt connection/runtime capability patterns.

### FreeCAD MCP (contextform)

- What we can learn: onboarding and tool discoverability.
- What to avoid: broad automation framing without strict policy contract.
- Fit: medium.
- Action: monitor and selectively adapt UX/documentation ideas.

### KiCad MCP (Seeed)

- What we can learn: read-only analysis richness, explicit checks, clear editing limitations.
- What to avoid: conflating checks with claims.
- Fit: high.
- Action: adopt/adapt inspection and limitation-reporting patterns.

### KiCad MCP (mixelpixx)

- What we can learn: tool inventory discipline and user-facing docs.
- What to avoid: too-broad workflow coupling inside one tool surface.
- Fit: medium.
- Action: monitor and adapt docs/tool inventory patterns.

### CadQuery MCP (rishigundakaram, bertvanbrakel)

- What we can learn: script verification, part-library indexing, lightweight previews.
- What to avoid: unrestricted script execution.
- Fit: high/medium.
- Action: adapt verify/preview patterns with strict sandbox/guards.

### ParaView/VTK/PyVista MCP

- What we can learn: post-processing and visualization artifact pathways.
- What to avoid: visual success becoming claim evidence by itself.
- Fit: high (as post-processing extension).
- Action: adapt with strict evidence-vs-claim policy.

### OpenFOAM MCP

- What we can learn: explicit capability/status matrices and domain segmentation.
- What to avoid: educational/autonomous assistant framing in core execution path.
- Fit: medium-low.
- Action: monitor only.

### EnergyPlus MCP

- What we can learn: strong tool taxonomy, layered architecture, auth/transport hardening.
- What to avoid: simulation completion interpreted as validation.
- Fit: high.
- Action: adapt config/auth and category structuring.

### SolidWorks MCP

- What we can learn: version-aware adapter architecture and context streaming.
- What to avoid: proprietary lock-in assumptions.
- Fit: medium.
- Action: monitor/adapt architecture abstractions only.

### Onshape MCP

- What we can learn: too little public detail currently.
- What to avoid: over-investing based on weak signal.
- Fit: low.
- Action: monitor.

### Abaqus GUI MCP

- What we can learn: explicit statement of automation fragility.
- What to avoid: GUI-script execution as trusted core path.
- Fit: low.
- Action: avoid.

### OpenSCAD MCP (jhacksman)

- What we can learn: explicit approval stages and artifact-centric flows.
- What to avoid: broad autonomous multi-service pipeline in core engineering truth path.
- Fit: low-medium.
- Action: monitor selective approval UX only.

## 6) Feature ideas ranked by fit

### High fit (implement sooner)

### Idea: Machine-readable tool side-effect catalog

Source inspiration:
- EnergyPlus MCP (clear tool categories)
- KiCad MCP docs/tool inventories
- VTK MCP narrow, explicit tool contracts

Problem it solves:
- Tool safety and orchestration ambiguity.

How to adapt safely:
- Add registry JSON/YAML linked from tool contracts and docs.

Required guardrails:
- Explicit side effects and runtime requirements for every mutating tool.

Interaction with `.aieng`:
- standalone behavior: report capabilities/side effects, no package writes unless explicitly requested.
- `.aieng`-enhanced behavior: include package write intents and claim-map mutation eligibility.

Evidence / trace behavior:
- Registry declares whether each tool writes evidence/trace.

Claim policy:
- claims_advanced must remain false unless explicit aieng_update_claim is used

Fit:
- high

Recommended priority:
- now

### Idea: Read-only CAD feature and parameter inspection summary

Source inspiration:
- KiCad schematic/netlist inspection depth
- VTK information tools

Problem it solves:
- Hard to reason about editability and guard outcomes before mutation.

How to adapt safely:
- Add explicit inspection endpoints that never mutate and surface unsupported/missing fields.

Required guardrails:
- No hidden recompute or writes.

Interaction with `.aieng`:
- standalone behavior: host-only feature introspection.
- `.aieng`-enhanced behavior: overlay feature graph/editability/constraints references.

Evidence / trace behavior:
- Optional evidence record only when explicitly requested.

Claim policy:
- claims_advanced must remain false unless explicit aieng_update_claim is used

Fit:
- high

Recommended priority:
- now

### Idea: Optional CAD visual preview artifacts

Source inspiration:
- Blender screenshots, FreeCAD view tools, ParaView viewport loop

Problem it solves:
- Human verification of geometry states is slow without quicklook artifacts.

How to adapt safely:
- Add optional screenshot/SVG/thumbnail tools with explicit artifact outputs.

Required guardrails:
- Visual output labeled as observational artifact only.

Interaction with `.aieng`:
- standalone behavior: return artifact paths in tool output.
- `.aieng`-enhanced behavior: persist as evidence artifacts with trace links.

Evidence / trace behavior:
- Record producer/runtime and artifact checksums.

Claim policy:
- claims_advanced must remain false unless explicit aieng_update_claim is used

Fit:
- high

Recommended priority:
- now

### Idea: Runtime capability report expansion

Source inspiration:
- EnergyPlus config/runtime checks
- OpenFOAM status matrix style (adapted, non-autonomous)

Problem it solves:
- Runtime surprises and brittle orchestration.

How to adapt safely:
- Expand capability schema for workbench/solver/mesher/headless signals.

Required guardrails:
- Optional dependencies never break default tests.

Interaction with `.aieng`:
- standalone behavior: host-only capability report.
- `.aieng`-enhanced behavior: include task-spec compatibility hints.

Evidence / trace behavior:
- No evidence write by default (read-only capability report).

Claim policy:
- claims_advanced must remain false unless explicit aieng_update_claim is used

Fit:
- high

Recommended priority:
- now

### Idea: Dry-run metadata for mutating tools

Source inspiration:
- Approval workflows and staged mutation patterns in CAD/3D projects

Problem it solves:
- Risky edits without clear preflight transparency.

How to adapt safely:
- Add `dry_run=true` paths returning planned side effects, guard outcomes, and required approvals.

Required guardrails:
- Dry-run must never mutate CAD/package state.

Interaction with `.aieng`:
- standalone behavior: preview host-side impact.
- `.aieng`-enhanced behavior: preview package writes and reference-map impacts.

Evidence / trace behavior:
- Trace can log dry-run operation; no evidence claim linkage needed.

Claim policy:
- claims_advanced must remain false unless explicit aieng_update_claim is used

Fit:
- high

Recommended priority:
- now

### Medium fit (research spike)

- ParaView/VTK post-processing adapter scaffold.
- CadQuery regeneration adapter scaffold.
- Richer error taxonomy normalization (`unsupported`, `missing`, `not_found`, `needs_review`, `unavailable_runtime`, `rejected_by_guard`).

### Low fit / avoid

- Autonomous workflow planner inside MCP.
- Natural-language direct unconstrained B-rep editing.
- Arbitrary execution tools.

## 7) Explicit do-not-adopt list

- Do not add arbitrary Python execution as a normal public tool.
- Do not add arbitrary shell execution.
- Do not auto-trigger CAE after CAD edits.
- Do not require CAD edits before CAE.
- Do not auto-advance claims after evidence generation.
- Do not equate solver success with engineering validation.
- Do not equate visual success with engineering validation.
- Do not make `.aieng` mandatory.
- Do not make FreeCAD/FEM/CalculiX mandatory for default tests.
- Do not convert MCP into an autonomous workflow planner.
- Do not hide unsupported/missing/not_found/needs_review states.
- Do not add broad mutating tools without side-effect metadata.
- Do not weaken guard/evidence/trace/claim policy discipline.

## 8) Recommended next improvements for `aieng-freecad-mcp`

1. Add machine-readable tool side-effect catalog and publish in docs.
2. Add stronger read-only CAD feature/parameter inspection summary tools.
3. Add optional CAD visual preview artifact export (screenshot/SVG/thumbnail) as evidence artifacts.
4. Add expanded runtime capability report (host, workbenches, solver/mesher availability, headless status).
5. Add dry-run metadata mode for all mutating operations.
6. Add documented and enforced richer error taxonomy across tool outputs.
7. Start post-processing adapter spike for VTK/ParaView-style artifact workflows.
8. Start CadQuery adapter spike focused on guarded regeneration and artifact export.

## 9) Open questions

1. Should side-effect catalog live in `docs/tool_contract.md`, a dedicated schema, or both?
2. What minimum preview artifact set is acceptable without adding heavy runtime dependencies?
3. Should dry-run be a universal flag on mutating tools or separate preview tools per operation family?
4. What should be the canonical severity taxonomy for warnings vs unsupported vs rejected_by_guard?
5. What is the preferred adapter boundary (module-level interfaces vs protocol-based plugin system)?
6. How should post-processing adapters write evidence while remaining host-agnostic?
7. What acceptance tests should gate future adapters to guarantee no claim auto-advance?

---

## Top 5 ideas to adopt soon

1. Machine-readable tool side-effect catalog.
2. Stronger read-only CAD feature/parameter inspection.
3. Optional CAD visual preview artifact export.
4. Expanded runtime capability reporting.
5. Dry-run metadata mode for mutating tools.

## Top 5 ideas to monitor later

1. VTK/ParaView post-processing adapter.
2. CadQuery regeneration adapter.
3. Proprietary CAD adapter abstraction patterns (SolidWorks/Onshape).
4. Advanced visualization pipelines with field overlays.
5. Domain-specific validation helper templates (without claim auto-updates).

## Top 5 patterns to avoid

1. Arbitrary Python/shell execution tools.
2. Autonomous CAD→CAE→claim workflow planning.
3. Solver-success-to-claim-pass shortcuts.
4. Visual-render-to-validation shortcuts.
5. Hidden package mutation and implicit side effects.

## Concrete next GitHub issues to create

1. Add machine-readable tool side-effect catalog and schema.
2. Add read-only CAD feature/parameter inspection summary tool set.
3. Add optional CAD preview artifact export (screenshot/SVG/thumbnail).
4. Add richer runtime capability report (workbench/solver/mesher/headless).
5. Add dry-run support and preview contract for mutating tools.
6. Add error taxonomy spec (`unsupported`, `missing`, `not_found`, `needs_review`, `unavailable_runtime`, `rejected_by_guard`).
7. Add VTK/ParaView post-processing adapter research spike.
8. Add CadQuery regeneration adapter research spike.
9. Add policy tests asserting no automatic claim advancement across all mutating tools.
