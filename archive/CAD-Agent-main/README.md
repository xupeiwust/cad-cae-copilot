> **ARCHIVED** — This directory is historical/experimental auxiliary CAD-agent material.
> It is NOT the active runtime, NOT the core semantic library, and NOT a development
> entry point for new features. See `ARCHIVE_NOTICE.md` for details.

# CAD-Agent Skills

CAD-Agent Skills is a portable skill/workflow package for generating CadQuery CAD models through an evidence-driven CAD compiler workflow. It can be used by Cursor agents or by other coding agents that can read the skill documents, run Python scripts, inspect generated files, and follow the required review gates.

The skill is designed for procedural CAD tasks that need more than a one-shot script: complex geometry, industrial design surfaces, iterative repair, validation artifacts, visual review, and final STEP/STL export.

## What It Provides

- A CadQuery-first modeling workflow using `import cadquery as cq`.
- Adaptive iteration planning before implementation.
- Feature decomposition, dependency tracking, and feature memory.
- Geometry validation through bounding boxes, volumes, shape validity, and CAD references.
- Mandatory visual review after each iteration, **performed by the agent** when it can read screenshots (multimodal); otherwise document fallback and do not fake inspection.
- Reference acquisition, object-agnostic checklists, and functional plausibility audits for any function-bearing or reference-driven model.
- Source-first repair rules for failed booleans, invalid shapes, bad proportions, and visible defects.
- Final STEP/STL export only after review evidence supports an `export_ready` decision.

## Repository Layout

```text
CAD-Agent-Skills/
  SKILL.md                     Main skill prompt and operating contract
  pipeline-contract.md         Required iteration artifacts and review gates
  cad-patterns.md              CadQuery helper patterns for generated scripts
  geometry-brain.md            Geometry facts, CAD references, and review loop
  rendering.md                 Screenshot rendering priority and fallback rules
  visual-review.md             Visual inspection requirements
  visual-defects.md            Hard-fail visual defect checklist
  reference-acquisition.md     Reference sourcing and reference_limited state
  object-agnostic-checklists.md Dimension-based checklist generation
  functional-defects.md        Functional hard-fail checklist for function-bearing models
  visual-review-template.html  HTML review template with Three.js viewer
  benchmarks.md                Quality and evaluation references
```

Generated modeling work should treat the workspace root as the modeling root:

```text
scripts/              Iteration scripts
exports/pipeline/     Iteration artifacts, review reports, screenshots
exports/              Final STEP/STL exports
```

## Requirements

Use Python 3.10 or newer. Install the recommended Python dependencies with:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Verify CadQuery availability:

```powershell
python -c "import cadquery as cq; print(cq.__version__)"
```

Verify the preferred offscreen screenshot renderer:

```powershell
python -c "import pyvista, vtk; print('pyvista renderer ok')"
```

### Agent Requirements

This workflow requires a multimodal large language model for production use. The agent must be able to directly inspect generated PNG screenshots such as `front.png`, `side.png`, `top.png`, and `iso.png` before writing visual findings or deciding that a model is export-ready.

A text-only agent may still read the documents, generate CadQuery scripts, and produce geometry facts, but it cannot complete the mandatory visual review gate unless a human or another multimodal reviewer inspects the rendered images and records the findings.

## Installing In AI Coding Agents

This package is intentionally plain text and portable. Any agent can use it if it can access the files and is instructed to read `CAD-Agent-Skills/SKILL.md` before starting CAD work.

Recommended setup:

- Cursor: copy `CAD-Agent-Skills/` to `.cursor/skills/cadquery-modeling/` in the target project or user skills location. The folder name should match the skill name in `SKILL.md`, and `visual-review-template.html` should stay in the same folder.
- Claude Code: keep this repository or the `CAD-Agent-Skills/` folder in the project, then add a short instruction in `CLAUDE.md` telling Claude to read `CAD-Agent-Skills/SKILL.md` for CadQuery, CAD, STEP, STL, or visual-review tasks.
- Codex: keep this repository or the `CAD-Agent-Skills/` folder in the project, then reference `CAD-Agent-Skills/SKILL.md` from `AGENTS.md` so Codex loads the workflow before CAD-related tasks.
- Other agents: place the folder wherever the agent stores reusable instructions, then point the agent to `SKILL.md` as the entry file.

You can also ask the AI agent to install the skill itself. Example prompt:

```text
Install the CAD-Agent Skills workflow for this project.

Use https://github.com/fhwangyinan/CAD-Agent as the source. Add the CAD-Agent-Skills folder to this project's reusable AI instructions or skills location. If this is Cursor, prefer .cursor/skills/cadquery-modeling/. If this is Claude Code, reference CAD-Agent-Skills/SKILL.md from CLAUDE.md. If this is Codex, reference CAD-Agent-Skills/SKILL.md from AGENTS.md.

Do not install Python dependencies without asking first. After installing, read CAD-Agent-Skills/SKILL.md and summarize when the workflow should be activated.
```

## Usage

Start with `CAD-Agent-Skills/SKILL.md`. For a new modeling request, the agent should:

1. Understand the requested geometry and identify uncertain dimensions.
2. Produce a modeling plan and wait for approval before writing code. The plan must include a **Skill Constraint Handoff** listing the skill/reference files read, applicable modes, non-negotiable gates, and first iteration scope contract.
3. For each iteration: generate one **single-focus** CadQuery script with **primary scope** and **out of scope** declared at the top (see `SKILL.md`, *Single-focus iteration discipline*). The matching `iteration_plan.json` must list `skill_constraints_handoff`, `in_scope`, `out_of_scope`, and `deferred_features`.
4. For visible or reference-driven models, write `reference_sources.json`, `reference_visual_checklist.json`, and `object_agnostic_checklist.json`; if physical function matters, also write `reference_measurements.json` and `required_functional_features.json`.
5. Before each iteration script, write `phase_gate.json` and `preflight_review.md`; after modeling, write `gate_results.json` before `review_report.md`.
6. Export that iteration’s STEP/STL and write the full pipeline artifact set (including `geometry_facts.json`, `cad_refs.json`, review HTML, and review markdown).
7. **Agent self-review:** complete the review gate yourself—generate or attempt screenshots, inspect `front`/`side`/`top`/`iso` PNGs when they exist, run the hard-fail visual defect audit, run the functional audit when applicable, and write evidence-backed `geometry_review.md`, `functional_review.md`, and `review_report.md`.
8. Choose the next action from review evidence; if the model is not `export_ready`, continue with the **next** single-focus iteration **without** pausing for human approval between iterations (unless the user asked for manual step approval).
9. Export final STEP/STL under `exports/` only after the review gate supports `export_ready`.

## Important Rules

- Do not use FreeCAD executables, FreeCAD Python modules, GUI modeling, `.FCStd`, PartDesign, or Sketcher workflows.
- Do not silently install missing dependencies during a modeling task; ask before modifying the environment.
- Do not implement from a plan that lacks the Skill Constraint Handoff; reread the skill files and regenerate the plan first.
- Do not replace the iterative artifact chain with a single monolithic `create_model.py` script for complex models.
- Do not collapse multiple major modeling stages into one `iteration_<nn>_*.py`.
- Do not let one iteration produce the complete requested model before `export_ready`; if it does, mark scope compliance as failed and split the work.
- Do not claim screenshot inspection unless the image files were actually generated and inspected.
- Do not treat functional features as cosmetic details; required moving axes, clearances, load paths, scale ratios, and service interfaces must pass the functional audit before `export_ready`.
- Do not mark a model `export_ready` while unresolved hard-fail visual defects, functional defects, reference limitations, required object-agnostic dimensions, high primitive-stack risk, or required `fail`/`partial`/`unknown` gate results remain.

## Key References

- Main skill contract: [`CAD-Agent-Skills/SKILL.md`](CAD-Agent-Skills/SKILL.md)
- Iteration artifact contract: [`CAD-Agent-Skills/pipeline-contract.md`](CAD-Agent-Skills/pipeline-contract.md)
- CadQuery script patterns: [`CAD-Agent-Skills/cad-patterns.md`](CAD-Agent-Skills/cad-patterns.md)
- Reference acquisition rules: [`CAD-Agent-Skills/reference-acquisition.md`](CAD-Agent-Skills/reference-acquisition.md)
- Object-agnostic checklist rules: [`CAD-Agent-Skills/object-agnostic-checklists.md`](CAD-Agent-Skills/object-agnostic-checklists.md)
- Rendering rules: [`CAD-Agent-Skills/rendering.md`](CAD-Agent-Skills/rendering.md)
- Visual review rules: [`CAD-Agent-Skills/visual-review.md`](CAD-Agent-Skills/visual-review.md)
- Functional defect rules: [`CAD-Agent-Skills/functional-defects.md`](CAD-Agent-Skills/functional-defects.md)
