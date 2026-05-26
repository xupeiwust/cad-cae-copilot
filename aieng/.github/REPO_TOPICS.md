# GitHub Repo Topics (for discoverability)

GitHub repository **topics** are surfaced in search, in the repo card, and in
GitHub's "Explore" page. They are configured in the repo's **Settings → About →
Topics** field (not in any tracked file). This file documents the topics this
repo intentionally claims so a maintainer can keep the settings in sync.

## Suggested topics for `armpro24-blip/aieng`

Paste this comma-separated list into the GitHub topics input
(GitHub stores them lowercase, hyphenated, no spaces):

```
cad, cae, fea, engineering, ai, llm, agent, mcp, model-context-protocol,
step, calculix, freecad, evidence-layer, semantic, package-format,
ai-readable, design-automation, fem, agi, claude, anthropic
```

Up to 20 topics are allowed per repository. The list above is exactly 21 —
drop one (probably `fem` since `fea` covers it) when entering into GitHub's
input.

## Suggested GitHub repository description

Replace the existing description (Settings → About → Description) with:

```
AI-readable engineering context package format for CAD/CAE agents. Converts STEP / CalculiX / FreeCAD artifacts into structured, auditable, evidence-tracked packages so LLM agents can reason over engineering state honestly.
```

## Suggested website field

If the repo has a documentation site, put it here. Otherwise leave blank or
point at the workspace docs:

```
https://github.com/armpro24-blip/aieng/tree/main/docs
```

## Why these topics

- `cad`, `cae`, `fea`, `fem`, `engineering` — discovered by engineers searching
  for CAD/CAE tooling.
- `ai`, `llm`, `agent`, `mcp`, `model-context-protocol`, `claude`, `anthropic` —
  discovered by the AI/agent-tooling community.
- `step`, `calculix`, `freecad` — discovered by users searching for specific
  format/solver/tool integrations.
- `evidence-layer`, `semantic`, `package-format`, `ai-readable` — the project's
  distinctive positioning vocabulary.
- `design-automation`, `agi` — adjacent discovery vectors.

## Updating these topics

When the project pivots or adds capabilities, update this file *and* the
GitHub repo settings together. The settings are the source of truth; this
file is a maintenance record.
