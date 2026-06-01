# Legacy Notice

**Status:** Legacy — old FreeCAD MCP adapter / compatibility reference  
**Moved from:** `aieng-freecad-mcp/` (root) → `legacy/aieng-freecad-mcp/`  
**Date:** 2026-06-01

---

## What this is

This directory preserves the old FreeCAD MCP adapter implementation. It retains
future FreeCAD compatibility and reference value for anyone who needs to bridge
FreeCAD via the MCP protocol, but it is **no longer the default CAD/CAE execution
runtime** in this workspace.

## What this is NOT

- **NOT** the current default CAD/CAE execution runtime — the default is `aieng-ui/backend` using build123d/OCP
- **NOT** a place for new production features — do not add new capabilities here
- **NOT** guaranteed to be maintained in lock-step with the active backend
- **NOT** required for the standard build123d workflow

## Guidance

- Do not develop new features in `legacy/aieng-freecad-mcp/`.
- If you need FreeCAD-specific functionality, consider whether the active backend
  (`aieng-ui/backend`) already covers the use case via its provider registry.
- If you genuinely need to revive this adapter, fork or copy it to an active path
  and explicitly state the migration reason and target integration point.
- The original README and docs inside this directory remain unmodified (except
  for this notice) to preserve historical context.
