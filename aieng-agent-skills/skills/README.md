# skills/

Agent behavior skills for the `.aieng` ecosystem, housed in the `aieng-agent-skills` repository.

## What this directory is

These skills are **not** part of the `aieng` runtime Python package and are **not** part of `aieng_freecad_mcp`. They are agent-facing behavior contracts: SKILL.md files plus reference notes that tell an agent how to use the existing CLI and packages correctly.

Skills in this directory:

- Reference `aieng/` (format, CLI) and `aieng_freecad_mcp/` (FreeCAD backend) without belonging to either.
- Version independently from both the `aieng` package and the `aieng_freecad_mcp` adapter.
- Live in this repository (`aieng-agent-skills/`) so they can be released and distributed separately.
- Use `engineering_skill_contracts.json` as the machine-readable contract index
  for repeatable CAD/CAE loops. The JSON catalog defines required evidence,
  allowed tools, refusal conditions, approval requirements, outputs, and a
  dogfood scenario for each contracted workflow.

## Placement

- `skills/` lives inside the `aieng-agent-skills` repository — the dedicated home for agent behavior skills.
- Generated `.aieng` outputs should not be committed here. Write them to a project-local path or the workspace-level `dist/` directory.

## Skills

- **aieng-cad-authoring/** — Create a new CAD part from natural-language intent through the `.aieng` Phase 1 authoring pipeline (`aieng plan` → `aieng validate-plan` → `aieng init-from-plan`).
- **aieng-cad-cae-copilot/** — Evidence-first CAE workflow skill prototype for inspect → setup patch → preflight → approval-gated solver run → FRD extraction → refreshed summary reporting.
  Validation note: `skills/aieng-cad-cae-copilot/validation.md`.
- **aieng-closed-loop-copilot/** — Closes the loop on top of `aieng-cad-cae-copilot`: recommend ranked CAD modifications (Phase 36) → verify them through the pre-execution gate (Phase 37) → apply the surviving proposal via `cad.edit_parameter` → re-simulate → compare against design targets. Bounded iteration budget; trust-layer-gated; no auto-approval.
- **engineering_skill_contracts.json** — Contract catalog for the initial product
  loop skills: `cae-preflight`, `design-target-review`,
  `cad-mod-propose-verify`, `solver-run-orchestrate`, and
  `evidence-report-synthesize`.

## Versioning

Each skill carries its own `skill_version` inside `SKILL.md`. Skills declare the minimum `aieng` CLI version they target in `references/workflow.md`.

## Adding a new skill

1. Create `skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter only.
2. Add `references/` with short, action-oriented notes loaded only when applicable.
3. Add `agents/openai.yaml` if OpenAI-compatible runtime metadata is needed.
4. Do not add `scripts/` or `assets/` unless deterministic helpers are genuinely required.

## Out of scope for this directory

- CAD/CAE execution logic (lives in `aieng_freecad_mcp/`).
- `.aieng` schema and validation (lives in `aieng/`).
- Engineering claim advancement. Skills must not advance claims.

---

## Skill handoff notes

### aieng-cad-authoring

**Purpose:** Guides an agent through the `.aieng` Phase 1 create-new CAD authoring workflow — from natural-language intent to a validated, audit-grade `.aieng` package. Covers decision, clarification, planning, validation, backend selection, execution, package interpretation, and response formatting. Not a backend, not an MCP server, not a CAD code generator.

**Source (editable):**

```text
skills/aieng-cad-authoring/
  SKILL.md
  agents/openai.yaml
  references/
    workflow.md
    decision-policy.md
    clarification-policy.md
    modeling-plan-rules.md
    evidence-claim-policy.md
    backend-policy.md
    failure-recovery.md
    output-format.md
```

**Packaged artifact:**

```text
dist/skill.zip
```

The archive must be named exactly `skill.zip` when uploading. It contains the skill contents under a top-level `aieng-cad-authoring/` folder (10 files, ~11 KB).

**Notes:**

- `skills/aieng-cad-authoring/` is the editable source of truth. Edit here, then repackage.
- `dist/skill.zip` is the upload artifact only. Do not edit inside the archive.
- Do not commit generated `.aieng` packages into `skills/`.
- Do not commit temporary `modeling_plan.json` files into `skills/`.
