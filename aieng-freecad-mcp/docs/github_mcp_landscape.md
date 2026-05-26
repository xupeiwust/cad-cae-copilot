# GitHub MCP Landscape for CAD/CAE, 3D Modeling, Simulation, and Engineering Workflows

Date: 2026-05-13

This research note surveys public GitHub/MCP projects related to CAD, CAE, 3D modeling, simulation, scientific visualization, and engineering workflows. It is intended as inspiration for `aieng-freecad-mcp`, not as an endorsement list or dependency list.

## Executive conclusion

Most public CAD/3D/engineering MCP projects focus on direct host-application control, scene/model generation, visualization, or domain-specific automation. Very few expose an auditable engineering evidence layer, explicit claim policy, reference mapping, or `.aieng`-style semantic context.

This leaves a clear differentiation space for `aieng-freecad-mcp`:

- standalone CAD/CAE MCP usability
- optional `.aieng` semantic/evidence enhancement
- standard result contract
- evidence and provenance persistence
- explicit claim update discipline
- reference mapping and `needs_review`
- composable paths rather than fixed autonomous workflows

## Summary table

| Project | Repo / source | Host application | Main pattern | Guardrails / evidence discipline | Relevance |
|---|---|---|---|---|---|
| Blender MCP by ahujasid | https://github.com/ahujasid/blender-mcp | Blender | Live 3D scene control via Blender addon + MCP bridge | Warns arbitrary Python can be dangerous; not engineering evidence-focused | Strong demo/UX inspiration; avoid raw code execution as default |
| FreeCAD MCP by contextform | https://github.com/contextform/freecad-mcp | FreeCAD | Natural-language FreeCAD automation | Tool execution focus; no visible `.aieng`-style evidence/claim layer | Direct category peer; compare setup and tool coverage |
| CADQuery MCP Server | https://github.com/rishigundakaram/cadquery-mcp-server | CadQuery / OCCT | Script verification and STEP/STL/SVG export | Basic verification, no engineering claim ledger | Useful for parametric script verification and preview artifacts |
| ParaView MCP by LLNL | https://github.com/LLNL/paraview_mcp | ParaView | Scientific visualization control with viewport feedback | Visualization-oriented, not claim/evidence ledger | Strong future inspiration for post-processing and visual evidence |
| OpenFOAM MCP Server | https://github.com/webworn/openfoam-mcp-server | OpenFOAM | CFD education, setup guidance, solver workflows | Educational/context workflow, not `.aieng` claim policy | Useful CAE guidance patterns; avoid subjective tutor behavior by default |
| KiCad MCP Server by Seeed Studio | https://github.com/Seeed-Studio/kicad-mcp-server | KiCad | Schematic/PCB inspection, net tracing, ERC/DRC, editing | Explicit validation tools, good tests/docs; no `.aieng` claim ledger | Very useful pattern for read-only inspection + design-rule checks |
| SolidWorks MCP by eyfel | https://github.com/eyfel/mcp-server-solidworks | SolidWorks | CAD context streaming through SolidWorks API | Context-streaming focus, not evidence ledger | Useful pattern for proprietary CAD adapter layers |
| OpenSCAD MCP listings | public MCP listings | OpenSCAD | Parametric model generation | Varies | Useful for text-to-parametric CAD ideas, but keep evidence discipline |
| Awesome Physical Engineering AI | https://github.com/010zx00x1/Awesome-Physical-Engineering-AI | Cross-tool list | Curated engineering AI/MCP ecosystem | Not a server | Useful ongoing discovery source |

## Project notes

### 1. Blender MCP by ahujasid

- Repo: https://github.com/ahujasid/blender-mcp
- Host application: Blender
- Stars observed: about 21k+ at time of research.
- Tools / capabilities: scene creation and manipulation, objects, materials, lighting, viewport/screenshot feedback, and arbitrary Blender Python execution.
- Execution model: Blender addon plus MCP bridge communicating over a JSON/TCP-style protocol.
- Read-only inspection: yes, scene and viewport observation.
- Mutating operations: yes, extensive scene/model mutation.
- Guardrails: README warns `execute_blender_code` can run arbitrary Python and should be used cautiously.
- Evidence/provenance: not focused on engineering evidence, claims, or audit ledgers.
- Tests: not reviewed in depth.

What we can learn:

- Demo quality matters.
- Live viewport/screenshot feedback is powerful.
- Two-process host-application bridge is a practical pattern for GUI-heavy tools.

What we should avoid:

- Do not make arbitrary Python execution a normal CAD/CAE path.
- Do not treat visual success as engineering validity.
- Do not copy autonomous scene-generation framing into engineering validation workflows.

### 2. FreeCAD MCP by contextform

- Repo: https://github.com/contextform/freecad-mcp
- Host application: FreeCAD
- Stars observed: about 70+ at time of research.
- Tools / capabilities: PartDesign and Part operations, primitives, booleans, transforms, view control, screenshots, and custom Python scripts.
- Execution model: FreeCAD workbench/service plus bridge server.
- Read-only inspection: yes, likely view/object/document inspection.
- Mutating operations: yes, object creation and modification.
- Guardrails: focused on FreeCAD automation; public README does not present an evidence/claim discipline.
- Evidence/provenance: no visible `.aieng`-style ledger.
- Tests: not reviewed in depth.

What we can learn:

- Simple install and onboarding matter.
- FreeCAD users want conversational CAD automation.
- View/screenshot operations are useful for feedback.

What we should avoid:

- Avoid being only another FreeCAD automation wrapper.
- Avoid broad script tools without standard result/evidence/trace discipline.

### 3. CADQuery MCP Server

- Repo: https://github.com/rishigundakaram/cadquery-mcp-server
- Host application/library: CadQuery / OCCT
- Stars observed: about a dozen at time of research.
- Tools / capabilities: `verify_cad_query`, stub `generate_cad_query`, STL/STEP export, SVG generation.
- Execution model: local Python MCP server validating or running CadQuery scripts.
- Read-only inspection: verification and SVG preview can be inspection-oriented.
- Mutating operations: generation/export writes artifacts, but does not mutate a live GUI model.
- Guardrails: requires scripts to follow a known `show_object(result)` convention.
- Evidence/provenance: basic pass/fail verification, no `.aieng` claim/evidence ledger.
- Tests: repo includes tests/evaluations.

What we can learn:

- Parametric-script verification is a good companion to FreeCAD GUI automation.
- SVG/preview artifacts are useful lightweight inspection outputs.
- CadQuery/OCP could become a controlled regeneration backend.

What we should avoid:

- Do not treat verification PASS as engineering validation without criteria/evidence.
- Avoid unsandboxed arbitrary script execution.

### 4. ParaView MCP by LLNL

- Repo: https://github.com/LLNL/paraview_mcp
- Host application: ParaView
- Stars observed: about 20+ at time of research.
- Tools / capabilities: scientific visualization control, viewport observation, natural-language manipulation of visualization pipelines.
- Execution model: ParaView server/GUI plus MCP server.
- Read-only inspection: yes, viewport/state observation.
- Mutating operations: yes, visualization pipeline changes.
- Guardrails: visualization-focused; not reviewed as engineering validation system.
- Evidence/provenance: not `.aieng`-style.
- Tests: not reviewed.

What we can learn:

- Visual feedback is valuable for post-processing.
- ParaView/VTK integration could be a strong future path for field-data evidence.
- Scientific visualization state can be exposed to agents in structured form.

What we should avoid:

- Do not let visualizations become implicit validation.
- Keep screenshots/VTK/CSV as evidence artifacts, not claims.

### 5. OpenFOAM MCP Server

- Repo: https://github.com/webworn/openfoam-mcp-server
- Host application: OpenFOAM
- Tools / capabilities: CFD case analysis, educational guidance, physics calculations, solver/case workflows, Socratic questioning, error resolution.
- Execution model: native/C++ OpenFOAM-oriented MCP architecture.
- Read-only inspection: likely case/config inspection.
- Mutating operations: likely case generation/editing and solver execution.
- Guardrails: educational guidance; not `.aieng` claim/evidence ledger.
- Evidence/provenance: no visible `.aieng`-style claim policy.
- Tests: not reviewed.

What we can learn:

- CAE users need diagnostics and error explanations.
- Solver setup assistance can be valuable because CAE has high expertise barriers.
- Runtime/case validation is important.

What we should avoid:

- Avoid making `aieng-freecad-mcp` a subjective tutor by default.
- Avoid solver recommendations that look like validation claims.

### 6. KiCad MCP Server by Seeed Studio

- Repo: https://github.com/Seeed-Studio/kicad-mcp-server
- Host application: KiCad
- Stars observed: about 30+ at time of research.
- Tools / capabilities: schematic analysis, PCB analysis, netlist tracing, ERC/DRC, pin analysis, project creation, Gerber export, code generation.
- Execution model: Python MCP server using KiCad APIs and `kicad-cli`.
- Read-only inspection: yes, extensive schematic/PCB inspection.
- Mutating operations: yes, project creation/editing/export operations.
- Guardrails: README documents editing limitations and recommends GUI for design work in some cases.
- Evidence/provenance: has explicit design validation tools, but no `.aieng` claim ledger.
- Tests: repository contains tests.

What we can learn:

- Read-only inspection can be as important as mutation.
- Validation tools should remain explicit operations.
- Headless CLI checks are useful for CI-friendly engineering workflows.
- Documenting editing limitations is important.

What we should avoid:

- Avoid combining DRC/solver/check execution with automatic claim updates.
- Avoid adding many tools without clear side-effect taxonomy.

### 7. SolidWorks MCP by eyfel

- Repo: https://github.com/eyfel/mcp-server-solidworks
- Host application: SolidWorks
- Tools / capabilities: public README emphasizes SolidWorks API integration and Claude-compatible context streams.
- Execution model: modular SolidWorks API / COM-style bridge.
- Read-only inspection: context streaming suggests strong inspection/context export orientation.
- Mutating operations: likely possible through SolidWorks automation, not reviewed in depth.
- Guardrails: not evaluated.
- Evidence/provenance: not `.aieng`-style.
- Tests: not reviewed.

What we can learn:

- Proprietary CAD needs adapter layers and version-aware bridges.
- Context export from CAD into LLM-readable streams is a useful pattern.

What we should avoid:

- Avoid tying engineering truth to one proprietary CAD API.
- Avoid undocumented version-specific automation.

## Cross-project patterns

### Useful patterns

1. Two-process bridge for GUI tools.
2. Read-only inspection is essential.
3. Visual feedback is compelling.
4. Runtime/capability detection matters.
5. Local execution dominates engineering MCPs.

### Risks to avoid

1. Arbitrary Python/shell execution as a normal pathway.
2. Strong autonomous workflow assumptions.
3. Weak evidence/provenance discipline.
4. Visual success mistaken for engineering validity.
5. Validation ambiguity, where checks or solver runs are treated as implicit claims.

## Inspiration items for `aieng-freecad-mcp`

1. Add visual feedback artifacts later.
2. Strengthen read-only inspection tools.
3. Keep runtime detection prominent.
4. Consider future adapter families:
   - `aieng-solidworks-mcp`
   - `aieng-onshape-mcp`
   - `aieng-cadquery-mcp`
   - `aieng-paraview-mcp`
   - `aieng-openfoam-mcp`
5. Add approval/dry-run patterns for high-risk mutation.
6. Develop field-data post-processing path.
7. Make side effects machine-readable.

## Differentiation

Most surveyed projects expose tool control. `aieng-freecad-mcp` adds:

- optional `.aieng` semantic/evidence context
- standalone mode plus `.aieng`-enhanced mode
- standard result contract
- evidence/provenance persistence
- explicit claim policy
- reference mapping and `needs_review`
- claim update separated from evidence generation
- composable paths instead of fixed autonomous workflow
- conservative treatment of surrogate, solver, and post-processing evidence

This is a significant distinction from ordinary 3D/CAD MCP wrappers.

## Recommended next improvements

1. Neutralize planner language.
2. Add a tool side-effect catalog.
3. Improve visual artifact support.
4. Strengthen real runtime demos.
5. Explore VTK/ParaView/PyVista path.
6. Preserve strict claim discipline.
7. Avoid raw code execution tools.

## Bottom line

The public MCP landscape has several useful CAD/3D/simulation examples, but most focus on direct control or generation. The clearest opportunity for `aieng-freecad-mcp` is to remain a composable, planning-neutral CAD/CAE execution interface that becomes safer and more auditable when paired with `.aieng` semantic/evidence packages.
