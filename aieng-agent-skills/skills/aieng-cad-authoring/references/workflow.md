# Canonical workflow

This workflow runs only when the agent or user selects it. The authoring pipeline is an agent/user/CLI-selected workflow for create-new CAD tasks; it does not auto-trigger for arbitrary CAD/CAE requests. The decision rules in `decision-policy.md` gate entry.

## Preconditions

- `aieng` CLI is on PATH. Verify with `aieng --version`.
- Working directory is the user's project, not the skill directory.
- The intent contains at least a shape concept the planner can map to Phase 1 primitives.
- If dimensions are missing, allow planner defaults only when the resulting assumptions are recorded and surfaced to the user.

## Commands

1. **Plan**

   ```bash
   aieng plan --intent "<intent>" --out modeling_plan.json
   ```

   Inspect `intent`, `units`, `assumptions[]`, `missing_information[]`, `steps[]`, `checks[]`.

2. **Validate**

   ```bash
   aieng validate-plan modeling_plan.json
   ```

   Exit 0 → proceed. Non-zero → see `failure-recovery.md`. Do not call `init-from-plan` on a failing plan.

3. **Execute**

   ```bash
   aieng init-from-plan modeling_plan.json --out generated.aieng --backend <backend>
   ```

   Backend choice per `backend-policy.md`. After plan validation and backend capability checks pass, `init-from-plan` writes a `.aieng` package for backend `success`, `partial`, and `failed` execution states; the `partial` / `failed` package is a diagnostic package. Plan validation failure or backend capability failure does not produce a package.

## Package map

| Path | Role |
|---|---|
| `validation/status.yaml` | `modeling_status`, `geometry_available`, errors, warnings |
| `authoring/modeling_plan.json` | Frozen intent |
| `authoring/construction_history.json` | Actual ops with `backend_metadata` |
| `provenance/tool_trace.jsonl` | Raw event log; read on failure |
| `results/evidence_index.json` | Stable evidence handles |
| `geometry/source.step` | Present only when `geometry_available: true` |
| `geometry/normalized.step` | Phase 1: byte-for-byte copy of `source.step` |
| `geometry/topology_map.json` | Present when post-processing ran |
| `graph/aag.json` | Present when post-processing ran |
| `graph/feature_graph.json` | Present when post-processing ran |

## Post-processing

Semantic post-processing is implemented in the current Phase 1 pipeline. `aieng init-from-plan` runs post-processing **by default** after successful backend execution and geometry artifact creation.

Successful post-processing may generate:

- `geometry/topology_map.json`
- `graph/aag.json`
- `graph/feature_graph.json`
- updated `validation/status.yaml`

### Disable post-processing

```bash
aieng init-from-plan modeling_plan.json --out generated.aieng --backend freecad --no-postprocess
```

Use when only the base package is needed (CI smoke tests, fast iteration, debugging the backend layer).

### Strict mode

```bash
aieng init-from-plan modeling_plan.json --out generated.aieng --backend freecad --postprocess-strict
```

Use when post-processing failure should be treated as a hard error rather than a non-fatal warning.

## Required CLI capabilities

The skill requires an `aieng` CLI build that supports:

- `aieng plan`
- `aieng validate-plan`
- `aieng init-from-plan`
- `init-from-plan --no-postprocess`
- `init-from-plan --postprocess-strict`

If any of those capabilities is missing, warn the user and stop. Skill changes should not require a CLI release; CLI changes should not silently break the skill.
