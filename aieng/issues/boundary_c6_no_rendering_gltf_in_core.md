---
title: "[Boundary C6] No visual rendering or glTF generation in .aieng core"
labels: ["boundary", "c6", "non-goal-v0.1"]
status: boundary-decision
---

## Decision

Rendered previews, screenshots, glTF generation, and mesh visualization are permanent non-goals for `.aieng` core.

## Rationale

1. Core scope is structured engineering state and evidence traceability.
2. Rendering pipelines add dependency and product-boundary risk.
3. External viewers/CAD tools should own visualization execution.

## Implication

Visual resources in core remain metadata/index scaffolds. Any future optional viewer must remain read-only and non-authoritative.
