---
name: superpowers
description: "Use when user asks for superpowers, fast project acceleration, plan-first execution, parallelized implementation, or high-velocity delivery with strong verification. Triggers on: superpowers, accelerate, optimize workflow, move faster, spec then execute, rapid iteration, parallel tasks, strict verify-before-done."
---

# Superpowers Skill (Workspace)

## Purpose

Provide a fast, disciplined development workflow for this repository:

1. Clarify target outcome and constraints.
2. Convert intent into short executable slices.
3. Implement with minimal blast radius.
4. Verify with focused tests first, then broader regression when needed.
5. Ship incremental commits quickly.

## Activation Hints

Use this skill when the user requests speed, acceleration, optimization, or asks to execute a multi-step roadmap quickly and safely.

## Workflow

### 1) Clarify and lock scope

- Restate the concrete deliverable in one sentence.
- Identify non-goals and trust boundaries already enforced by the project.
- Prefer one smallest useful slice before broader refactors.

### 2) Plan as small slices

- Break work into 2-5 short tasks.
- Each task must define:
  - files to touch
  - expected behavior change
  - validation command
  - done condition

### 3) Execute with minimal edits

- Prefer deterministic code paths over broad abstractions.
- Avoid changing unrelated APIs.
- Keep evidence-only and explicit-missingness policies intact.

### 4) Verify before claiming done

- Run narrow tests covering changed behavior.
- Run nearby regression tests affected by touched files.
- If tests fail, fix root cause before proceeding.

### 5) Ship in tight increments

- Commit each completed slice with a specific message.
- Push after green verification.
- Report delta only: what changed, how verified, what is next.

## Repository-specific guardrails

- Never auto-advance claims from imported artifacts.
- Never infer missing CAD/CAE facts from absent data.
- Keep external tool execution boundaries explicit.
- Preserve deterministic validator behavior.

## Output style

- Lead with outcome and status.
- Provide concise evidence of verification.
- Propose next smallest slice immediately.
