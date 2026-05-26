---
title: "[Boundary C5] No arbitrary STEP/B-rep direct editing in .aieng core"
labels: ["boundary", "c5", "non-goal-v0.1"]
status: boundary-decision
---

## Decision

Arbitrary STEP/B-rep direct geometry editing is a permanent boundary decision for `.aieng` core.

## Rationale

1. `.aieng` is a semantic/evidence layer, not a CAD kernel.
2. Geometry editing is executed by external CAD tools or explicit regeneration-backed adapters.
3. Keeping this boundary preserves auditability, determinism, and tool-responsibility clarity.

## Implication

Feature work should target structured semantic proposals and guarded regeneration paths, not unrestricted B-rep mutation.
