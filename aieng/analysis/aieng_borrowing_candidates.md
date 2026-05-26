# `.aieng` Borrowing Candidates from `earthtojake/text-to-cad`

Per-mechanism evaluation. Each row answers: how it works there, how valuable it is here, how to adapt without crossing `.aieng`'s execution boundary, what changes are required, what could go wrong, and which phase should consider it.

Value scale: **High** = directly strengthens `.aieng`'s file-format/evidence identity; **Medium** = nice ergonomics; **Low** = marginal or duplicative.

---

## 1. Stable references like `@cad[...]`

**How it works in text-to-cad.** Strings of the form `@cad[path/to/model.step#selector]` and `@cad[path/to/assembly.step#moving_selector]` are quoted by the agent and passed to `python scripts/inspect refs` / `measure` / `mate` / `frame`. They are a stable, copy-pasteable handle to a geometry element across turns.

**Value for `.aieng`: High.** `.aieng` already has stable IDs in every structured resource (`feat_*`, `face_*`, `edge_*`, `iface_*`, `claim_*`, `evidence_*`, `trace_*`). What is missing is a canonical *string form* that AI/agents/MCP/CLI can quote in prose, copy from chat into a tool call, and the package can dereference deterministically.

**How to adapt.** Define `@aieng[<resource-path>#<id>]` as the canonical reference string. See [aieng_reference_notation_proposal.md](aieng_reference_notation_proposal.md). Add three CLI verbs: `aieng ref-inspect`, `aieng ref-list`, `aieng ref-check`. Add a `references` field to the MCP tool surface so agents can dereference handles in one call.

**Required changes.** Small. No schema breakage — IDs already exist. New: a `references` JSON-pointer mini-spec in `docs/`, three CLI verbs, one MCP tool. Optional `references_index.json` is a *generated* index only.

**Boundary risks.** A reference resolver must not become a query/edit interface for geometry. Resolve to existing structured records only; never synthesise data.

**Suggested phase: Phase 18A.**

---

## 2. CAD Explorer / visual inspection workflow

**How it works.** A read-only Node/Vite web GUI started via `npm --prefix scripts/explorer run dev:ensure -- --file model.step`. Reuses existing servers, returns a printed Explorer URL. Supports `.step`/`.stp`/`.stl`/`.3mf`/`.dxf`/`.urdf`/`.srdf`/`.sdf`. Read-only, no source modification.

**Value for `.aieng`: Medium.** A read-only viewer that inspects an `.aieng` package would help users and agents debug coverage, claim status, and protected regions. But the value is in the *resource visualization*, not the *geometry visualization* — the latter belongs to external CAD viewers.

**How to adapt.** Build an optional `aieng-viewer` package (separate `pyproject` extra or sibling repo) that reads only the structured resources and presents: feature graph, topology adjacency, protected regions, simulation targets, evidence/claim status, tool trace, completeness. See [aieng_viewer_mvp_proposal.md](aieng_viewer_mvp_proposal.md). Keep it out of the default install.

**Required changes.** New optional extra. No schema change. New CLI verb `aieng view <package.aieng>` that simply prints a launch hint if the extra is not installed.

**Boundary risks.** (a) Viewer becoming source of truth — mitigate by making it read-only and stamping every page "derived view, see `<resource.json>` for authoritative state." (b) Heavy Node deps in default install — keep behind extra. (c) Geometry rendering tempting users to treat it as validation — restrict viewer to *semantic* visualisation; do not render mesh from STEP.

**Suggested phase: Phase 18B (optional).**

---

## 3. Source-first regeneration discipline

**How it works.** "Edit the owning source file or imported source file first, then regenerate the explicit target with the relevant skill tool." Derived artifacts are never hand-edited; git-diff is not used for large derived files.

**Value for `.aieng`: High** (but already partly internalised). `.aieng` already says structured JSON/YAML is source of truth and Markdown summaries are derived. What is missing is a single written rule explaining the analogous discipline for *every* derived resource: AAG, object registry, interface graph, summaries, README_FOR_AI.md, completeness report.

**How to adapt.** Add a short `docs/derived_artifact_discipline.md` (or a section in `core_position.md`) enumerating: which resources are derived, which are source-of-truth, and what `--overwrite` semantics mean. No code change.

**Required changes.** Docs only.

**Boundary risks.** None.

**Suggested phase: Phase 18 (docs slice, low cost).**

---

## 4. Explicit derived-artifact generation (named targets, never directory-wide)

**How it works.** "Do not run directory-wide generation. Use explicit target paths." Each artifact is produced by an explicit command with explicit inputs.

**Value for `.aieng`: Medium-High.** Already true: every `.aieng` CLI verb writes a named resource into a named package. Worth codifying as a CLI invariant so contributors do not add a `aieng regenerate-all` shortcut that hides which inputs produced which outputs.

**How to adapt.** Add a contribution rule: every new CLI verb writes exactly one structured resource (plus index updates). No "regenerate everything" verb. The existing reference demo orchestration script can chain the verbs in user-facing demos, but the CLI itself stays granular.

**Required changes.** Contribution guideline in `docs/` (could live in `architecture.md`). No code.

**Boundary risks.** None.

**Suggested phase: Phase 18 (docs slice).**

---

## 5. Snapshot / review loop (`scripts/render` thumbnails)

**How it works.** Quick PNG thumbnails of generated STEP geometry, used as a fast visual sanity check during iteration.

**Value for `.aieng`: Low.** `.aieng`'s value is in *being readable by AI*, not in being viewable by humans. Thumbnails would risk being mistaken for validation evidence. Visual scaffolding already exists at the metadata level (`visual/annotation_layers.json`, `visual/model_manifest.json`) and explicitly does *not* render.

**How to adapt.** Do not add a snapshot generator to `.aieng` core. If a future viewer (candidate #2) adds export-as-PNG, the resulting image must:
- be written under `visual/snapshots/` with a generated-asset marker
- never be referenced by `results/evidence_index.json`
- be excluded from claim decision criteria via a schema-level forbidden role
- carry a `not_validation_evidence: true` flag in its sidecar JSON

**Required changes.** Schema guard if and only if viewer ships snapshot export.

**Boundary risks.** Very high — easy to slip into "snapshot looks fine → claim passes." Schema const guards must enforce that no evidence entry has a snapshot `producer_kind`.

**Suggested phase: Future / behind viewer.**

---

## 6. Topology artifact export

**How it works.** Topology data (edge graphs, face adjacency, vertex coords) exported as a derived sidecar alongside STEP.

**Value for `.aieng`: Already present.** `geometry/topology_map.json` + `graph/aag.json` are first-class. text-to-cad's topology is *flat sidecar*; `.aieng`'s topology is structured, ID-stable, validator-checked, and carries `extraction_mode`/`runtime_provider` provenance.

**How to adapt.** Nothing to borrow — `.aieng` is ahead here. Phase 17A will harden the real-geometry path.

**Required changes.** None.

**Boundary risks.** Do not regress to flat sidecar export.

**Suggested phase: Reject (no borrow needed).**

---

## 7. Benchmark prompt/output packaging

**How it works.** `benchmarks/` directory with 10 parametric geometry targets (rectangular block, flange, L-bracket, stepped shaft, enclosure, clevis bracket, radial engine cylinder, centrifugal impeller, spiral staircase, planetary gear stage). Stored via Git LFS.

**Value for `.aieng`: Medium.** `.aieng` already has `benchmarks/handoff/` and `benchmark_runs/bracket_001_manual/` and `benchmark_runs/real_bracket_001/`. What can be borrowed is the *input-pack discipline* — naming a small portfolio of representative parts and reusing the same questions across them — to compare honesty/usefulness at scale.

**How to adapt.** Expand `benchmark_runs/` to cover 3–5 part families (bracket, flange, enclosure, plate-with-pattern, shaft). Reuse the existing 16/18-question rubric. Avoid LFS; keep STEP fixtures small or generatable via `scripts/generate_real_bracket_step.py`-style scripts. See [aieng_benchmark_upgrade_proposal.md](aieng_benchmark_upgrade_proposal.md).

**Required changes.** New fixture generators + benchmark scaffolds; no schema change.

**Boundary risks.** Benchmarks must keep measuring *understanding, honesty, evidence-correctness, boundary-correctness* — not whether a model generates STEP. Do not score CAD synthesis.

**Suggested phase: Phase 18C.**

---

## 8. Skill packaging and install scripts

**How it works.** Per-agent install scripts (`codex-install.sh`, `claude-install.sh`, `gemini-install.sh`, `openclaw-install.sh`) plus universal `npx agent-skills-cli`. Skills live in `skills/<name>/SKILL.md`.

**Value for `.aieng`: Low.** `.aieng` is a file format; bundling agent skills would invert the product. MCP is the one optional access surface and that is already implemented.

**How to adapt.** Do not. Continue: `pip install aieng`, optional `[mcp]` and `[geometry]` extras, no per-agent installers.

**Required changes.** None.

**Boundary risks.** If `.aieng` ships an agent skill bundle by default, it stops being a CAD/CAE-side export format and starts being a CAD agent product.

**Suggested phase: Reject.**

---

## 9. Local-first workflow

**How it works.** Everything runs locally (Python venv + Node). No cloud service. CAD Explorer reuses local servers.

**Value for `.aieng`: High** (already true). `.aieng` is local-only by design. Worth keeping as an explicit invariant.

**How to adapt.** No change. Add a one-line invariant to `core_position.md`: "All `.aieng` core operations are local. No network, telemetry, or remote service is required for any CLI verb."

**Required changes.** Docs.

**Boundary risks.** None.

**Suggested phase: Phase 18 (docs slice).**

---

## 10. Prompt-reference UX for follow-up edits

**How it works.** Agent quotes `@cad[...]` handles from previous turns to make precise edits without re-parsing. The handle is the contract between turns.

**Value for `.aieng`: High.** Same problem solved on the semantic side: when an agent says "tighten the hole pattern tolerance," it should quote `@aieng[graph/feature_graph.json#feat_hole_pattern_001]` rather than free-text "the hole feature." The string form is portable across CLI, MCP, chat, PRs.

**How to adapt.** Covered by candidate #1. Additionally, update the MCP tool surface so every tool that returns a record returns its canonical `@aieng[...]` form; this makes follow-up references trivial for agents.

**Required changes.** MCP tool response shape updates (additive). Documentation in `docs/mcp_server.md`.

**Boundary risks.** None beyond #1.

**Suggested phase: Phase 18A (combined with #1).**

---

## Summary recommendation table

| # | Mechanism | Value | Phase |
|---|---|---|---|
| 1 | `@aieng[...]` reference syntax + CLI | High | 18A |
| 2 | Optional read-only viewer | Medium | 18B |
| 3 | Source-first / derived-artifact discipline (docs) | High | 18 (docs) |
| 4 | Granular per-resource CLI invariant (docs) | Medium-High | 18 (docs) |
| 5 | Snapshot/review images | Low | Future / behind viewer |
| 6 | Topology export | n/a (already ahead) | Reject |
| 7 | Benchmark input packs | Medium | 18C |
| 8 | Agent skill installers | Low | Reject |
| 9 | Local-first invariant (docs) | High | 18 (docs) |
| 10 | Prompt-reference UX (MCP response refs) | High | 18A |

Reject 6, 8 (would dilute identity). Defer 5 (snapshot) until and unless a viewer exists. Everything else clusters into Phase 18A (references), 18B (optional viewer), 18C (benchmark refresh), plus a small docs slice covering 3, 4, 9.
