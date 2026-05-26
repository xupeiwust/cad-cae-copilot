# Failure recovery

Two tiers. Handle them differently. Never silently retry across tiers.

## Tier 1 — plan failure

`aieng validate-plan` exits non-zero.

- Read the validator messages.
- If the issue is mechanically fixable (duplicate `step_id`, missing required parameter, unresolved `target`, family op slipped in), construct a corrected plan and re-validate. **Maximum one re-plan attempt per session.**
- Otherwise, surface the validator output and ask the user. Do not call `init-from-plan`.

## Tier 2 — backend failure

`aieng init-from-plan` produces `modeling_status: partial` or `failed`.

- The diagnostic package was still written. Open it.
- Read `validation/status.yaml.errors` and `provenance/tool_trace.jsonl`.
- Report which step(s) failed, whether any geometry was produced, and that the diagnostic package itself is the deliverable.

## Forbidden

- Silently switching `--backend freecad` to `--backend fake` and calling the result success. The two produce different deliverables; a `fake` STEP is a placeholder, not a fix.
- Editing files inside an already-produced `.aieng` package.
- Setting or implying `claims_advanced: true` anywhere.
- More than one re-plan attempt, or more than two `init-from-plan` runs in a session, without explicit user direction.

## Acceptable next steps

- Ask the user whether to retry with adjusted parameters.
- If the failure indicates the user actually wanted a different workflow (for example modifying an existing file), say so and hand off; do not paper over.
