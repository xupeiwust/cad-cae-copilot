# `.aieng` vs `earthtojake/text-to-cad`: Positioning Comparison

Source: https://github.com/earthtojake/text-to-cad

This is a comparison of design positioning. The question is not whether text-to-cad is good; it is which of its mechanisms strengthen `.aieng` as a CAD/CAE-side semantic export and evidence layer without changing `.aieng`'s identity.

## 1. One-line positioning

- **text-to-cad** is an *agent-side* skill+harness bundle that turns a generic coding agent into a CAD authoring runtime. Agents edit build123d Python sources, regenerate STEP/STL/3MF/GLB targets via `scripts/step`, inspect them via `scripts/inspect`, and hand artifacts to CAD Explorer for visual review. The product is the agent workflow.
- **`.aieng`** is a *CAD/CAE-side* semantic export and evidence package format. CAD/CAE tools emit `.aieng` packages so general AI systems can understand engineering state (features, interfaces, constraints, simulation context, validation state, evidence, allowed operations) before requesting external tool actions. The product is the file format and its CAD/CAE-derived structured resources.

Different identities, different layers of the stack. They are not competitors; they could in principle compose (an agent built with text-to-cad style skills could be the agent that consumes a `.aieng` package, and could be one of the external tools that writes evidence back).

## 2. Architecture in one diagram each

```
text-to-cad:
  User prompt → Agent edits build123d source → scripts/step regenerates STEP → scripts/inspect verifies →
  CAD Explorer renders → Agent quotes @cad[path/to/model.step#selector] handles → loop.

.aieng:
  CAD/CAE tool emits .aieng package (geometry refs, topology, features, context,
  simulation setup, claims, evidence ledger, tool trace, completeness report)
   → External AI/agent reads package, proposes structured patches and tool requirements
   → External CAD/CAE/mesher/solver executes, writes evidence back into the package
   → aieng validate enforces cross-resource consistency. .aieng never executes solvers,
     meshers, or arbitrary B-rep edits.
```

## 3. Side-by-side table

| Dimension | text-to-cad | `.aieng` |
|---|---|---|
| Primary artifact | build123d Python source + regenerated STEP/STL/3MF/GLB | `.aieng` package (structured JSON/YAML resources) |
| Source of truth | Python CAD source file (edit it, regenerate everything) | Structured resources in package; STEP remains immutable execution artifact |
| AI role | Agent authors CAD code | Agent reads semantic state, proposes structured patches, never edits geometry |
| Geometry generation | Yes — agent generates geometry by editing source | No — `.aieng` records semantic edit intent; CAD writeback is external (CadQuery parametric path only) |
| Topology | Exported as derived artifact alongside STEP | First-class resource (`geometry/topology_map.json`) with explicit `extraction_mode` and provenance |
| Reference notation | `@cad[path/to/model.step#selector]` strings used by `scripts/inspect` | Stable IDs (`feat_*`, `face_*`, `iface_*`, `claim_*`, `evidence_*`) referenced by JSON pointer inside resources |
| Visual review | CAD Explorer web GUI, returns Explorer URLs | None today — visual scaffold (annotation layers, manifest) describes what visual assets exist but does no rendering |
| Snapshots | Optional `scripts/render` PNG thumbnails for review loop | Not present; explicitly forbidden as validation evidence |
| Validation | Programmatic geometry checks (`measure`, `mate`, `frame`, `diff`) on regenerated STEP | Cross-resource validator (`aieng validate`); evidence/claim ledgers with `decision_criteria` per claim |
| Solver / mesh | Out of scope | Out of scope for `.aieng` core; handoff contracts + evidence import only |
| Honesty discipline | "Edit sources first"; do not git-diff derived artifacts | "Best-effort semantic conversion with explicit missingness"; `unsupported` ≠ false; `auto_advance: false` |
| Install footprint | Python venv + Node + multiple skill installers per agent | Pure Python; CadQuery optional; no Node, no GUI required |
| Distribution | Per-agent installers (`codex-install.sh`, `claude-install.sh`, etc.) + `agent-skills-cli` | `pip install aieng`; optional `[geometry]` and `[mcp]` extras |
| Benchmark | 10 parametric geometry targets in `benchmarks/` (LFS); evaluate whether agent regenerates target | `benchmarks/handoff/` and `benchmark_runs/*` for AI understanding/honesty/usefulness vs raw STEP |
| Audit trail | Git history of source + regenerated artifacts | `results/evidence_index.json`, `results/claim_map.json`, `provenance/tool_trace.json`, `validation/completeness_report.json` |
| Manufacturing | SendCutSend skill (preflight DXF/STEP upload) | Out of scope; could be referenced via external tool requirements |

## 4. Similarities / Differences / Useful ideas / Reject

### Similarities
- Both refuse to treat derived artifacts as authoritative (text-to-cad: regenerate from Python; `.aieng`: structured resources are source of truth, summaries are derived).
- Both insist that stable references — not free text — be how AI points at geometry.
- Both refuse to rely on git-diff over large binary geometry as a comparison signal.
- Both treat visual rendering as review, not validation.

### Differences (identity-defining for `.aieng`)
- text-to-cad **generates** CAD. `.aieng` **describes** CAD that external tools generated.
- text-to-cad's agent edits geometry. `.aieng`'s agent edits structured semantics; geometry edits happen only via external CadQuery regeneration (G7) on tightly guarded `editability=executable_by_regeneration` features.
- text-to-cad ships agent skills and harness files. `.aieng` ships a file format and a deterministic CLI.
- text-to-cad's review loop is human-in-the-loop visual inspection. `.aieng`'s review loop is evidence + claim status + completeness, machine-checkable.

### Useful ideas (worth borrowing — see borrowing-candidates doc)
- **Stable `@cad[...]` reference syntax** for cross-tool addressing of geometry elements. `.aieng` already has stable IDs; a canonical string-form like `@aieng[resource#id]` would let agents quote refs in chat and tools resolve them.
- **`scripts/inspect refs`-style inspection CLI** as the canonical way to enumerate, validate, and dereference handles. Pairs naturally with the proposed `aieng ref-inspect`, `aieng ref-list`, `aieng ref-check`.
- **CAD Explorer as read-only review broker.** A read-only `.aieng` viewer that visualises features, protected regions, simulation targets, evidence status, claim breakdown, and completeness — without ever becoming source of truth — would materially help debugging.
- **Source-first regeneration discipline.** Reinforces an existing `.aieng` principle (structured JSON/YAML is authoritative; summaries are derived). Useful as a written rule borrowed and documented.
- **Snapshot/review images as a fast iteration aid** — but only as derived artifacts behind a non-validation flag; never as evidence.
- **Benchmark input packs with expected observations and scoring rubrics.** text-to-cad has 10 parametric targets; `.aieng` already has a handoff benchmark — borrow the input-pack discipline and rubric structure.

### Reject (would change `.aieng` identity)
- **Agent-side skill bundle as the product.** `.aieng` is a file format; skills are at most a thin optional consumer.
- **Agent-authored geometry as primary workflow.** Geometry authoring belongs to external CAD; `.aieng` records intent and imports evidence.
- **Vendoring per-agent installers** (`codex-install.sh`, `claude-install.sh`, etc.). MCP is `.aieng`'s one optional access interface; multiplying agent integrations would invert the product.
- **Web GUI server as part of the default install.** Heavy Node dependency for a viewer must remain optional and out-of-tree.
- **Render-as-evidence.** Snapshots must never satisfy a claim. text-to-cad already enforces this for *validation*; `.aieng` must enforce it for *claim status* too.
- **Git LFS for benchmark binaries.** `.aieng` benchmarks should remain text-first (structured input indexes, expected observations) so AI readers can ingest them without LFS.

## 5. What `.aieng` already does that text-to-cad does not

- Claim/evidence ledger with per-claim `decision_criteria`, `pass_requires`, `unsupported_if`, `auto_advance: false`.
- Cross-resource consistency validator (G5) — contradictions across solver_execution, claims, forbidden_core_actions, tool_trace, claim_map are flagged.
- Explicit completeness/missingness report with `available` / `partial` / `missing` / `unknown` / `unsupported`.
- Tool trace as separate provenance resource, not git history.
- Task spec + external-tool-requirements contract describing the handoff to external CAX before any tool runs.
- Adapter capability declaration (G11) for emitters.
- Schema const guards enforcing the execution boundary at the data level, not just the prose level.

These are the load-bearing pieces of `.aieng`'s identity. Any borrowing from text-to-cad must preserve them.

## 6. Bottom line

text-to-cad solves "make a coding agent generate CAD." `.aieng` solves "make CAD/CAE state legible and auditable to a general AI before it asks any tool to do anything." The two designs are complementary, not redundant.

The mechanisms worth borrowing are all about **addressing, inspection, review, and benchmark discipline** — the parts that survive after you delete the geometry-generation core. The borrowing should not import the agent-authoring identity that defines text-to-cad.
