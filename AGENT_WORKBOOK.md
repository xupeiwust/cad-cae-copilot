# AGENT_WORKBOOK

## AIENG project memory

### Product direction
- AIENG mainline is an agent-facing CAD/CAE understanding and execution-assistance layer: engineers should be able to use natural-language prompts to generate CAD, set up CAE, run/review simulations, iterate designs, and preserve evidence in `.aieng` packages.
- Current emphasis: CAD/CAE Copilot loop over safety/review/audit product framing. Keep minimal technical guardrails for external execution, file mutation, honesty, and stale evidence, but avoid making approval paperwork the product center.
- External CAD/CAE tools remain backend adapters. AIENG's core value is project context, engineering intent, evidence lifecycle, action selection, and chat-first orchestration.

### Current architecture snapshot
- Workspace root contains multiple related repos; `aieng-ui` is the active web workbench/backend orchestration surface.
- `aieng-ui/backend/app` now contains the vertical CAD?CAE?postprocess loop:
  - chat/context/action: `contextual_chat.py`, `agent_context.py`, `action_selector.py`, `runtime.py`, `runtime_tools.py`;
  - CAD generation/refinement: `cad_generation.py` using Claude + build123d, storing STEP/STL/GLB/topology/source code;
  - geometry understanding: `geometry_providers.py` with static package and optional FreeCAD providers;
  - FEA setup: `ai_preprocessing.py` using LLM-produced material/BC/load/mesh setup plus validation;
  - simulation: `simulation_runner.py` for Gmsh mesh + CalculiX solve, sync and SSE stream paths;
  - postprocess/advice: `post_processing.py`, `stress_heatmap.py`, `design_target_chat.py`.
- `aieng/src/aieng/modeling` contains CAD backend protocols/prompts and standard part context for text-to-CAD.
- Frontend main path is chat-first: `frontend/src/App.tsx` routes detected intents to CAD generation/refinement, preprocessing, simulation, material/mesh iteration, target setting, and project-grounded contextual chat. `ChatPanel.tsx` renders cards; `ModelViewer.tsx` displays model/heatmap.

### Current shipped capability state (compacted from v0.35-v0.52 records)
- Closed-loop Copilot foundation: project health, design targets, computed metrics import, target comparison, FreeCAD inspection/edit paths, structural preflight, solver-run path, reports, loop history/comparison/export, review support packet, workflow sections, contextual approval panels.
- Template authoring/handoff: controlled template drafts for `cantilever_beam` and `plate_with_hole`; target adoption; approval-gated template CAD fixture metadata.
- Agent context and action selection: read-only `/api/projects/{id}/agent-context`; runtime tool `aieng.agent_context`; planner wiring; candidate-only available actions; intent-constrained selection so status/inspection requests do not authorize export/setup/result import/solver/CAD mutation.
- AI preprocessing: LLM-driven FEA setup from geometry context; material catalog; validation for material names, face IDs, load sanity, NSET collisions; atomic writes of `simulation/setup.yaml` and `simulation/cae_mapping.json`.
- Geometry provider system: Protocol-based `GeometryProvider`, CAD-neutral `GeometryContext`, static package heuristics, optional FreeCAD enrichment, LLM-readable geometry text.
- Text-to-CAD: build123d backend via Claude; generates code, executes in subprocess, extracts topology, writes `geometry/generated.step`, `geometry/preview.stl`, optional `geometry/preview.glb`, `geometry/topology_map.json`, `graph/feature_graph.json`, `geometry/source.py`; refinement path reads source and overwrites artifacts; standard part hints for fasteners/extrusions.
- Chat-first UI: unified chat input, CAD result cards, preprocessing cards, simulation approval/progress/result cards, target cards, FoS advisory cards, stress heatmap toggle.
- Simulation: Gmsh + CalculiX run path with explicit confirmation, tool availability degradation, NSET face?node mapping including normal-vector plane mapping, solver failure diagnosis, SSE progress endpoint, atomic result writes to `simulation/solver_log.txt`, `simulation/result.frd`, `simulation/results_summary.json`, `simulation/mesh.inp`.
- Postprocessing: design-target interpretation, stress/displacement suggestions, FoS computation, FoS engineering advisory, stress heatmap GLB with MPa colorbar headers.
- Context-aware chat: project-grounded Claude chat reads geometry, FEA setup, simulation summary/verdict, and design targets.

### Latest validation remembered
- Earlier full-suite baselines progressed from 613 to 867 backend tests passing as features shipped.
- v0.51/v0.52 remembered state: backend suite `867 passed`; frontend build clean.
- Known v0.43.1 note: one unrelated pre-existing site-packages import conflict appeared in a targeted run.

### Durable risks / follow-up areas
- Documentation and package contract drift: older docs still describe v0.37 or run-scoped `simulation/runs/.../outputs/result.frd`, while current chat simulation path writes flat `simulation/result.frd`, `simulation/results_summary.json`, and `simulation/mesh.inp`; generated CAD artifacts such as `geometry/generated.step` and `geometry/source.py` should be reflected in the canonical contract.
- Chat intent routing is keyword-based in `App.tsx`; ordering and localization issues can misroute engineering prompts. Move toward backend-mediated typed intent/action plans with explainable confidence.
- `executeIterationFromPrompt` extracts material hints but currently delegates to preprocessing without passing the extracted `material_hint`; check/fix before relying on material-change chat iteration.
- `cad_generation.py` executes LLM-generated build123d code in a subprocess with timeout; add stronger sandbox/resource restrictions and output validation before broader use.
- `simulation_runner.py` duplicates sync and SSE run logic; consolidate to one core pipeline yielding events/results to reduce drift.
- Package schema/versioning and artifact provenance should be tightened as CAD generation, preprocessing, simulation, and heatmap writes expand.
- Next high-value product steps: robust intent/action planner, benchmarked engineering task suite, report export, multi-iteration comparison, structured parameter diff edits, stronger geometry/FEA validity checks, and adapter capability manifests.
### v0.53 local start ? chat action routing hardening (2026-05-25)
- Added backend `engineering_action_plan.py` plus `POST /api/projects/{project_id}/engineering-action-plan` as a read-only typed action candidate layer for chat prompts. It centralizes priority rules and emits intent, confidence, extracted inputs, project state, action metadata, write targets, external tools, and approval tier.
- Frontend `sendUnified()` now tries backend action planning first and falls back to local `detectCadIntent()` if unavailable.
- Fixed high-priority intent ordering so set-target/change-material/refine-mesh/generate are not swallowed by broad CAD refinement triggers.
- Fixed material-change iteration path to pass extracted `material_hint` into AI preprocessing.
- Added `tests/test_engineering_action_plan.py`; targeted validation passed: `6 passed, 2 warnings`. Frontend `npm run build` passed with existing large-chunk warning.
### v0.54 local start ? symbolic B-Rep graph pointer layer (2026-05-25)
- Added backend `brep_graph.py`: deterministic symbolic B-Rep graph derived from `geometry/topology_map.json`, with pointer syntax `@face:<id>`, `@edge:<id>`, `@group:<id>`.
- Emits `graph/brep_graph.json`, `graph/entity_index.json`, and `ai/brep_digest.md`; includes face roles, entity signatures, feature-backed groups, cylindrical-pattern groups, and explicit/inferred face adjacency. Inferred bbox adjacency is marked low-confidence/virtual.
- Added endpoints: `POST /api/projects/{id}/brep-graph/build` and `GET /api/projects/{id}/brep-graph`. No CAD kernel, mesh, solver, or LLM execution.
- Integrated compact B-Rep digest into `contextual_chat.build_context_block()` and `agent_context.brep_graph` so agents can cite precise face/group pointers.
- Added `tests/test_brep_graph.py`; targeted validation passed: `24 passed, 2 warnings` across B-Rep graph, engineering action plan, contextual chat, and agent context. Frontend build passed with existing large-chunk warning.
### v0.55 local start ? B-Rep pointers in AI preprocessing (2026-05-25)
- `ai_preprocessing.py` now builds a transient B-Rep graph context from `geometry/topology_map.json` and injects the compact B-Rep pointer digest into the Claude preprocessing prompt.
- FEA output schema now allows `target_pointers` such as `@face:face_001` and `@group:feat_holes` for BC/load selection.
- Validation normalizes B-Rep pointers through `entity_index`: face pointers and group pointers resolve into `target_face_ids`; invalid or unsupported pointers produce validation warnings.
- `setup.yaml` now preserves `target_pointers` and `target_face_ids` for review; `cae_mapping.json` preserves target pointers, selection source, and supports pointer-only selection keys so simulation NSET mapping still works without a feature ID.
- AI preprocessing write-back now also writes `graph/brep_graph.json`, `graph/entity_index.json`, and `ai/brep_digest.md` by default when B-Rep graph context is available.
- Targeted validation passed: `45 passed, 2 warnings` for AI preprocessing, B-Rep graph, simulation runner. Frontend build passed with existing large-chunk warning.
### v0.56 local fix ? honest STEP import / preview readiness without CAD provider (2026-05-26)
- `services/platform_logic.import_aieng_file()` no longer routes STEP import through the unavailable CAD provider stub. It now uses `aieng` core bridge helpers to create `.aieng` packages from STEP, then best-effort enriches them with `geometry/topology_map.json`, `graph/aag.json`, `graph/feature_graph.json`, `validation/completeness_report.json`, `validation/status.yaml`, `README_FOR_AI.md`, and `ai/summary.md`.
- `services/platform_logic.validate_aieng_file()` now validates through `aieng_bridge.validate_package()` instead of the provider stub, so package validation works even when no external CAD adapter is configured.
- `services/platform_logic.convert_asset()` now reports preview unavailability honestly. When no CAD provider can export STEP→STL, the API returns `status="unavailable"` and the project metadata keeps `web_asset=None` / `web_asset_format=None` instead of pointing at nonexistent viewer assets.
- `services/platform_logic.package_summary()` now falls back to zip inspection when the provider summary path returns `status="unavailable"`, so imported packages still show members/topology/features in the UI without a CAD adapter.
- `config.Settings.from_env()` now falls back to `aieng/examples/bracket.step` when the historical `SFA-5.41/nist_ctc_05.stp` sample is absent, so `/api/projects/sample` is usable again in this workspace.
- `main.runtime_config_snapshot()` and the unavailable provider probe now expose frontend-compatible runtime fields (`provider`, `freecad_home`, `freecad_mcp_root`, `probe.ready`, `probe.issues`, resolved topology backend, etc.), making UI status reporting more diagnosable.
- Validation: targeted backend regression checks passed (`4 passed`) and live API repro now shows `import-aieng -> status=ok`, real package created, summary member_count populated, and preview conversion honestly marked unavailable without a provider.


## v0.57 local fix – minimal FreeCAD preview provider wiring (2026-05-26)
- Added a real `freecad` provider path for STEP preview export readiness under `aieng-ui/backend/app/providers/freecad_preview.py`.
- Runtime probe now reports `provider=freecad`, auto-detects workspace `aieng-freecad-mcp` presence, and honestly surfaces missing `FreeCADCmd` with actionable config guidance.
- `convert_asset()` now distinguishes `unavailable` vs `error` preview outcomes instead of collapsing every missing-STL case into fake success.
- `frontend/src/App.tsx` workbench import flow now treats any non-`ok` preview status as an error-stage outcome and uses readable upload/import/preview notices.
- Validated locally:
  - targeted backend pytest: 3 passed
  - frontend build: passed
  - live API: STEP import still succeeds; preview now returns `freecad_cmd_missing` with `status=unavailable` and no fake viewer asset.
- Remaining blocker for real model preview: install/configure a working FreeCAD runtime exposing `FreeCADCmd`.
