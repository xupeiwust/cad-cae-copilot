# Backend selection

## Available in Phase 1

- `fake` — pure Python, no FreeCAD, generates a placeholder STEP. Deterministic. `fake` does not produce real CAD geometry. Use for CI, dry-runs, and package-skeleton inspection only.
- `freecad` — real OpenCASCADE geometry via FreeCADCmd subprocess. Requires a FreeCAD installation reachable through `FREECAD_MCP_FREECAD_PATH`, `FREECAD_HOME`, or PATH.

`freecad` is the reference backend for Phase 1. It is **not** the architecture boundary; future backends register through the `aieng.backends` entry-point group.

## Decision tree

1. Real STEP / real CAD geometry requested → prefer `freecad` or another real backend.
2. No real backend available and user requested real geometry → do not automatically fall back to `fake`. Explain the unavailability. Offer the user two options: (a) run with `fake` to produce a package skeleton / placeholder artifact, or (b) configure or select a real backend and retry.
3. CI / dry run / package-skeleton inspection → `fake`, labeled clearly in the response.
4. Default: ask the user once, then prefer `freecad`.

## Pre-checks before `freecad`

- Confirm FreeCAD is reachable. If not, do not automatically fall back to `fake`. Explain that FreeCAD is unavailable, then offer two options:
  1. Run with `fake` to produce a package skeleton / placeholder artifact.
  2. Configure or select a real backend and retry.
- Use `fake` only when the user explicitly accepts a skeleton, when the task is a dry run, or when running in CI / sandbox.
- Do not present a `fake` STEP as real geometry. Label it as a placeholder in every response where it appears.

## MCP and transport

MCP (for example `aieng_freecad_mcp`) is one possible transport for a backend; it is not an architecture boundary. The skill addresses backends by their `backend_id` ( `fake`, `freecad`, …) — not by transport. Future backends may run in-process, via subprocess, via MCP, or via remote APIs.

## Future backends

Discovered via `aieng.backends` entry points and the dotted-path fallback. Do not hardcode a list. If an unknown `backend_id` is passed, the CLI surfaces the error; relay it to the user and ask for a supported id.
