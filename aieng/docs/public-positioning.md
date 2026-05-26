# Public Positioning

This doc is the **outward-facing** explanation of `.aieng`. It is written for GitHub visitors, contributors, and reviewers who land on the repo cold and need to understand the value in under a minute.

The inward-facing architectural rationale lives in [`core_position.md`](core_position.md) and the workspace [`Agent.md`](../../Agent.md). The adapter-side architecture and trust boundary live in [`../../aieng_freecad_mcp/docs/product_boundary.md`](../../aieng_freecad_mcp/docs/product_boundary.md), [`evidence_and_claim_policy.md`](../../aieng_freecad_mcp/docs/evidence_and_claim_policy.md), and [`agentic-cad-cae-blueprint.md`](../../aieng_freecad_mcp/docs/agentic-cad-cae-blueprint.md). Those documents remain authoritative. This file does not replace them.

---

## 1. Positioning

`.aieng` is an **AI-readable engineering context layer** for CAD/CAE agents.

- It helps agents understand CAD/CAE models by exposing features, editable parameters, protected regions, constraints, task intent, references, evidence, and trace.
- It can help agents propose more structured, bounded, reasonable CAD edits.
- It is **not** a CAD kernel.
- It is **not** a solver or mesher.
- It is **not** a CAD DSL or generative geometry runtime.
- It is **not** an autonomous agent or agent runtime.
- It must remain **backend-agnostic**. FreeCAD is one possible execution adapter, not the semantic model.

`.aieng` enhances agent understanding and auditability. It does not guarantee engineering correctness, manufacturability, simulation validity, or claim satisfaction.

---

## 2. GitHub-facing narrative

GitHub users discovering this project are unlikely to start by reading schemas, provenance contracts, or claim maps. They are more likely to understand the value through a **same-task, side-by-side comparison**.

The hook:

> **Better CAD agents start with better engineering context.**

The mechanism, in one paragraph:

> Without `.aieng`, agents tend to guess from raw geometry, filenames, or prose.
> With `.aieng`, agents can inspect features, editable parameters, protected regions, constraints, task intent, references, and prior evidence.
> The agent does not become an engineer. It stops guessing from a geometry blob.

What this is **not**:

- It is not a claim that agents now design safe parts.
- It is not a claim that `.aieng` validates engineering.
- It is not a claim that a better-looking artifact is a better design.

This is a demonstration of better engineering **context**, not automatic engineering **validation**.

---

## 3. Demonstration Direction

The active roadmap is product capability first: strengthen `.aieng` package quality, adapter interoperability, and explicit evidence/claim discipline.

Demonstrations remain important, but the preferred proof points are:

- real end-to-end runs,
- focused demo scripts,
- reproducible reports,
- short videos,
- bounded product demonstrations tied to actual workflows.

The earlier `aieng-gallery` repository idea is now **de-prioritized as a maintained roadmap direction**. Its lessons remain useful (clear side-by-side storytelling, explicit boundaries, and visible evidence-vs-claim discipline), but current direction does not depend on maintaining a separate gallery framework.

---

## 4. Relationship between repos and layers

```
aieng/                    semantic package format, schemas, core validation,
                          AI-readable engineering context

aieng_freecad_mcp/        one MCP adapter implementation
                          (FreeCAD / FreeCADCmd / CalculiX)

demo scripts / reports    optional demonstration assets,
videos                    not a required standalone product layer

aieng-cad-copilot/        agent workflow layer / Skill
   (future / Skill)       may use .aieng and adapters; not implemented
```

Dependency direction (read top-down only):

```
agent / Skill
    ↓
aieng_freecad_mcp  ───►  FreeCAD / FreeCADCmd / CalculiX
    ↓
aieng (semantic / evidence package format)
```

Rules:

- The adapter depends on the format. Not the reverse.
- A future Skill depends on the format and adapters; demonstration assets are optional.
- Adapter logic must not leak into `aieng/`.

---

## 5. Boundary and trust rules

These are restated from the existing architecture docs and remain non-negotiable for any public messaging or demo path:

- FreeCAD is one backend, not the semantic model.
- `.aieng` canonical schemas must not become FreeCAD-specific.
- Adapter-specific metadata belongs in **adapter-local provenance** or **demo scenario files**, not in required canonical schema fields.
- **Evidence** records what happened.
- **Trace** records tool execution.
- **Claims** require explicit claim update workflows (see [`evidence_and_claim_policy.md`](../../aieng_freecad_mcp/docs/evidence_and_claim_policy.md)).
- Evidence must not automatically become a claim.
- Demos must not imply automatic engineering validation.
- A better-looking or more complex generated model is not automatically a validated design.

---

## 6. Demonstration Scope Guidance

The archived gallery Milestone 0 spec remains available as a historical design record in [`aieng-gallery-milestone-0-spec.md`](aieng-gallery-milestone-0-spec.md), but it is not the active roadmap.

Scope:

- Keep demo scope tightly coupled to real product capability.
- Prefer demonstrations that execute real bounded flows through current adapters.
- Keep "Evidence ≠ claim" and explicit claim-update discipline visible in all demo outputs.
- Avoid adding standalone demo infrastructure as a near-term dependency.

Demonstration acceptance criteria should prioritize whether real end-to-end product behavior is understandable, reproducible, bounded, and honest about validation limits.

---

## 7. Risks

The biggest risks for this public-positioning direction are not technical — they are framing risks. They are listed here so anyone working on a gallery, demo, or copy update is aware:

- **Turning `.aieng` into a generative CAD DSL.** `.aieng` describes; it does not generate geometry. Resist any pressure to add `aieng generate <prose>` or equivalent.
- **Implying `.aieng` validates engineering safety.** It does not. Surface the disclaimer in every report, every screenshot, every README.
- **Making `.aieng` too FreeCAD-specific.** Demo fixtures must not put FreeCAD object names into required canonical fields. Adapter-local metadata stays adapter-local.
- **Making the demo too complex for GitHub users.** A 5-minute install/run barrier is the budget. No web app, no GPU, no API keys in the default path.
- **Hiding evidence/claim discipline behind visual polish.** The evidence/trace/`claims_advanced: false` banner is not optional decoration. It is the trust posture.
- **Moving adapter logic into `aieng/`.** All FreeCAD-specific paths, executable detection, FCStd handling, and FreeCAD Python snippets stay in the adapter.
- **Implementing a full Copilot Skill before core product capability is validated.** The Skill is a future workflow layer and should follow proven format+adapter capability.

---

## 8. Recommended wording

Short phrases suitable for a README, social post, or talk title:

- *Better CAD agents start with better engineering context.*
- *Make CAD models understandable to AI agents.*
- *Stop asking agents to guess from geometry blobs. Give them `.aieng`.*
- *`.aieng` does not make the agent an engineer. It gives the agent the engineering context it was missing.*
- *This demo produces evidence, not engineering validation.*
- *Evidence records what happened. Claims are explicit engineering assertions. The two are not the same.*

Use sparingly. Pair each headline with the qualifier in the same paragraph or screenshot — never the headline alone.

---

## See also

- [`core_position.md`](core_position.md) — the inward-facing positioning doc.
- [`../../Agent.md`](../../Agent.md) — workspace-level boundary rules.
- [`../../aieng_freecad_mcp/docs/product_boundary.md`](../../aieng_freecad_mcp/docs/product_boundary.md) — adapter-side product boundary.
- [`../../aieng_freecad_mcp/docs/evidence_and_claim_policy.md`](../../aieng_freecad_mcp/docs/evidence_and_claim_policy.md) — evidence / trace / claim discipline.
- [`../../aieng_freecad_mcp/docs/agentic-cad-cae-blueprint.md`](../../aieng_freecad_mcp/docs/agentic-cad-cae-blueprint.md) — long-term agent direction, including §14 cad-copilot Skill.
- [`../../aieng_freecad_mcp/docs/mvp-1-plan.md`](../../aieng_freecad_mcp/docs/mvp-1-plan.md) — current adapter MVP plan and multi-CAD boundary rules.
