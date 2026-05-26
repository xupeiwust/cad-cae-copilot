# GitHub MCP Landscape: CAD/CAE/3D/Simulation

Date: 2026-05-13
Scope: Public GitHub projects related to MCP + CAD/CAE/3D/simulation workflows.

## Method and limits

- Sources used: public GitHub repository pages and metadata from GitHub API where available.
- Search terms used: blender mcp, freecad mcp, cad mcp, cae mcp, cadquery mcp, openscad mcp, paraview mcp, vtk mcp, pyvista mcp, openfoam mcp, kicad mcp, solidworks mcp, onshape mcp, simulation mcp.
- Limitation encountered: GitHub API returned intermittent HTTP 403 on some repositories during metadata fetch. For those, this note falls back to repository page information.

## Current project baseline to preserve

`aieng-freecad-mcp` already has patterns many peers do not:

- Standard result contracts (`StandardToolResult`, `EvidenceBlock`, `TraceBlock`, `ClaimPolicy`)
- Optional `.aieng` context loading and dual operation modes (standalone + `.aieng`-enhanced)
- Guard checks and protected/semantic edit discipline
- Evidence/provenance persistence
- `reference_map` and `needs_review` handling
- Explicit `aieng_update_claim` as the only claim-advancing path
- Composable workflow paths (CAD-only, CAE-only, optional CAD→CAE orchestration, reference mapping, explicit claim update)
- Runtime capability detection and planning-neutral capability exposure

## Survey table

| Project | Repo | Stars* | Host/domain | Read-only inspection | Mutating support | Guardrails and side-effect discipline | Evidence/provenance posture | Tests/CI signals | Fit for `aieng-freecad-mcp` | Recommended action |
|---|---|---:|---|---|---|---|---|---|---|---|
| Blender MCP | https://github.com/ahujasid/blender-mcp | 21.6k | Blender scene modeling | Yes (scene info, screenshots) | Yes (create/edit/delete, materials, code execution) | Explicit arbitrary Python tool warning; broad power | No explicit engineering evidence/claim layer | Actions present; tests not emphasized in README | Medium | Adapt selected UX ideas; avoid execution model |
| FreeCAD MCP (neka-nat) | https://github.com/neka-nat/freecad-mcp | 937 | FreeCAD CAD/FEM control | Yes (object/view tools) | Yes (create/edit/delete, execute code, FEM run) | Remote IP allowlist controls; still includes arbitrary code tool | No explicit evidence/claim policy layer | Active repo; tests not highlighted | High | Adapt selective patterns, avoid arbitrary code tool |
| FreeCAD MCP (contextform) | https://github.com/contextform/freecad-mcp | 72 | FreeCAD natural-language CAD | Some (view, document context) | Yes (part ops + script path) | Convenience-focused; includes Python execution | No `.aieng`-style evidence/claim separation | `tests/` exists | Medium | Monitor and borrow onboarding ideas |
| KiCad MCP (Seeed) | https://github.com/Seeed-Studio/kicad-mcp-server | 37 | EDA schematic/PCB analysis | Strong (schematic/PCB/netlist/validation) | Yes (project/edit/export) | Explicit editing limitations; headless ERC/DRC | Validation outputs, but not claim policy ledger | `tests/` present | High | Adopt/adapt inspection + explicit limitation style |
| KiCad MCP (mixelpixx) | https://github.com/mixelpixx/KiCAD-MCP-Server | 996 | EDA full workflow | Strong | Strong | Large tool inventory, trace logs/visual feedback; broad automation surface | Operational logs but no engineering claim policy discipline | `tests/`, `.github`, active CI patterns | Medium | Monitor for tooling maturity patterns |
| CadQuery MCP (rishigundakaram) | https://github.com/rishigundakaram/cadquery-mcp-server | 12 | Scripted parametric CAD | Moderate (verify + SVG) | Limited generation/export | Script conventions (`show_object`) and verify step | Verification-oriented, not evidence/claims ledger | `tests/` + evaluations | High | Adapt verification/preview pattern |
| CadQuery MCP (bertvanbrakel) | https://github.com/bertvanbrakel/mcp-cadquery | 16 | Scripted parametric CAD | Moderate (scan/search/preview) | Strong script execution/export | Broad `execute_cadquery_script` surface (arbitrary script risk) | No claim/evidence discipline | Strong testing focus in README | Medium | Adapt library/preview ideas; avoid raw execution path |
| ParaView MCP | https://github.com/LLNL/paraview_mcp | 44 | Scientific visualization | Strong viewport feedback | Visualization pipeline mutations | Declares architecture caveats; autonomous language | Visual workflow focus, not claim policy | Research-oriented repo; tests not prominent | High (post-processing only) | Adapt for evidence artifacts only |
| VTK MCP | https://github.com/Kitware/vtk-mcp | 6 | VTK docs + semantic search | Strong read-only docs tooling | Minimal mutation | Narrow tools, clear API boundaries | Documentation tooling, not engineering evidence | Clear testing matrix and CI | High (for inspection tooling style) | Adapt tool minimalism and test structure |
| PyVista MCP | https://github.com/pyvista/pyvista-mcp-server | 6 | Lightweight visualization | Basic | Basic HTML export | Narrow scope; low-risk by design | Artifact generation only | OSS hygiene; tests not prominent | Medium | Monitor for visualization adapter scaffold |
| OpenFOAM MCP | https://github.com/webworn/openfoam-mcp-server | 94 | CFD + educational assistant | Some (mesh/STL/result analysis) | Yes (OpenFOAM ops) | Heavy educational/autonomous framing; broad workflow narratives | Mixes analysis guidance with educational outputs; no claim discipline | `.github`, `tests/`, C++ architecture docs | Medium-low | Monitor selectively; avoid autonomous framing |
| EnergyPlus MCP | https://github.com/LBNL-ETA/EnergyPlus-MCP | 86 | Building simulation | Strong model inspection tools | Strong model mutation + simulation | Good config/auth patterns (HTTP tokens fail-closed) | Robust simulation ops, not claim/evidence distinction | Tests documented (`test_config_transport`, `test_auth`) | High | Adapt runtime config/auth and tool taxonomy patterns |
| SolidWorks MCP | https://github.com/eyfel/mcp-server-solidworks | 84 | Proprietary CAD adapter | Context-stream focus | Not clearly documented in README | Version-aware adapter architecture emphasis | No visible evidence/claim policy | Limited public implementation detail | Medium | Monitor architecture idea, avoid assumptions |
| Onshape MCP | https://github.com/BLamy/onshape-mcp | 11 | Cloud CAD | Unknown | Unknown | Minimal docs; immature | Unknown | Limited visible testing | Low | Monitor only |
| Abaqus MCP (GUI scripting) | https://github.com/jianzhichun/abaqus-mcp-server | 70 | Abaqus GUI automation | Message log scrape | Executes Python in live GUI | Explicitly GUI-sensitive; high fragility; arbitrary script tool | No explicit provenance/claim discipline | Single test file visible | Low | Avoid architecture pattern |
| OpenSCAD MCP | https://github.com/jhacksman/OpenSCAD-MCP-Server | 150 | OpenSCAD + image-to-3D pipeline | Includes preview/approval stages | Extensive generation/export/remote processing | Broad autonomous pipeline + external service dependencies | Trace-like outputs but no engineering claim separation | Many test scripts | Low-medium | Monitor selective approval UX ideas only |

*Stars observed on 2026-05-13 from public repo pages/API.

## Project-by-project notes (condensed)

### Blender MCP (ahujasid)

- What stands out:
  - Strong screenshot/viewport loop and polished UX.
  - Simple bridge architecture (addon + MCP server).
- What to avoid:
  - `execute_blender_code` arbitrary Python path as normal tooling.
  - Any implication that visual success equals engineering validity.

### FreeCAD MCP (neka-nat)

- What stands out:
  - Direct FreeCAD control, growing FEM support, remote connection controls.
  - Practical host capability checks and operational ergonomics.
- What to avoid:
  - `execute_code` style tools.
  - Coupling tool success with engineering claim semantics.

### FreeCAD MCP (contextform)

- What stands out:
  - Easy install and onboarding.
  - Broad Part/PartDesign operation coverage.
- What to avoid:
  - General script execution routes without strict side-effect metadata.

### KiCad MCP (Seeed)

- What stands out:
  - Strong read-only inspection and explicit validation tools.
  - Honest editing limitations and fallback behavior when APIs unavailable.
- What to avoid:
  - Auto-interpreting ERC/DRC pass as claim pass.

### KiCad MCP (mixelpixx)

- What stands out:
  - Rich docs, tool inventory, practical integrations.
  - Visual/session logs and strong community momentum.
- What to avoid:
  - Overly broad orchestration under one server without explicit side-effect taxonomy.

### CadQuery MCP (rishigundakaram, bertvanbrakel)

- What stands out:
  - Script verification and lightweight preview artifacts (SVG/STEP/STL).
  - Useful part-library scan/search patterns.
- What to avoid:
  - Arbitrary script execution as default path.

### ParaView/VTK/PyVista MCP

- What stands out:
  - Visual artifact loops and post-processing ergonomics.
  - In VTK, narrow tools with clear tests and transport coverage.
- What to avoid:
  - Reframing visualization quality as engineering validation.

### OpenFOAM MCP

- What stands out:
  - Rich domain-specific analysis features and explicit status matrix.
  - Tool breakdown by capability domain.
- What to avoid:
  - Autonomous educational assistant behavior inside core execution adapter.
  - Blurred boundary between guidance and validated engineering claims.

### EnergyPlus MCP

- What stands out:
  - Excellent tool categorization and layered architecture docs.
  - Strong transport/auth configuration patterns (token policy, fail-closed behavior).
- What to avoid:
  - Treating simulation completion as claim advancement.

### SolidWorks/Onshape/Abaqus/OpenSCAD examples

- What stands out:
  - Adapter thinking for proprietary/CAD cloud systems.
  - In OpenSCAD projects, image approval UX and artifact pipelines.
- What to avoid:
  - GUI automation fragility and arbitrary script execution in live GUIs.
  - Fully autonomous text-to-design pipelines for engineering truth paths.

## Cross-project patterns worth learning

- Read-only inspection depth is a major quality differentiator.
- Tool taxonomy clarity (especially by domain and side effects) improves reliability.
- Visual feedback artifacts improve human verification and debugging.
- Runtime capability and dependency checks are essential for practical deployments.
- Explicitly documented limitations build user trust.

## Cross-project risks to avoid

- Arbitrary Python or shell execution tools.
- Autonomous workflow planning and hidden orchestration decisions.
- Implicit claim advancement after simulation or visualization.
- Weak distinction between read-only and mutating operations.
- Poor support for unsupported/missing/not_found/needs_review states.

## Relevance summary for `aieng-freecad-mcp`

Most useful external inspiration is not "do everything these servers do". It is:

- Improve safe read-only inspection breadth.
- Improve machine-readable side-effect metadata.
- Improve optional visual evidence artifacts.
- Improve runtime capability reporting and graceful degradation.
- Keep strict evidence/trace/claim separation as the core differentiator.
