# aieng-agent-skills

Agent behavior skills for the `.aieng` ecosystem. These are SKILL.md-based behavior contracts that tell an AI agent how to use the `.aieng` CLI and packages correctly. They are not execution code, not backends, and not part of the `aieng` runtime package.

## Repository structure

```text
skills/
  README.md                    — skill index and handoff notes
  engineering_skill_contracts.json
                               — machine-readable CAD/CAE loop contracts
  aieng-cad-authoring/         — Phase 1 create-new CAD authoring skill
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

## Related repositories

- `aieng/` — `.aieng` package format, schemas, CLI, orchestrator.
- `aieng_freecad_mcp/` — FreeCAD backend adapter and MCP server.

Skills reference both but belong to neither. They version independently from both.

See `skills/README.md` for full per-skill handoff notes.
