# aieng Workbench — Agent Guide

Canonical onboarding doc for any AI agent (Claude Code, GitHub Copilot, OpenAI
Codex, Cursor, Cline, …) working in this workspace. This is the single source of
truth — `CLAUDE.md`, `.github/copilot-instructions.md`, and the MCP tool
`aieng.agent_readme` all point here.

---

## STOP — read this first

**Do NOT browse `aieng/src/` to understand what this system can do.**
That is a legacy library with a `FakeBackend` stub that produces no real geometry.

**The workbench is driven primarily through the `aieng-workbench` MCP server tools.**
If you see `aieng.*` / `cad.*` / `cae.*` tools in your tool list, use them — they
provide live UI events, topology feedback, and incremental modeling.

**If you do NOT have these MCP tools** (e.g. Kimi Code CLI without MCP
configuration), you are in **fallback mode**. You can still produce geometry by:
1. Writing build123d scripts and running them through the provided runner script.
2. Importing the resulting STEP file into the workbench with the provided importer
   script so it appears in the UI.
See the **Fallback mode** section below for the exact commands.

If the `aieng-workbench` MCP server is not in your tool list, it is configured in
this repo (`.mcp.json` for Claude Code, `.vscode/mcp.json` for VS Code/Copilot,
see MCP_SETUP for Codex, and see **Kimi Code CLI** notes in the Fallback section).

---

## First three calls every session

```
1. aieng.agent_readme                   → this guide, served at runtime
2. aieng.list_projects                  → discover available project IDs
3. aieng.agent_context { project_id }   → geometry state, pointers, next steps
```

Call these **before** reading files or running code. `aieng.agent_context` gives
you the current geometry state, stale-artifact warnings, and the pointer IDs you
need to construct valid tool calls.

---

## Workspace layout

| Path | Status | Purpose |
|------|--------|---------|
| `aieng-ui/backend/` | **Active** | FastAPI backend + MCP server + all tools |
| `aieng-ui/frontend/` | **Active** | React workbench UI |
| `aieng/` | Core library | Semantic package format library — `.aieng` package engine, Shape IR, schemas, validation, CLI, artifact/evidence model |
| `aieng-agent-skills/` | Active | Agent skill definitions |
| `legacy/aieng-freecad-mcp/` | Legacy | Old FreeCAD adapter — not the default runtime |
| `archive/CAD-Agent-main/` | Archived | Historical/experimental auxiliary CAD-agent material |

### Development path rules

- **Default do not develop in `archive/` or `legacy/`**. These areas are
  preserved for reference and compatibility only.
- **CAD/CAE execution work** starts from `aieng-ui/backend`. That is where
  build123d/OCP runs, MCP tools are registered, and the active runtime lives.
- **Shape IR, schema, validation, `.aieng` package/evidence model** work starts
  from `aieng/`. This is the core semantic library; it is **not** legacy.
- **If you genuinely need to migrate logic** from `archive/` or `legacy/` into
  an active path, explicitly state: (1) what you are migrating, (2) why it is
  needed in an active path, and (3) the target active path.

---

## Frontend maintainability rules

When editing `aieng-ui/frontend/`, think about maintainability before adding or
changing code:

- Keep `src/App.tsx` as a lightweight composition layer. Do not put workflow
  orchestration, data fetching, domain actions, or large JSX trees directly in
  `App.tsx`.
- Prefer focused hooks and modules by responsibility: runtime settings, agent
  runs, geometry pointers, CAD/CAE actions, live activity streams, and pure
  formatting/helpers should live in separate files.
- Do not replace one giant file with another. If a module grows beyond a single
  clear responsibility, split it before adding more behavior.
- Preserve existing UI behavior and styling during refactors. Move code first,
  verify, then simplify.
- Remove dead components, helpers, constants, and types once they are no longer
  reachable from the active UI or API surface. Do not keep obsolete panels around
  "just in case" unless there is a concrete owner and integration path.
- For new UI work, prefer reusable components and explicit prop contracts over
  hidden cross-file coupling. Use TypeScript build results and reference searches
  to prove that cleanup is safe.

### Agent run display state

- **Terminal runs must look stopped.** `completed` / `failed` / `cancelled` are
  terminal (`isTerminalAutopilotStatus` in
  [`chatTranscript.ts`](aieng-ui/frontend/src/app/chatTranscript.ts)). A terminal
  run must never render an active spinner, a pending/glowing plan step, or a
  "waiting approval" badge after reload.
- **Cancelled is distinct from blocked.** A cancelled run projects to the
  `cancelled` transcript tone (stopped/neutral, no spinner), *not* `blocked`
  (which stays amber "waiting approval" for genuinely paused runs). The run's own
  status is authoritative over a stale `plan.status`: `planToTranscriptItem` /
  `normalizeTerminalPlanSteps` rewrite any not-yet-finished step of a cancelled
  run to `cancelled` so nothing reads as in-flight. Completed keeps its
  pending→`skipped` normalization; failed is left untouched.
- Active-run restore / processing indicators key off the active set
  (`running` / `awaiting_approval` / `chatting` / `blocked`) — never the terminal
  set — so a reloaded cancelled run does not re-arm the composer Stop button or
  the elapsed-time spinner. Raw event/run detail stays available via the
  per-row Details disclosure.

### Composer slash commands and @-mentions

The chat composer recognizes leading slash commands (`/build`, `/modify`,
`/critique`, `/explain`, `/simulate`) and surfaces a suggestion menu.
`parseComposerIntent` / `toComposerIntentMetadata` (in
[`composerIntent.ts`](aieng-ui/frontend/src/components/chat/composerIntent.ts))
attach a `composer_intent` blob to the persisted chat message `extra` and to the
autopilot run create request (echoed back on `AutopilotRunState.composer_intent`).
The raw `/command` text is always preserved in the stored user message.

**Backend routing status:**
- **`/build` (routed, mutation-required).** When
  `AutopilotRunState.composer_intent.command == "build"`, the engine injects a
  create-geometry instruction into the run context (biasing the agent toward CAD
  mutation tools such as `cad.execute_build123d`) and **forces the geometry-
  mutation guard ON** (`intent_type == "create_geometry"`) — a bare `final` is
  rejected until a CAD mutation tool has succeeded. This holds **even when the
  free text contains no create trigger word**. Asking the user for clarification
  (`ask_user`) or reporting a clear blocker is still allowed; a false success is
  not.
- **`/modify` (routed, mutation-required).** Same as `/build` but with a modify-
  geometry instruction (`intent_type == "modify_geometry"`). A read-only result
  such as `cad.critique` does **not** satisfy the requirement. If no CAD model
  exists yet, `ask_user` or a clear blocking `final` is acceptable — no false
  success.
- **`/critique` (routed, read-only).** When
  `AutopilotRunState.composer_intent.command == "critique"`, the engine injects a
  read-only critique/inspection instruction into the run context (biasing the
  agent toward `cad.critique` and read-only inspection tools such as
  `aieng.inspect_package` / `aieng.validate` / `cad.get_source`) and **suppresses
  the geometry-mutation guard** so a `final` is allowed after a read-only result
  (or a clear "no CAD available" answer) even if the free text contains words
  like "add". It does **not** force `cad.critique`, change CAD execution, or
  bypass approval.
- **`/explain` (routed, read-only).** When
  `AutopilotRunState.composer_intent.command == "explain"`, the engine injects a
  read-only explanation instruction into the run context (`intent_type ==
  "explain_project"`; biasing the agent toward read-only context/source/topology
  tools such as `aieng.agent_context` / `aieng.inspect_package` / `cad.get_source`
  / `aieng.agent_readme`) and **suppresses the geometry-mutation guard** so a
  `final` is allowed after a read-only inspection — or a clear "nothing available
  to explain" answer — even if the free text contains words like "add"/"change".
  If no CAD/project/artifact exists, `ask_user` or a clear blocking `final` is
  acceptable. It does **not** force any specific tool, change CAD execution, or
  bypass approval.
- **`/simulate` (parsed, not routed).** Stored as metadata only — no tool/prompt
  routing yet. Natural-language intent and the geometry-mutation guard behave
  exactly as before for it.

Command-specific routing **never bypasses approval** — `cad.execute_build123d`
and the other mutation tools still pause for approval as usual. Helpers live in
[`engine.py`](aieng-ui/backend/app/agent_autopilot/engine.py):
`get_composer_command` / `is_critique_command` / `is_read_only_command` /
`is_mutation_required_command` / `command_intent_label` / `command_mutation_intent`.

**`@`-mentions (routed as prompt/context, v1).** The composer also parses
lightweight `@kind:value` mentions (`extractComposerMentions` in
[`composerIntent.ts`](aieng-ui/frontend/src/components/chat/composerIntent.ts))
into `{ kind, raw, value }` and persists them on `composer_intent.mentions`.
- **`@part:<label>` and `@artifact:<id>` are routed.** The engine surfaces them
  to the agent as a mention-context section ("The user referenced these CAD
  parts: …" / "… these artifacts: …"), with command-aware targeting guidance:
  `/explain @part:x` → explain that part (read-only), `/critique @part:x` →
  critique that part if available (read-only), `/modify @part:x` → target the
  CAD edit at that part **(approval and the mutation guard are unchanged)**.
- This is **prompt/context guidance only** — *not* strict object binding. If a
  referenced part/artifact is not found in the current model/topology, the agent
  is told to ask the user or clearly report "target not found" rather than invent
  it. Mentions are never required for any command.
- Helpers: `mentioned_parts` / `mentioned_artifacts` / `mention_context_label`
  (in `engine.py`), robust to missing/malformed metadata.
- **Future work:** `@workspace` / `@project` / `@face` mention routing, strict
  topology/artifact binding, and `/simulate` command routing are not implemented
  yet (the parser recognizes those kinds, but the backend does not route them).

---

## What the workbench can actually do

### Real 3D CAD modeling (no API key needed)

`cad.execute_build123d` runs caller-supplied Python code against **build123d**
(the real OpenCASCADE geometry kernel) and produces actual STEP/STL/GLB files.
This is NOT a stub. Supported operations include:

- Primitives: `Box`, `Cylinder`, `Cone`, `Sphere`, `Torus`
- Operations: `extrude`, `revolve`, `loft`, `sweep`
- Modifications: `fillet`, `chamfer`, `shell`, `mirror`
- Boolean: add / `subtract` (`Mode.SUBTRACT`) / intersect
- Patterns: `PolarLocations`, `GridLocations`, `Locations`
- Holes, slots, countersinks

Enough to model most mechanical parts: housings, brackets, enclosures, manifolds,
and simplified consumer-product bodies.

**Code contract:**
- Bind the final model to a variable named **`result`**.
- Do **not** include export calls — the runner adds `export_step` / `export_stl` /
  `export_gltf` (build123d 0.10.0; exports are free functions).
  - If you absolutely must export manually (fallback mode), use `export_gltf(result, path, binary=True)`
    to produce a real binary GLB. Without `binary=True`, build123d writes a JSON
text file that the frontend cannot render.
- A `+` that yields a `ShapeList` is auto-wrapped in a `Compound`, so unions export fine.

**Name your parts.** Set `.label` on shapes and combine them with a `Compound` so
each part gets a semantic ID you can reference later (instead of anonymous
`body_001`). Labels appear as named parts in `topology_map.json` and as
`named_part` features in `feature_graph.json`.

**Color your parts.** Set `.color = Color(r, g, b)` (RGB in 0..1) on each part.
Colors flow through to **both** the agent thumbnail (so you can visually tell
parts apart) **and** the GLB the UI viewer displays. Parts without a `.color`
get a cycling palette in the thumbnail; in the UI they appear default-grey.
Use color to make part boundaries readable and to encode design intent
(e.g. red structural, blue moving, silver mechanical).
```python
from build123d import *
body = Box(40, 40, 10); body.label = "fuselage"
body.color = Color(0.78, 0.15, 0.15)   # red
fl = Cylinder(3, 30); fl.label = "motor_pod_FL"
fl.color = Color(0.20, 0.30, 0.65)     # blue
result = Compound(children=[body, fl])
```

**Incremental modeling (`mode: "append"`).** Instead of resubmitting the whole
script each step, append onto the previous result:
- `mode: "replace"` (default) — the script is the whole model.
- `mode: "append"` — the previously-stored script runs first; its model is exposed
  as **`previous_result`**. Your code adds to it and must still reassign **`result`**.
  Requires an existing model (run once with `replace` first). Labels from earlier
  steps are preserved.
```python
# step 2, mode=append — keeps the fuselage + motor_pod_FL from step 1
from build123d import *
arm = Cylinder(3, 30); arm.label = "motor_pod_FR"
result = Compound(children=[previous_result, arm])
```

**Visual feedback (multi-view contact sheet).** `cad.execute_build123d` returns a
single PNG with **four labelled views in a 2×2 grid: front, side, top, iso**.
If a reference image is attached to the project (see "Reference image
calibration" below) the layout becomes 2×3 with the reference filling the
rightmost column for side-by-side comparison. The image arrives as an MCP
image content block (disable with `{"thumbnail": false}`).
**Look at all four views** — each catches problems the others hide:
- **front** — wrong proportions (e.g. arms reaching to feet), left/right symmetry
- **side** — overhangs, depth, parts sticking out forward/back
- **top** — layout in the XY plane, parts hidden behind others in front view
- **iso** — overall 3D form

Don't judge from face counts or bounding boxes — actually look at the views.

**Iterate using fail-first review.** Before adding more parts, list 3–5 reasons
the current build does **not** look like the target object (specific to view +
specific part), then list what's right. Decide the next iteration from the
failures, not from a preset plan. This works much better than building straight
through to the finish.

**Reference image calibration.** When the user names a real product, character,
or vehicle, attach a reference image once with `cad.set_reference_image`
(pass `image_url` for HTTP fetch or `image_path` for a local file). The
reference is stored in the project's `.aieng` package and every subsequent
`cad.execute_build123d` thumbnail tiles it next to the 4 views, so you compare
proportions against the real reference instead of relying on memory.
Set the reference **before** starting iteration if you have one — that way
even the first build is calibrated. Without a reference you're guessing
proportions; with one, fail-first review can cite specific mismatches like
"forearm tapers wrong: reference shows widening toward the wrist, my build
narrows."

**Response summary fields** (text-side feedback, useful when your client drops the image):
`named_parts` (all named parts now in the model), `parts_added` (what this step added),
`mode` (`replace`/`append`), `used_base` (whether an append consumed a prior model).

**Quantitative geometry report (`geometry_report`).** Every `cad.execute_build123d`
and `cad.edit_parameter` response carries a deterministic `geometry_report` —
judge proportions from these *numbers*, not only the blurry thumbnail (LLMs read
ratios far more reliably than low-res 3D renders):
- `overall_proportions` — normalized H:W:D of the whole model (largest dim = 1.0).
- `parts[].ratio_to_largest` — each named part's size relative to the biggest part.
- `symmetry[]` — for left/right name pairs (`arm_L`/`arm_R`, `motor_pod_FL`/`FR`):
  `ok:false` = the pair is NOT symmetric (fix the coordinates); `align_residual_mm`
  is how far off the mirror is; `status:missing_partner` = you named one side only.
- `gaps[]` — `status:floating` flags a detached part (usually a coordinate typo);
  `touching` = parts connect as intended; `floating_parts` lists all detached ones.
Cite specific numbers when iterating ("arm ratio_to_largest=0.5, too short → 0.7")
— this converts proportion judgment from eyeballing into a convergence metric.

**Parametric editing (`cad.edit_parameter`) — change one dimension fast, no LLM.**
When you want to resize an existing feature, do NOT regenerate the whole model.
`cad.edit_parameter` does a deterministic text replacement of a named constant in
`geometry/source.py` and re-executes build123d — sub-second to a few seconds,
fully reproducible. For this to work the source must declare dimensions as
**UPPER_SNAKE_CASE constants** (the system prompt enforces this on generated
code; do the same in hand-written code):
```python
MOTOR_POD_RADIUS = 3        # editable → feature_graph exposes radius_mm
fl = Cylinder(MOTOR_POD_RADIUS, 30); fl.label = "motor_pod_FL"
```
The feature graph then carries editable `parameters` with a `cad_parameter_name`
pointing back at the constant. Call it as:
```
cad.edit_parameter { project_id, featureId, parameterName, newValue }   [APPROVAL]
```
- `featureId` / `parameterName` come from the feature's `parameters` block in
  `feature_graph.json` (or `aieng.agent_context`).
- Validated against the parameter's declared `min_value`/`max_value` first.
- If the new value breaks the build, the package is left untouched and the error
  is returned — the prior geometry is preserved.
- Constants whose prefix is `GLOBAL_`/`DEFAULT_`/`WALL_`/`FILLET_`/`CHAMFER_` are
  also surfaced under a synthetic `Global Parameters` feature for shared dims.
  Any declared constant that matches no part name lands in a `Model Parameters`
  feature (or, if there's exactly one named part, on that part) — so every
  declared constant is editable.
Use `cad.execute_build123d` (mode=append/replace) only for changes that add or
remove geometry; use `cad.edit_parameter` for pure dimensional tweaks.

**Regression diff on every edit (`regression_diff`).** The `cad.edit_parameter`
response includes a `regression_diff` that compares the before/after topology by
named part — your safety net against an edit silently warping geometry it
shouldn't have. Read its `verdict` before trusting the result:
- `clean` — only the intended part(s) changed; `changed[]` lists each with
  `size_delta_mm` / `center_shift_mm`.
- `collateral_change` — **WARNING**: parts you did NOT target also moved
  (`collateral_parts` names them). Usually means the constant is shared across
  parts; reconsider the edit or split the constant.
- `identical` — nothing changed (wrong constant, or a no-op value).
- `topology_changed` — the part set changed (a part appeared/disappeared);
  unexpected for a pure dimensional edit.
(For edits to a `Global Parameters` constant, collateral is not judged — shared
dims are *meant* to move many parts.)

**Part-level edits — `cad.replace_part` / `cad.remove_part` (the visible loop).**
`append` only ADDS geometry; when you need to fix or drop ONE part of a
character/product without resubmitting the whole script, use these:
- `cad.remove_part { project_id, label }` — drops the part with that `.label`.
- `cad.replace_part { project_id, label, code }` — swaps it for new build123d
  `code` (which must reassign `result` to the new part and set `result.label`,
  normally back to the same name). The high-level helpers are available in `code`.
Both append a transform step to `source.py` (so the stored script stays
self-consistent) and re-execute — no LLM — and return a `regression_diff` so you
can confirm only the targeted part changed. **Build incrementally with these +
`append` so each step shows in the viewer** — that is how the user watches the
model assemble, instead of one monolithic build appearing at the end.

**Organic vs mechanical (`model_kind`).** `cad.execute_build123d` accepts
`model_kind`: `"mechanical"` runs the bolt-pattern + base-plate feature
heuristics, `"organic"` skips them, `"auto"` (default) infers from part labels
and helper usage. Pass `"organic"` for characters/vehicles/products — otherwise
the heuristics mislabel limb cylinders as `mounting_hole_pattern` and the bottom
face as a `base_plate`, cluttering the feature graph. The chosen kind is echoed
back in `feature_graph.model_kind`.

**Advanced-feature awareness in the feature graph.** Beyond named parts, the
feature graph now tags the modelling operations it detects in the source:
`loft`, `revolve`, `sweep`, `fillet` (with average radius), and `mirror`. This
lets you (and downstream tools) see whether a body was built with industrial-
design curves or plain primitive stacking.

Example — a simplified coffee-machine body:
```python
from build123d import *
with BuildPart() as bp:
    Cylinder(radius=55, height=200)
    fillet(bp.edges().filter_by(Axis.Z, reverse=True), radius=8)
    with Locations((0, 0, 80)):
        Cylinder(radius=40, height=100, mode=Mode.SUBTRACT)
    with Locations((63, 0, 30)):
        Cylinder(radius=8, height=25, rotation=(0, 90, 0))
result = bp.part
```

### Industrial Design Mode — escape primitive stacking

For **complex visible exterior forms** (named characters, vehicles, consumer
products, electronics, anything where shape recognizability matters), `Box +
Cylinder` stacking caps the result at "high-quality pixel art." To produce
something that reads as designed rather than assembled, switch into
**industrial design mode**: build from a skeleton, generate solids by lofting
or sweeping between profiles, apply large fillets, and add details only after
the silhouette is correct.

**Activate when:** the user names a real product, character, or vehicle, or
says "make it look like a …" / "designed" / "smooth" / "rounded." Skip when
the user asks for mechanical brackets, fixtures, prototypes, or massing
studies — primitive stacking is fine there.

**Workflow:**

1. Plan landmarks (anchor Z heights, half-widths) as **named constants**.
   This lets later iterations adjust proportions in one place.
2. Build silhouette + skeleton first; verify the 4-view contact sheet reads
   correctly before adding detail.
3. Replace tapered or curved bodies with `loft` / `sweep` / `revolve` —
   **not** stacked boxes that imitate curves.
4. Apply `fillet` aggressively (radius 5–20mm) on visible edges. Apply LAST,
   after all booleans.
5. Mirror symmetric parts with `mirror(part, about=Plane.YZ)` — half the
   code, guaranteed symmetry.

**Hard rule:** if your iteration script is mostly `Box(...) + .moved(...)`
calls for a visible character/vehicle/product, stop and replace the major
exterior masses with one of the curve patterns below.

### High-level helpers — prefer these over hand-rolled boilerplate

`cad.execute_build123d` pre-injects these functions into your namespace (do NOT
import or redefine them). They wrap the error-prone BuildSketch/Plane/loft/sweep
boilerplate that LLMs routinely break, so you get smoother forms **and** fewer
failed builds. Each takes `label=` / `color=` and returns a `Part`:

| Helper | Use for | Signature |
|--------|---------|-----------|
| `lofted_stack(sections)` | torsos, cabs, fuselages, tapered bodies | sections = list of `(z, r)` circle / `(z, w, d)` rounded-rect / `(z, w, d, corner_r)` |
| `rounded_box(l, w, h, radius, edges=)` | designed enclosures (vs hard Box) | `edges="all"` or `"vertical"` |
| `capsule(radius, length, axis=)` | arms, legs, limbs, rounded pins | `axis` ∈ `"X"/"Y"/"Z"` |
| `tapered_cylinder(r_bot, r_top, h)` | necks, nozzles, tapered legs | — |
| `swept_tube(path_points, radius)` | pipes, handles, exhausts, cables | `path_points` = list of `(x,y,z)` |
| `revolved_profile(profile_points)` | bottles, vases, wheels, axisymmetric | `profile_points` = list of `(r, z)`, auto-closed to Z axis |
| `organic_blend(solids, radius)` | merge parts into ONE smooth body | fuses + fillets the joins; auto-degrades radius if infeasible |

```python
# A humanoid torso + symmetric arms + blended head — no BuildSketch boilerplate:
torso = lofted_stack([(0,120,80),(200,150,90),(392,60)], label="torso")
arm_L = capsule(8, 120, label="arm_L").moved(Location((-90,0,300)))
arm_R = mirror(arm_L, about=Plane.YZ); arm_R.label = "arm_R"
head  = Sphere(45).moved(Location((0,0,440)))
result = organic_blend([torso, head], 12, label="body")  # smooth neck join
result = Compound(children=[result, arm_L, arm_R])
```

### Curve patterns — copy + adapt (when a helper doesn't fit)

**Tapered body via loft** (truck cabs, helmet crowns, conical housings):
```python
from build123d import *
with BuildPart() as bp:
    with BuildSketch(Plane.XY.offset(0)) as s1:
        RectangleRounded(200, 100, radius=10)
    with BuildSketch(Plane.XY.offset(100)) as s2:
        RectangleRounded(170, 90, radius=14)
    loft()  # smooth taper between the two sketches
result = bp.part
```

**Revolved profile** (bottles, vases, bell housings, axisymmetric parts):
```python
from build123d import *
with BuildPart() as bp:
    with BuildSketch(Plane.XZ) as s:
        with BuildLine() as l:
            Spline((0, 0), (30, 20), (40, 50), (35, 80), (40, 110))
            Line((40, 110), (0, 110))
            Line((0, 110), (0, 0))
        make_face()
    revolve(axis=Axis.Z)
result = bp.part
```

**Swept profile along a 3D path** (exhaust pipes, handles, cable routing):
```python
from build123d import *
with BuildLine() as path:
    Spline((0, 0, 0), (0, 20, 50), (0, 40, 100), (0, 30, 130))
with BuildPart() as bp:
    with BuildSketch(Plane(origin=path.line @ 0, z_dir=path.line % 0)) as prof:
        Circle(8)
    sweep(path=path.line)
result = bp.part
```

**Aggressive fillet for designed feel** — apply LAST, after all booleans:
```python
from build123d import *
with BuildPart() as bp:
    Box(100, 60, 40)
    fillet(bp.edges().filter_by(Axis.Z), radius=12)       # vertical edges
    fillet(bp.edges().group_by(Axis.Z)[-1], radius=4)     # top edges
result = bp.part
```

**Mirror for symmetric parts** — build one half, mirror the other:
```python
from build123d import *
left_arm = Box(40, 60, 100).moved(Location((-110, 0, 200)))
left_arm.label = "left_arm"
right_arm = mirror(left_arm, about=Plane.YZ)
right_arm.label = "right_arm"
result = Compound(children=[left_arm, right_arm])
```

**Named landmarks** — define proportions once, reference them everywhere:
```python
from build123d import *
# Landmarks (mm) — change here, the whole body re-proportions
HIP_Z, SHOULDER_Z = 232, 392
HIP_HALF, SHOULDER_HALF = 55, 150

with BuildPart() as bp:
    with BuildSketch(Plane.XY.offset(HIP_Z + 30)) as base:
        Rectangle(HIP_HALF * 2 + 20, 90)
    with BuildSketch(Plane.XY.offset(SHOULDER_Z)) as top:
        Rectangle(SHOULDER_HALF * 2, 80)
    loft()
result = bp.part
```

### Engineering Mode — well-formed mechanical parts

Counterpart to Industrial Design Mode. Activate when the user names a
**mechanical/engineering part** that downstream tools will need to
understand — `bracket`, `housing`, `enclosure`, `manifold`, `fixture`,
`frame`, `mount`, `flange`, `chassis`. These parts are usually destined
for CNC/3D-printing or FEA, so structure (named features, manufacturable
geometry, protected mounting interfaces) matters as much as silhouette.

Use the **canonical feature vocabulary** from
`aieng/schemas/feature_graph.schema.json` for part labels — the
`_topology_to_feature_graph` heuristic in the workbench recognizes these
names and tags them with semantic intent in the feature graph an agent
can query later:

| `.label` to use | Semantic role |
|---|---|
| `base_plate`, `back_plate`, `mount_plate` | Primary load-bearing flat body |
| `mounting_hole` / `mounting_hole_pattern` | Bolted interfaces — **protected**, don't modify casually |
| `rib`, `rib_<N>` | Stiffeners on plates / shells |
| `boss`, `boss_<name>` | Localized features carrying threaded inserts / screws |
| `flange` | Mating face for bolted assembly |
| `interface_face`, `load_interface` | Where external loads or other assemblies attach |
| `wall`, `wall_<face>` | Enclosure side walls |
| `cover`, `lid` | Removable enclosure top |

**Manufacturing rules to honor** (CNC aluminium defaults — adjust if
the user specifies a different process):
- Minimum wall thickness ≥ **3 mm** (CNC), ≥ **1 mm** (sheet metal), ≥ **1.5 mm** (FDM/SLA print).
- Minimum hole-edge distance ≥ **2 × hole radius**.
- Preferred internal corner radius ≥ **2 mm** — no sharp internal corners.
- Through-holes prefer multiples of standard drill sizes (3, 4, 5, 6, 8, 10, 12, 16, 20 mm).
- Avoid undercuts unless the user explicitly asks for them (machinable from one side).

**Workflow:**
1. Decompose the part into named features (base_plate + holes + ribs +
   bosses + interfaces) **before** writing code. State each feature's
   role explicitly in a brief plan.
2. Build with the canonical labels above — the resulting topology and
   feature_graph then carry engineering semantics that the user (and
   downstream FEA tools) can introspect.
3. Apply the manufacturing rules during sizing — pick wall thicknesses
   and hole spacings that respect them.
4. Once geometry is in, call `cad.critique` (engineering mode) to get a
   deterministic audit against the same rules. The critique walks the
   feature graph and reports violations.
5. For parts destined for FEA, also fix mounting interfaces and load
   surfaces explicitly (the user usually wants these `@face:` pointers
   to drive `cae.apply_setup_patch`).

Example — a CNC bracket with two named ribs and a 4-bolt mounting
pattern (this is the same intent encoded in
`aieng/examples/definition_simple_bracket.yaml`, expressed as code):
```python
from build123d import *

with BuildPart() as bp:
    Box(120, 80, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # 4 mounting holes — 10mm dia, on a 90x50 pattern, ≥ 2× r from edges
    with Locations((45, 25, 0), (-45, 25, 0), (45, -25, 0), (-45, -25, 0)):
        Hole(radius=5, depth=8)
    fillet(bp.edges().filter_by(Axis.Z), radius=4)  # preferred 2mm+ corner
base_plate = bp.part
base_plate.label = "base_plate"
base_plate.color = Color(0.55, 0.62, 0.70)

# Named rib — fits the canonical type so feature_graph tags it as `rib`
rib = Box(60, 5, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))
rib = rib.moved(Location((0, 0, 8)))
rib.label = "rib_main"
rib.color = Color(0.55, 0.62, 0.70)

result = Compound(children=[base_plate, rib])
```

### Structural FEA (CalculiX)

Linear static analysis pipeline — see workflow C below.

---

## Pointer syntax — `@kind:id`

Tool responses and `aieng.agent_context` output use pointer tokens to reference
geometry entities precisely. Use them verbatim in tool arguments and in messages
to the user — the UI renders them as clickable chips.

| Prefix | Refers to |
|--------|-----------|
| `@face:id` | A BREP face (loads / supports / fixtures) |
| `@feature:id` | A CAD feature (use in `cad.edit_parameter` featureId) |
| `@edge:id` | A BREP edge |
| `@group:id` | A named face group (load surface, constraint surface, …) |
| `@artifact:id` | A package artifact (step file, mesh, result file, …) |

Example: if `aieng.agent_context` reports `@face:f_top_001` as a flat surface
suitable for a fixed support, pass `"faceId": "f_top_001"` in your CAE setup call.

**Free-form faces and CAE.** Faces produced by the high-level helpers
(loft/sweep/sphere/spline) now keep the best available surface class
(`bspline`, `bezier`, `sphere`, `cone`, `torus`, `surface_of_revolution`,
`surface_of_extrusion`, or `freeform`) and carry `freeform: true`, `uv_bounds`
when available, and a *proxy* normal sampled at the face midpoint. That is
enough to pick them and bind an approximate CAE boundary condition, but the
node-mapping is a tangent-plane band, not the exact curved surface. For accurate
fixtures/loads prefer **planar faces** (a `rounded_box` keeps its flat faces as
true planes with exact normals). This is also good engineering practice —
fixture and load on flat interfaces.

---

## Tool taxonomy

### Onboarding / discovery (read-only)

| Tool | Purpose |
|------|---------|
| `aieng.agent_readme` | This guide, served at runtime |
| `aieng.list_projects` | All known projects with id, name, status, and (for agent-built geometry) `named_parts` + `part_count` |
| `aieng.find_projects_by_part` | Locate a project by a part label (case-insensitive substring on `named_parts`) |
| `aieng.agent_context` | Compact context: pointers, stale warnings, next steps |
| `aieng.inspect_package` | Full project summary: geometry, CAE setup, results, verdict |

### Read-only inspection (no approval)

| Tool | Purpose |
|------|---------|
| `aieng.read_audit_log` | Recent agent/user actions on this project |
| `aieng.validate` | Schema + rule validation report (no mutation) |
| `aieng.write_completeness_report` | What is missing before simulation |
| `cae.prepare_solver_run` | Solver preflight — checks readiness, runs nothing |
| `cad.get_source` | Accumulated build123d source + `{named_parts, has_base}` — call before an incremental edit |
| `cad.critique` | Deterministic engineering audit (min wall, hole sizes, floating components) — call after building an engineering part |

### Geometry creation (requires approval — mutates package)

| Tool | Purpose |
|------|---------|
| `cad.execute_build123d` | Run caller-supplied build123d code to create/replace geometry (mode=replace\|append). Optional `name` sets a human-recognizable project name (else placeholder projects are auto-named from part labels); optional `model_kind` (auto\|organic\|mechanical) gates the feature-graph heuristics |
| `cad.edit_parameter` | Fast parametric edit: replaces a named constant in `source.py` + re-executes build123d (no LLM). Requires the feature to carry editable parameters — see "Parametric editing" below |
| `cad.replace_part` | Swap ONE named part (by `.label`) for caller-supplied build123d code, keeping everything else. Re-executes, no LLM. See "Part-level edits" below |
| `cad.remove_part` | Drop ONE named part (by `.label`) from the model. Re-executes, no LLM |
| `cad.set_reference_image` | Attach a reference photo/drawing to a project so future thumbnails include it side-by-side for proportion calibration |

Before an incremental edit, call **`cad.get_source`** (read-only) to see the current
accumulated script, which named parts already exist, and whether `has_base` (append
is possible).

### CAE setup (no approval)

| Tool | Purpose |
|------|---------|
| `cae.apply_setup_patch` | Patch CAE setup artifacts (materials, BCs, mesh params) |
| `cae.generate_solver_input` | Generate CalculiX `.inp` deck from setup artifacts |
| `cae.write_mesh_handoff` | Write mesh handoff contract for external Gmsh |
| `cae.import_solver_evidence` | Import an external solver result file as evidence |

### Simulation execution (requires approval — runs external CalculiX)

| Tool | Purpose |
|------|---------|
| `cae.run_solver` | Execute CalculiX on the generated input deck |

### Post-processing (no approval)

| Tool | Purpose |
|------|---------|
| `cae.extract_solver_results` | Parse CalculiX FRD → `computed_metrics.json` |
| `cae.extract_field_regions` | Cluster high-stress / high-displacement regions |
| `cae.map_results` | Map stress/deflection results back to topology entities, object_registry objects, and `source_ir_node` → `analysis/cae_result_map.json` (unmapped regions reported honestly) |
| `opt.derive_problem_from_cae` | Derive a topology-optimization problem (grid + supports + loads + design space) from a project's CAE setup (`simulation/setup.yaml`) + geometry (`topology_map` faces + design-space bbox). Read-only; returns the problem + a `derivation` block. `dimension=2d` (default) projects supports/loads onto the plane of the two largest dims (out-of-plane force dropped); `dimension=3d` keeps the full 3D layout (structured voxel grid, supports→boundary layers, full 3D force) and returns `status=needs_user_input` with diagnostics if BCs can't be safely mapped |
| `opt.run_topology_optimization` | Run topology optimization (built-in self-contained SIMP, compliance-min, pure numpy — no external solver) → `analysis/topology_optimization.json`. `simp_2d` (default) or `simp_3d` (experimental structured-voxel 3D, `dimension=3d`; honest `capability` block: experimental_reference, production_ready:false). Honest coarse limitations recorded. Set `auto_derive` (or omit `problem`) to derive supports/loads/design-space from the project's CAE setup; 3D may return `needs_user_input` instead of guessing |
| `opt.writeback_to_shape_ir` | Author the optimization result back into `geometry/shape_ir.json`, then recompile through runtime routing → the optimized body meshes/views + gets verification + object_registry, linked to its `design_space_node`. 2D: `method=contour` (default) writes a marching-squares boundary as an `extruded_region` (`boundary=spline` default → closed periodic spline / CAD-friendly curve, falls back to `polygon` if it would overshoot the design-space envelope); `method=voxels` writes the blocky `density_voxels`. 3D: `method=surface` (default) writes a smooth **marching-cubes** `surface_mesh` proxy (mesh / lossy / not production CAD; falls back to `voxels` if no isosurface); `method=voxels` writes the blocky 3D `density_voxels`. Placed in the design-space frame. Default representation `brep_build123d` for 2D (analytic faces — pickable, STEP-exportable; auto-falls back to `manifold_mesh` if the B-Rep build fails); 3D defaults to `manifold_mesh` |

**Mesh-to-CAD reconstruction honesty.** Mesh outputs may run a conservative
backend-only reconstruction ladder after region segmentation / analytic fitting:
face candidates → OCC face validation → stitching plan → OCC sewing →
closed-shell solidification → STEP export → roundtrip verification. STEP export is
allowed only when OCC validates a real closed shell and solid; partial shells write
diagnostics (`diagnostics/mesh_brep_sewing.json`,
`diagnostics/mesh_brep_step_export.json`,
`diagnostics/mesh_brep_roundtrip_verification.json`) but no STEP. Successful
reconstruction writes derived CAD only to `geometry/reconstructed.step` and never
overwrites the source/generated STEP. When reconstructed topology replaces
`geometry/topology_map.json`, the original mesh topology is preserved at
`geometry/mesh_topology_map.json`; failed reruns remove stale reconstructed artifacts
and restore mesh topology. Reconstructed STEP (`geometry/reconstructed.step`) is
mesh-derived/lossy, not original design history, not production CAD certification,
and freeform/NURBS fitting remains future work.
| `postprocess.generate_computed_metrics` | Import metrics from CSV/JSON |
| `postprocess.refresh_cae_summary` | Regenerate result summary + evidence markdown |

### Package lifecycle

| Tool | Purpose |
|------|---------|
| `aieng.convert` | Import STEP/FCStd/Shape IR into a `.aieng` package. Shape IR compiles by `representation`: `brep_build123d` (default) → build123d STEP/B-Rep; `nurbs_brep` → OCP NURBS B-Rep surfaces (per-patch `bspline` faces); `implicit_sdf` → fogleman/sdf mesh; `manifold_mesh` → manifold3d CSG mesh. B-Rep reps give analytic per-face topology; mesh reps give region-level faces. Publishes a viewer preview |
| `aieng.apply_shape_ir_patch` | **[APPROVAL]** Apply a surgical patch to a project's Shape IR (set_parameter / move_control_point / add_node / remove_node / replace_node / connect / disconnect / change_representation_backend). Atomic + validated; on success recompiles through runtime routing and refreshes verification + object registry. `dry_run` previews without writing |
| `aieng.generate_preview` | Regenerate GLB/STL web preview from current STEP |
| `aieng.refresh_semantics` | Re-validate and re-extract semantic labels |
| `aieng.update_validation_status` | Write per-category validation flags |
| `aieng.write_evidence_scaffold` | Initialize `results/evidence_index.json` scaffold |
| `aieng.delete_project` | **[APPROVAL]** Permanently delete a project — its directory + chat sessions/messages. Irreversible |

### MCP introspection

| Tool | Purpose |
|------|---------|
| `mcp.check` | Guardrails, capability gaps, operation policy for this project |
| `mcp.parse_patch` | Validate a patch proposal without applying it |
| `mcp.prepare_execution` | Dry-run a patch proposal and return preflight side effects |

---

## Recommended workflows

### A — Inspect and understand a project
```
aieng.agent_context { project_id }
```
Read the geometry summary, note any `@artifact:` tokens marked stale, check
`suggested_next_steps`.

### B — CAD generation from scratch
```
1. cad.get_source            { project_id }                                (is there already a base?)
2. cad.set_reference_image   { project_id, image_url }                     (only when modelling a real product/character — sets a reference for every future thumbnail)
3. cad.execute_build123d     { project_id, code }                          [APPROVAL REQUIRED] (mode=replace, default)
4. (inspect the returned thumbnail + named_parts to confirm the shape is right)
```
Set `.label` and `.color` on each part in your build123d code and combine with
`Compound` so the result carries semantic names + readable colors (see the
build123d section above). After step 3 the project is `viewer_ready_glb` and
the web preview is current — no separate `generate_preview` call needed for
agent-built geometry. Step 2 is optional but **strongly recommended** for any
named real-world target: it pins a reference image into the project so every
build's thumbnail shows your model next to the truth.

### B2 — Incremental modeling (the sustainable loop)
```
1. cad.get_source         { project_id }                (source, named_parts, has_base)
2. cad.execute_build123d  { project_id, code, mode: "append" }   [APPROVAL REQUIRED]
3. (check response parts_added / named_parts and the thumbnail; repeat from 1)
```
In append mode the previous model is exposed as `previous_result`; your code adds to
it and must still reassign `result`. The response's `parts_added`, `named_parts`,
`mode`, and `used_base` tell you exactly what this step did — use them to decide the
next step instead of guessing or re-deriving state. Prefer this over resubmitting the
whole script each time.

### C — CAD → CAE simulation pipeline
```
1. aieng.agent_context        { project_id }
2. cae.apply_setup_patch      { project_id, patch }      (material, BCs, mesh)
3. cae.prepare_solver_run     { project_id }             (preflight, no execution)
4. cae.generate_solver_input  { project_id }             (write CalculiX .inp deck)
5. cae.run_solver             { project_id }             [APPROVAL REQUIRED]
6. cae.extract_solver_results { project_id }
7. cae.extract_field_regions  { project_id }
8. postprocess.refresh_cae_summary { project_id }
```

### D — Inspect results and explain findings
```
1. aieng.agent_context        { project_id }
2. cae.extract_field_regions  { project_id, field: "stress" }
```
Summarize the high-stress clusters; reference faces with `@face:id` so the user
can click to highlight them.

### E — Parametric modification (design iteration)
```
1. aieng.agent_context     { project_id }
2. cad.edit_parameter      { project_id, featureId, parameterName, newValue }  [APPROVAL]
3. aieng.refresh_semantics { project_id }
4. (re-run the CAE pipeline if geometry changed)
```

---

## Approval-gated tools

Tools marked `[APPROVAL REQUIRED]` mutate the package or execute an external
process. Always: (1) explain the side effects to the user, (2) wait for explicit
confirmation, (3) report the outcome after the call.

Currently approval-gated: `cad.execute_build123d`, `cad.edit_parameter`,
`cad.replace_part`, `cad.remove_part`, `cae.run_solver`, `aieng.delete_project`,
`aieng.apply_shape_ir_patch`.

---

## Stale-artifact warnings

After a geometry edit, `aieng.agent_context` includes an **EDIT IMPACT** section
listing `@artifact:` references needing revalidation. Treat these as hard blockers
before running a simulation. Typical fix:
```
1. aieng.refresh_semantics   { project_id }
2. cae.generate_solver_input { project_id }
3. cae.run_solver            { project_id }   [APPROVAL REQUIRED]
```
(A fresh `cad.execute_build123d` automatically clears stale state.)

---

## If the backend (port 8000) is unreachable

You may see `{"status": "error", "code": "connection_refused"}` or timeouts when
`AIENG_BACKEND_URL` is set — the FastAPI backend is not running.

**Do NOT restart processes yourself.** Tell the user and ask them to start it:
```powershell
conda activate aieng311
cd aieng-ui/backend
uvicorn app.main:app --reload --port 8000
```
Verify with `aieng.list_projects`. Note: if the backend is down, the MCP server
**falls back to in-process execution automatically** — tools still work (no live
UI), so you can usually continue regardless.

---

## .aieng package structure (reference)

The backend manages all package I/O; never read it directly. Structure:
```
<project_id>.aieng   (ZIP)
├── metadata.json            project name, status, timestamps
├── geometry/                source.py, sdf_source.py / manifold_source.py, shape_ir.json, generated.step, preview.stl/.glb, topology_map.json
├── graph/                   aag.json, feature_graph.json, interface_graph.json, brep_graph.json
├── state/                   revalidation_status.json (stale-artifact flags)
├── diagnostics/             shape_ir_verification.json, shape_ir_patch_report.json
├── registry/                object_registry.json (Shape IR node ↔ topology/mesh/viewer ids + params)
├── analysis/                computed_metrics.json, field_regions.json (solver-neutral CAE), cae_result_map.json (CAE ↔ topology/node), topology_optimization.json, design_study_problem.json
├── patches/                 (optional) design_candidates/<candidate_id>.json (proposed, validated, NEVER auto-applied)
├── candidates/              (optional) <candidate_id>/ derived design-study workspace (patch.json, geometry/shape_ir.json, provenance/, analysis/evaluation.json) — never overwrites baseline
├── provenance/              conversion_manifest.json (converter + geometry_execution record)
├── assembly/                (optional, multi-part) assembly_ir.json, part_registry.json, connection_graph.json, interface_resolution.json
├── simulation/              setup/deck artifacts, including assembly_cae_setup_draft.json, assembly_cae_model.json, optional assembly_calculix.inp
├── cae/                     setup.json, mesh_params.json, simulation/ (CalculiX .inp/.frd)
├── results/                 computed_metrics.json, field_regions.json, evidence_index.json
└── audit_log.jsonl          append-only action history
```

### Design study v0 (optional, parameter studies)

A package MAY carry `analysis/design_study_problem.json` — a backend contract for an
**agent-guided parameter design study**: design variables (with bounds / allowed values /
`safe_to_modify` / `semantic_role`), plus constraints and an objective that are **recorded, not
executed**. Proposed parameter changes live under `patches/design_candidates/<candidate_id>.json`.
This is **contract + validation only**: `POST /api/projects/{id}/design-study/validate` (or a
recompile) validates the problem (`diagnostics/design_study_problem_diagnostics.json`) and every
candidate (`diagnostics/design_study_candidate_validation.json`) — checking bounds, allowed values,
`safe_to_modify`, **protected interface variables**, `max_variables_per_candidate`, assembly
`selected_part_id` scope, and reasoning. **No optimization/search is run, no candidate is applied,
no geometry is recompiled, no CAE is run, and the baseline geometry is never modified.** Valid
candidates are normalized (`applied:false`) but not applied.

A validated candidate can then be **explicitly executed** into a derived workspace via
`POST /api/projects/{id}/design-study/candidates/{candidate_id}/run` (PR2). This applies the
patch to a DEEP COPY of the baseline Shape IR, writes `candidates/<id>/` (patch + derived
`geometry/shape_ir.json` — or `parts/<part>/geometry/shape_ir.json` for assembly part-scoped —
+ provenance + `analysis/evaluation.json`), and, when `compile` is enabled (default), recompiles
the candidate in a **throwaway copy** of the package so the baseline package's geometry artifacts
are never created or overwritten. Each run appends a deterministic `iter_NNN` record to
`analysis/design_study_iterations.json` and rebuilds `diagnostics/design_study_report.json`.
Execution is explicit and single-shot — **no optimizer/search/Pareto loop, no CAE, and no
candidate is ever auto-promoted into the baseline** (`baseline_modified:false` everywhere; best a
valid candidate reaches is `refine_candidate`).

Candidate evidence can be **explicitly evaluated** (PR5) via
`POST /api/projects/{id}/design-study/candidates/{candidate_id}/evaluate`, or refreshed
automatically by ranking when candidate-local evidence exists. This reads only artifacts under
`candidates/<id>/` — neutral/static metrics, optional `field_regions` / `cae_result_map`,
geometry execution manifest, and assembly/proxy evidence — then writes
`candidates/<id>/analysis/evaluation.json` plus
`candidates/<id>/diagnostics/evaluation_report.json`. The evaluator normalizes mass, volume,
max stress, max deflection, minimum safety factor, and optional compliance/stiffness proxies;
keeps units, load-case ids, and source paths; uses worst-case stress/deflection and lowest
safety factor across load cases; and marks proxy assembly evidence lower confidence with
`contact_physics_modeled:false` and `bolt_preload_modeled:false`
honesty. It never runs a solver, never recompiles geometry, never mutates baseline artifacts,
and never promotes a candidate.

Candidate proposal hints can be **explicitly generated** (PR6) via
`POST /api/projects/{id}/design-study/hints`. This reads the design-study variables,
candidate evaluations/ranking/scoring diagnostics, optional CAE/topopt maps, and assembly
recommendations, then writes `analysis/design_study_candidate_hints.json` plus
`diagnostics/design_study_candidate_hints_report.json`. Hints are structured and
machine-readable (`adjust_parameter`, `protect_parameter`, `rerun_evaluation`,
`request_user_input`, `stop_no_safe_hint`) with `variable_id`, direction, magnitude,
priority, confidence, evidence links, and safety notes. The hint layer is advisory only:
it never creates candidate patches, never runs optimization/search, never executes
candidates, never runs CAE, never ranks or accepts candidates, and never mutates geometry
or baseline artifacts. Low-confidence/proxy evidence leads to conservative hints and
explicit `contact_physics_modeled:false` / `bolt_preload_modeled:false` honesty notes.

**Executed candidates can be ranked** (PR3) via `POST /api/projects/{id}/design-study/rank`.
This reads the iteration history and per-candidate evaluation artifacts (building/refreshed from
candidate-local evidence when safe), classifies each candidate
as `feasible` / `infeasible` / `unknown` / `failed`, scores them against the problem objective
and constraints, and writes `analysis/design_study_candidate_ranking.json` +
`diagnostics/design_study_scoring_report.json`. Ranking is **advisory only** — it does not
search or propose new candidates, does not recompile geometry, does not run CAE, does not
promote any candidate to the baseline, and missing metrics honestly produce
`needs_more_evaluation` / low-confidence outcomes. The best candidate is selected only when
it is feasible, improves the objective, and has high-confidence metrics; otherwise
`best_candidate_id` is `null` and `safe_to_accept` is `false`.

**A ranked candidate can be explicitly accepted** (PR4) via
`POST /api/projects/{id}/design-study/candidates/{candidate_id}/accept`. This copies the
candidate's derived workspace into `accepted/<candidate_id>/` (patch, derived Shape IR,
evaluation, and acceptance provenance) and writes `analysis/design_study_acceptance.json` +
`diagnostics/design_study_acceptance_report.json`. Acceptance is **explicit and gated**:
- The candidate must be the `best_candidate_id` (or `override_unsafe` must be explicitly set).
- The candidate must be `feasible`; `failed` / `infeasible` / `unknown` candidates are rejected.
- The candidate workspace artifacts must exist.
- **Baseline geometry is never overwritten.** The accepted candidate is a derived design artifact
  only; production approval is **not** claimed.

**Candidate CAE evaluation request** (explicit, candidate-local) via
`POST /api/projects/{id}/design-study/candidates/{candidate_id}/cae-evaluate`. Derives
a candidate-local CAE setup from the baseline, normalizes existing candidate-local
neutral metrics into `candidates/<candidate_id>/analysis/evaluation.json`, and optionally
refreshes ranking. Solver execution is disabled by default and best-effort when enabled.
Baseline CAE artifacts are never overwritten.

**Canonical demo + regression** (`aieng-ui/backend/tests/test_design_study_demo.py`) exercises
the full PR1–PR5 pipeline end-to-end using deterministic static/neutral metrics (no external solver):
- Fixture: `aieng-ui/backend/tests/fixtures/design_study_demo/` — bracket-like baseline Shape IR,
  4 variables (wall_thickness, rib_thickness, fillet_radius, bolt_dia), 5 candidates:
  - `candidate_good` — valid, improves volume, within constraints
  - `candidate_bad_bounds` — rejected (out of bounds)
  - `candidate_protected` — rejected (protected variable)
  - `candidate_unknown` — valid but no metrics → `unknown`
  - `candidate_infeasible` — valid but stress violation → `infeasible`
- Full-flow test: validate → execute all 5 → inject static evaluations → rank → accept best.
- Hints path: explicit hint generation produces protected-variable, stress/safety, and
  rerun-evaluation hints without creating patches or modifying baseline geometry.
- Unsafe-data test: only bad candidates → ranking says no viable candidate → acceptance blocked.
- Missing-ranking test: acceptance without prior ranking → `needs_user_input`.

Future work: optimizer/search loop, multi-objective Pareto ranking, richer candidate CAE evidence ingestion,
auto-promotion to baseline, and design-history branching.

**Related docs:**
- [`aieng/docs/demo_catalog.md`](aieng/docs/demo_catalog.md) — canonical demos and regression flows
- [`aieng/docs/showcase_gallery.md`](aieng/docs/showcase_gallery.md) — showcase with demo talking points
- [`aieng/docs/showcase_gallery.json`](aieng/docs/showcase_gallery.json) — machine-readable gallery manifest
- [`aieng/docs/backend_capability_matrix.md`](aieng/docs/backend_capability_matrix.md) — capability status snapshot

A lightweight backend stability gate checks that canonical demos, artifact names, and honesty boundaries stay in sync:
```bash
pytest aieng/tests/test_backend_stability_gate.py -q
```
This is a consistency smoke test, not a production certification suite.

### Assembly IR v0 (optional, multi-part)

A package MAY carry `assembly/assembly_ir.json` — a backend representation of a **multi-part
assembly**: parts (+ roles / placements / materials), interfaces, and **simplified connections**
(`rigid_tie` / `bonded` / `bolted_proxy` / `welded_proxy` / `contact_proxy` / `spring_proxy`).
Connections are **PROXIES, not full nonlinear contact** — there is no bolt preload and no real
contact physics. When present, the backend best-effort writes
`diagnostics/assembly_validation.json`, `assembly/part_registry.json`,
`assembly/connection_graph.json`, and a solver-neutral `simulation/assembly_cae_setup_draft.json`
(auto on recompile, or via `POST /api/projects/{id}/assembly/process`). Schema:
`aieng/schemas/assembly_ir.schema.json`. Single-part packages are unaffected.

When per-part / package topology maps are available, the same call also **resolves interfaces
and validates connection geometry** (geometry-validation only — still no contact/preload/solver):
it resolves each interface's `topology_refs` to bbox/centroid/normal/area, applies the part
transform into world coordinates (`assembly/interface_resolution.json`), and judges each
connection's plausibility from centroid distance / bbox overlap / normal alignment / semantic-role
fit → `geometry_status` ∈ plausible / warning / invalid / insufficient_data
(`diagnostics/assembly_connection_geometry.json`). Invalid connections are marked `disabled` +
`needs_user_input` in the CAE setup draft. Unresolved refs are reported honestly, never invented.

Assembly CAE v0 then produces a **solver-neutral simplified proxy model**:
`simulation/assembly_cae_model.json` plus
`diagnostics/assembly_cae_model_diagnostics.json`. Solver deck generation is optional and
best-effort: `simulation/assembly_calculix.inp` is written only when enabled simplified
connections and actual per-part mesh refs exist; otherwise
`diagnostics/assembly_solver_deck_generation.json` records `skipped`. Solver execution is
also optional; v0 normalizes generic/fake assembly results when provided, otherwise writes
`diagnostics/assembly_solver_execution.json` with `solver_executed:false`. Assembly results map
to parts/interfaces/connections/source_ir_node with confidence in
`analysis/assembly_result_map.json` and `diagnostics/assembly_result_mapping.json`.

Assembly-aware topology optimization v0 is **explicit execution only**:
setup writes `analysis/assembly_topopt_problem.json`,
`diagnostics/assembly_topopt_derivation.json`, and, when supports+loads are safe,
`analysis/topology_optimization_problem.json`. A separate explicit backend helper
`run_assembly_topology_optimization(package_path, ...)` — exposed through
`opt.run_assembly_topology_optimization` and
`POST /api/projects/{project_id}/assembly/topology-optimization/run` — consumes
those artifacts, calls the existing single-part SIMP optimizer, and writes:
- `analysis/assembly_topology_optimization.json`
- `diagnostics/assembly_topopt_execution.json`
- `diagnostics/assembly_post_optimization_verification.json`
- `analysis/assembly_optimization_summary.json`
- `analysis/assembly_design_recommendations.json`
- `diagnostics/assembly_postprocess_report.json`
- `analysis/assembly_next_actions.json`
- `parts/<selected_part_id>/analysis/topology_optimization.json`
- `parts/<selected_part_id>/geometry/optimized_shape_ir.json` when writeback is safe

This optimizes **one selected `design_part` only**. Reference, fixture, fastener,
load-source, frozen, and non-editable parts are rejected. Mounting/bolt/weld/contact/
mating connector regions are passed through as preserve masks when their grid cells
are known; unmapped preserve regions are warned, never silently ignored. Writeback
creates a selected-part derived artifact and does **not** overwrite package-level
geometry or reference parts. Post-optimization verification checks that only the
selected part got derived artifacts, that preserve interfaces stay traceable (or
warn honestly when they do not), and that proxy/contact/preload limitations are
still explicit. It does **not** certify physical interface equivalence.
After verification, a best-effort rule-based postprocess pass writes structured
assembly design recommendations and a postprocess report. These are advisory
only: they do not rerun topopt automatically, do not mutate geometry, and do
not certify downstream export/reconstruction safety beyond the same proxy-model
honesty boundaries.

Canonical backend regression/demo fixture: `aieng-ui/backend/tests/fixtures/assembly_topopt_demo/`
plus `aieng-ui/backend/tests/test_assembly_topopt_demo.py`. It exercises the full
backend-only loop on a deterministic proxy-based assembly:
`/assembly/process` → `write_assembly_topopt_problem(...)` →
`/assembly/topology-optimization/run` → post-optimization verification + recommendation/report writeback, and also pins the unsafe-data
`needs_user_input` path where no standard problem is emitted and no geometry is
overwritten. Run it with:
`pytest aieng-ui/backend/tests/test_assembly_topopt_demo.py -q`

All outputs keep `production_ready:false`, `contact_physics_modeled:false`, and
`bolt_preload_modeled:false`. Future work: real nonlinear contact modeling, bolt preload,
assembly meshing improvements, and simultaneous multi-part topology/size optimization.

---

## Fallback mode — when you do not have MCP tools

Some agent clients (notably **Kimi Code CLI** in its default configuration) do not
automatically load user-defined MCP servers. If `aieng.list_projects` is not in
your tool list, follow this fallback path.

### Environment topology (know where things are)

| Service | Address | Purpose |
|---------|---------|---------|
| React UI | `http://localhost:5173` | The workbench front-end |
| FastAPI backend | `http://localhost:8000` | API + MCP bridge + static assets |
| Platform data | `aieng-ui/data/` | Projects, runtime config, logs |
| Projects root | `aieng-ui/data/projects/` | One folder per project |
| Conda env | `aieng311` | Where build123d / OCP live |

### Running build123d without MCP

Use the provided runner so exports are handled exactly like the backend does
(including `binary=True` for GLB):

```bash
conda activate aieng311
cd aieng-ui/backend/scripts
python agent_build123d_runner.py my_model.py --out-dir ./output
```

Output files:
- `output/result.step` — AP214 STEP
- `output/result.stl` — binary STL
- `output/result.glb` — **binary** GLB (if export succeeded)
- `output/topology.json` — face / solid entities with labels

### Registering the model in the UI without MCP

After you have a STEP file (and optional preview GLB/STL), import it as a proper
project so the React UI can display it:

```bash
conda activate aieng311
cd aieng-ui/backend/scripts
python agent_import_project.py ../../output/result.step \
    --name "My Model" \
    --preview ../../output/result.stl \
    --project-id my_model_001
```

This atomically:
1. Creates the `.aieng` package.
2. Runs topology + feature-graph enrichment.
3. Creates the project directory + `metadata.json`.
4. Copies the preview into `viewer/`.
5. Updates the project status to `viewer_ready_*`.

Refresh the UI (`http://localhost:5173`) and the project will appear.

### Kimi Code CLI specific notes

Kimi Code CLI does **not** read `.mcp.json` automatically (unlike Claude Code).
To give Kimi the workbench MCP tools, you must either:
- Use Kimi's settings UI to add the MCP server defined in `.mcp.json`.
- Or accept fallback mode and use the scripts above.

### Direct REST API (last resort)

If you need to trigger backend actions without MCP, the backend exposes standard
HTTP endpoints. The most useful ones for agents:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Backend status, tool count |
| `/api/projects` | GET | List projects |
| `/api/projects` | POST | Create empty project |
| `/api/projects/{id}/upload` | POST | Upload STEP or `.aieng` |
| `/api/projects/{id}/cad-preview` | GET | Stream GLB/STL preview |
| `/api/projects/{id}/agent-context` | GET | Full geometry + CAE context |
| `/api/agent/invoke-tool` | POST | Run any MCP tool by name (emits UI events) |

Example — invoke a tool directly:
```bash
curl -X POST http://localhost:8000/api/agent/invoke-tool \
  -H "Content-Type: application/json" \
  -d '{"tool": "cad.execute_build123d", "input": {"project_id": "...", "code": "..."}}'
```

---

## Common mistakes to avoid

| Mistake | Correct approach |
|---------|-----------------|
| Reading `aieng/src/` to learn capabilities | Call `aieng.agent_readme`; real engine is `aieng-ui/backend` |
| Running code to diagnose the backend | Use MCP tools; if backend down, ask user to start it |
| Including `export_step(...)` in build123d code | Omit exports — the runner adds them |
| `result.export_step(path)` (build123d <0.9 API) | Use `export_step(result, path)`, or just omit |
| `cae.run_solver` without preflight | Call `cae.prepare_solver_run` first |
| Referencing stale artifacts after an edit | `aieng.refresh_semantics` then regenerate |
| Raw face indices instead of `@face:id` | Use pointer IDs from `aieng.agent_context` |
| Judging geometry from one view (iso) only | Inspect all 4 views in the contact sheet (front/side/top/iso) — alignment errors hide in iso |
| Monochrome parts → can't tell which is which | Set `.color = Color(r,g,b)` on each labelled part |
| Building straight to finish without review | After each step, list 3–5 fail-first objections by view + part, then decide next iteration |
| Stacking `Box(...)` for a character/vehicle/product | Switch to Industrial Design Mode — use `loft`/`sweep`/`revolve` + aggressive `fillet` for visible exterior forms |

---

## Environment variables (for MCP server operators)

| Variable | Purpose |
|----------|---------|
| `AIENG_PLATFORM_DATA` | Override the data directory (default `aieng-ui/data`) |
| `AIENG_BACKEND_URL` | When set, forward tool calls to the running backend for live UI |
| `AIENG_MCP_BLOCK_APPROVAL_TOOLS` | Set to `1` to hard-block approval-gated tools at the server level |

Full wiring (Claude Code / Copilot / Codex): `aieng-ui/backend/MCP_SETUP.md`.
