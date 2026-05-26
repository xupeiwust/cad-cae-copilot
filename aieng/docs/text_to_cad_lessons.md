# Lessons from `earthtojake/text-to-cad`

Source: https://github.com/earthtojake/text-to-cad

This note summarises what `.aieng` should and should not borrow from text-to-cad. The analysis that produced this summary lives in `analysis/`:

- [text_to_cad_comparison.md](../analysis/text_to_cad_comparison.md)
- [aieng_borrowing_candidates.md](../analysis/aieng_borrowing_candidates.md)
- [aieng_reference_notation_proposal.md](../analysis/aieng_reference_notation_proposal.md)
- [aieng_benchmark_upgrade_proposal.md](../analysis/aieng_benchmark_upgrade_proposal.md)
- [risk_register.md](../analysis/risk_register.md)

## Key sentence

`.aieng` should borrow text-to-cad's addressing and review patterns, not its CAD authoring identity.

## What text-to-cad does well

- **Stable references.** `@cad[path/to/model.step#selector]` handles let an agent quote a precise geometry element across turns and into CLI commands such as `python scripts/inspect refs '@cad[...]'`. The reference is portable through chat, PR descriptions, and tool calls.
- **Review-oriented agent workflow.** Agents edit build123d Python sources, regenerate explicit STEP/STL/3MF/GLB targets, validate with `scripts/inspect`, and hand artifacts to a read-only CAD Explorer for review. Authoring and review are clearly separated.
- **Local-first derived artifact discipline.** "Edit the owning source file first, then regenerate the explicit target." Derived artifacts are never hand-edited; `git diff` on large derived files is explicitly rejected as a comparison signal. Everything runs locally.
- **Benchmark packaging.** A small, named portfolio of representative parts (rectangular block, flange, L-bracket, stepped shaft, enclosure, clevis bracket, radial engine cylinder, centrifugal impeller, spiral staircase, planetary gear stage) serves as fixed input scaffolding for comparing agents.

## What `.aieng` should borrow

- **`@aieng[...]` reference notation.** A canonical string form over `.aieng`'s already-stable IDs so AI/agents/MCP/CLI/PRs/benchmarks can quote handles deterministically. See [`reference_notation.md`](reference_notation.md).
- **Reference inspection/list/check commands.** `aieng ref-inspect`, `aieng ref-list`, `aieng ref-check`. Planned as part of Phase 18A.
- **Derived artifact discipline as a written rule.** Structured JSON/YAML resources are source of truth; AAG, registry, interface graph, visual index, summaries, and benchmark outputs are derived. See [`derived_artifact_discipline.md`](derived_artifact_discipline.md).
- **Benchmark refresh focused on AI package understanding.** A small set of representative coverage probes (flange, plate_with_pattern, and later optionally enclosure, shaft_stepped) plus new categories: reference correctness, completeness reasoning, evidence trace, external-tool-boundary correctness, unsupported-claim correctness. Coverage probes, *not* a fixed list of supported part families.

## What `.aieng` should reject or defer

- **Text-to-CAD generation.** `.aieng` does not turn natural-language prompts into geometry. CAD authoring belongs to external CAD tools. No `aieng generate`, `aieng synthesise`, or `aieng author` verb.
- **Agent-authored CAD workflow as the product.** `.aieng` is a file format. text-to-cad's product is the agent skill bundle plus harness; importing that identity would invert `.aieng`.
- **Per-agent skill installers.** No `claude-install.sh`, `codex-install.sh`, `gemini-install.sh`, or equivalent. MCP remains the one optional access surface.
- **Heavy default viewer/frontend dependencies.** No Node/Vite/three.js in the default install. The default install stays pure Python and `aieng validate` works without any extras.
- **Snapshots as validation evidence.** Even if a future viewer or rendering helper produces PNGs, snapshots are never admissible in `results/evidence_index.json` or as claim support. This guard must be enforced at schema and writeback layers when any such helper is introduced.
- **Viewer implementation in Phase 18.** A read-only viewer is conceptually compatible with `.aieng`'s boundary, but is deferred. See [`roadmap.md`](roadmap.md) Phase 18B note and `issues/phase_18_optional_viewer.md` for the deferred status.

## Why this borrowing pattern is safe

The mechanisms above survive the test: delete text-to-cad's geometry-generation core and the addressing/review/discipline/benchmark patterns still make sense. The mechanisms in the "reject or defer" list do not survive that test; they are inseparable from text-to-cad's authoring identity and would change `.aieng`'s product if imported.
