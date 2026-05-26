---
title: "[Phase 18B] Optional read-only `.aieng` viewer — DEFERRED"
labels: ["phase-18", "phase-18b", "viewer", "deferred"]
status: deferred
---

## Status: Deferred — not part of current Phase 18 implementation

This issue is **deferred** and is **not part of the current Phase 18 implementation plan**. It is preserved here as a written record of the design space and the conditions any future implementation would have to meet. Implementation of a viewer requires **separate approval** before any work begins.

Current Phase 18 implementation work is limited to:

- **Phase 18A** — stable AI-facing reference notation (`@aieng[...]` + `ref-inspect` / `ref-list` / `ref-check`),
- **Phase 18C-min** — general CAX semantic coverage benchmark refresh.

See [docs/roadmap.md](../docs/roadmap.md) Phase 18 section for the canonical status.

## Why deferred

A read-only viewer that visualises the *structured package* (features, claims, evidence, completeness, tool trace) is conceptually compatible with `.aieng`'s boundary. It is deferred because:

- **Dependency risk.** Any viewer adds runtime surface area. The project's lightweight, local-first default install must remain unaffected, and the simplest viewer designs still risk pulling in heavier static-asset toolchains or platform-specific dependencies over time.
- **Boundary risk.** Viewers tempt downstream consumers to treat the rendered view as authoritative state, or to attach snapshots to claims as if they were validation evidence. Both would break the discipline documented in [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md).
- **Opportunity cost.** Phase 18A and Phase 18C-min produce direct, measurable benefits (better addressing, better honesty benchmarks). A viewer is supportive infrastructure; it does not strengthen the package format itself.

The reference and benchmark work proceeds first. A viewer may be revisited later if and only if a concrete need emerges that the existing CLI inspection (`aieng validate`, `aieng ref-inspect`, `aieng ref-list`, structured resources read directly) cannot serve.

## Hard requirements if ever revisited

Any future viewer implementation would have to satisfy all of the following before any work begins:

1. **Must remain read-only.** No editing, no claim advancement, no patch application, no resource writes of any kind. Hash-before / hash-after invariant test required.
2. **Must remain optional.** Behind an extra (`pip install aieng[viewer]` or equivalent). Default install footprint unchanged. `aieng` without the extra must continue to pass the full test suite.
3. **Must visualise semantics only.** No 3D STEP rendering, no mesh viewer, no solver-result colour map. The viewer reads structured JSON/YAML resources and presents them as tables, lists, and lightweight diagrams. Geometry visualisation belongs to external CAD viewers.
4. **Must enforce snapshot-as-evidence guards.** Schema rejection of `producer_kind: "aieng_viewer"` in `results/evidence_index.json`; writeback rejection by `aieng record-evidence`; sidecar markers (`not_validation_evidence: true`) on any image export. See [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md) rule 6.
5. **Must be local and offline.** Bind to `127.0.0.1` only. No telemetry. Verified by an offline-install test.
6. **Must carry the "derived view" banner on every page.** "Derived view of `<package>`. Authoritative state lives in the JSON/YAML resources."
7. **Must not import geometry kernels** (`cadquery`, `OCP`, `build123d`, `trimesh`, `pyvista`) inside the viewer module. Lint rule required.
8. **Must satisfy separate approval.** A new design review and explicit go-ahead are required before implementation work starts.

## Background

`earthtojake/text-to-cad` ships a read-only CAD Explorer that opens generated geometry in a web GUI for review. The pattern of a strictly read-only review surface is healthy. Applying it to `.aieng` is only useful if it visualises the structured package itself — not the geometry inside it — and only if the guards above are in place. Since none of those guards exists today and there is no current pressure to add them, the viewer is deferred.

See [analysis/aieng_viewer_mvp_proposal.md](../analysis/aieng_viewer_mvp_proposal.md) for the previously-drafted MVP design, retained for reference only. The MVP design is **not** an active implementation plan.

## Related documents

- [docs/roadmap.md](../docs/roadmap.md) (Phase 18B note)
- [docs/text_to_cad_lessons.md](../docs/text_to_cad_lessons.md)
- [docs/derived_artifact_discipline.md](../docs/derived_artifact_discipline.md)
- [analysis/aieng_viewer_mvp_proposal.md](../analysis/aieng_viewer_mvp_proposal.md) (reference only; deferred)
- [analysis/risk_register.md](../analysis/risk_register.md) (R2, R4, R6, R14, R15)

## Action

**No implementation work to be done under this issue at this time.** Update or revisit only after explicit separate approval.
