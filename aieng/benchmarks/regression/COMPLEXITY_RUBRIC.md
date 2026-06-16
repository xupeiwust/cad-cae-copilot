# CAD complexity rubric

The original CAD-create prompts (001–005) top out at a 3-part mini assembly. That
is not enough to exercise the Agent-facing modeling layer where the real gap lives:
**decomposition, sub-assembly planning, and intermediate verification** of models
an agent cannot hold correctly in one shot. This rubric defines "complex" so the
gap is measurable, and the `complex`-tagged prompts (023+) are the moving target.

## Why a separate tier

A model is *complex* (for this workbench) when a single hand-written
`cad.execute_build123d` script is likely to be wrong on the first try, so the
agent needs to **build it in verified sub-steps** rather than one shot. That
happens when several of the dimensions below stack up — not from raw triangle
count.

## Complexity dimensions (score each model)

| Dimension | Signal |
|-----------|--------|
| `part_count` | number of distinct named parts (`.label` + `Compound` children) |
| `feature_kinds` | distinct operations used: `loft` / `revolve` / `sweep` / `fillet` / `shell` / `subtract` / `pattern` |
| `mates` | inter-part relationships that must hold: shaft-in-bore, gear-on-shaft, gear-mesh center distance, bolted interface, concentric, coaxial |
| `kinematic` | the model is a chain of links joined by joints (revolute / prismatic) — pose must be coherent |
| `internal_features` | bores, pockets, counterbores, threads-as-clearance not visible in the silhouette |
| `symmetry` | mirror pairs (left/right links, opposed bearings) that must stay symmetric |

## Tiers

- **simple** — 1–2 parts, primitives only, ≤2 `feature_kinds`. (001–004)
- **moderate** — 3–5 parts, ≤3 `feature_kinds`, ≤2 mates, no kinematic chain. (005)
- **complex** — **any** of: `part_count ≥ 6`, a kinematic chain, `mates ≥ 3`,
  or `feature_kinds ≥ 4` combined with internal features. (023+)

## How to score a complex run

These prompts are executed by an external agent through MCP (see
`AGENT_BENCHMARK_RUNBOOK.md`), then `record.py` captures the outcome. For complex
prompts, score against the **acceptance signals** listed in each prompt file:

1. **Built at all** — `status` reached `viewer_ready_glb` without an unrecovered
   build error (`pass` / `fail`).
2. **Part completeness** — every named part in the prompt is present in
   `named_parts` (record as `part_count` + the missing set).
3. **Structural sanity** — `geometry_report`: `floating_parts == []` and required
   symmetry pairs are `ok` (mates that the geometry report can see).
4. **Dimensional spot-checks** — the explicit key dimensions in the prompt are
   within ±2% (record under `metrics`).
5. **Process used** — whether the agent decomposed + verified sub-parts
   (`cad.validate_subpart` / incremental `replace_part`) or one-shot wrote the
   whole script. This is the signal the validate-loop work is meant to move.

Record `mates` and `kinematic` coherence qualitatively until a deterministic
assembly check exists — that gap is exactly what the assembly-authoring slice
(`cad.define_part` / `cad.define_mate` on the existing Assembly IR) will close.

Honesty boundary: passing this rubric means "the agent produced a structurally
coherent, dimensionally close model," **not** that the assembly is
manufacturable, kinematically valid, or certified.
