# Archive Notice

**Status:** Archived — historical / experimental reference material  
**Moved from:** `CAD-Agent-main/` (root) → `archive/CAD-Agent-main/`  
**Date:** 2026-06-01

---

## What this is

This directory contains historical and experimental CAD-agent material originally
created as an auxiliary exploration of CadQuery-based agent workflows. It is
preserved for reference and to retain any reusable patterns, but it is **not**
part of the active runtime.

## What this is NOT

- **NOT** the active CAD/CAE execution runtime — use `aieng-ui/backend` for build123d/OCP execution
- **NOT** the core semantic library — use `aieng/` for `.aieng` package format, Shape IR, schemas, and validation
- **NOT** a development entry point for new features — do not add production code here
- **NOT** a maintained integration target — scripts and dependencies may be stale

## Guidance

- Do not develop new features in `archive/CAD-Agent-main/`.
- If you need to migrate useful logic from here, copy it to an active path
  (`aieng-ui/backend/`, `aieng/`, or `aieng-agent-skills/`) and adapt it to the
  current contracts.
- The README inside this directory remains unmodified (except for this notice)
  to preserve historical context.
