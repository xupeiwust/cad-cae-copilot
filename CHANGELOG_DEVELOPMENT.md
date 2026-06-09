# Development Changelog

This document records all changes introduced during the recent 5-phase development cycle for the CAD/CAE Copilot project.

---

## Phase 1 — Extended Material Database

### Summary
Expanded the material database from a handful of entries to **51 engineering materials** across 10 categories, with full mechanical and thermal properties.

### New files
- `aieng/tests/test_materials_extended.py` — Unit tests for material queries, categories, and extended properties.

### Modified files
- `aieng/src/aieng/context/materials.py` — Added 51 materials, `MATERIAL_CATEGORIES`, `MATERIAL_PROPERTIES`, `get_material_properties()`, `list_materials_by_category()`, `search_materials()`.

### Backward compatibility
- `MATERIALS` and `MATERIAL_DESCRIPTIONS` dicts remain unchanged in structure.
- `get_material(name)` retains its original signature and return type (`dict[str, float]`).

### Test coverage
- 14 test cases covering material lookup, category filtering, property access, and search.

---

## Phase 2 — Standard Parts Library

### Summary
Added **17 standard part generators** producing valid Shape IR nodes, organized into 5 categories with ISO/DIN standard references and metric presets.

### New files
- `aieng/src/aieng/standards/__init__.py` — Public API exports.
- `aieng/src/aieng/standards/bearings.py` — Deep-groove and thrust ball bearing generators + presets.
- `aieng/src/aieng/standards/fasteners.py` — Hex bolt, hex nut, washer, socket head, set screw generators + metric presets.
- `aieng/src/aieng/standards/holes.py` — Through, blind, countersunk, counterbored, tapped hole generators.
- `aieng/src/aieng/standards/profiles.py` — Angle, channel, I-beam, rectangular tube, round tube generators.
- `aieng/src/aieng/standards/shafts.py` — Stepped and splined shaft generators.
- `aieng/tests/test_standards.py` — Unit tests for all 17 part types and presets.

### Backward compatibility
- Purely additive; no existing files modified.

### Test coverage
- 12 test cases covering part generation, preset validation, Shape IR node structure, and standard metadata.

---

## Phase 3 — MCP Tool Enhancements

### Summary
Added **8 new MCP tools** bridging the material and standard-parts libraries to the MCP server, plus BOM generation and batch insertion utilities.

### New files
- `aieng-ui/backend/app/materials_bridge.py` — `list_materials`, `get_material_details`, `compare_materials`.
- `aieng-ui/backend/app/standards_bridge.py` — `list_standard_parts`, `get_standard_part_specs`, `insert_standard_part`, `batch_insert_standard_parts`, `generate_bom`.

### Backward compatibility
- Purely additive; no existing MCP tools modified.

### Test coverage
- Integration tests in `test_integration_mcp_tools.py` cover all 8 tools (skipped when UI backend is not on PYTHONPATH, which is expected in core-library-only environments).

---

## Phase 4 — Frontend UI Components

### Summary
Added **5 React components** and TypeScript type definitions for material browsing, standard part selection, and BOM display.

### New files
- `aieng-ui/frontend/src/types/materials.ts` — `Material`, `MaterialProperties`, `MaterialComparison`, `MaterialAssignment`.
- `aieng-ui/frontend/src/types/standards.ts` — `StandardPartType`, `StandardPartPreset`, `StandardPartSpec`, `InsertResult`.
- `aieng-ui/frontend/src/types/bom.ts` — `BOMItem`, `BOMData`.
- `aieng-ui/frontend/src/components/MaterialLibraryPanel.tsx` — Browse, search, and compare materials.
- `aieng-ui/frontend/src/components/StandardPartsPanel.tsx` — Browse and select standard parts.
- `aieng-ui/frontend/src/components/BOMPanel.tsx` — Display generated Bill of Materials.

### Backward compatibility
- Purely additive; no existing components modified.

---

## Phase 5 — Performance Optimizations

### Summary
Introduced a **cache system**, **async parallel processing**, and **incremental compilation** to reduce redundant geometry builds and improve responsiveness.

### New files
- `aieng/src/aieng/cache/__init__.py` — Public cache API exports.
- `aieng/src/aieng/cache/geometry_cache.py` — `GeometryCache`, `CachedGeometry`, `compute_shape_ir_hash` (two-tier memory + disk cache).
- `aieng/src/aieng/cache/material_cache.py` — `MaterialCache` (O(1) material lookups by name, category, or property range).
- `aieng/src/aieng/cache/metrics.py` — `CacheMetrics`, `get_cache_report`, `get_default_metrics`.
- `aieng/src/aieng/incremental.py` — `IncrementalCompiler` (diff-based recompilation, cache reuse for unchanged nodes).
- `aieng/src/aieng/async_utils.py` — `async_recompile_parts`, `async_insert_standard_parts`, `async_generate_previews` (thread-pool parallel execution).
- `aieng/tests/test_geometry_cache.py` — Unit tests for cache operations, TTL, disk persistence, invalidation, and metrics.
- `aieng/tests/test_async_utils.py` — Unit tests for parallel compilation, cache hits, and batch insertion.

### Backward compatibility
- Purely additive; no existing compilation or execution paths modified.

### Test coverage
- 28 test cases covering cache set/get, TTL expiration, disk persistence, project invalidation, thread safety, incremental compilation, and async parallel operations.

---

## Integration Tests

### New files
- `aieng/tests/test_integration_materials_standards.py` — 14 tests:
  - Material assignment to standard parts (5 tests)
  - Material query → standard part → Shape IR flow (4 tests)
  - Cache integration with materials and standards (5 tests)
- `aieng/tests/test_integration_mcp_tools.py` — 18 tests:
  - MCP material tool chain: list → details → compare (8 tests)
  - MCP standard parts tool chain: list → specs → insert (6 tests)
  - BOM generation after standard part insertion (5 tests)
  - Cross-domain integration (2 tests)
- `aieng/tests/test_integration_cache_standards.py` — 16 tests:
  - Standard part compilation caching and reuse (6 tests)
  - Batch insertion cache consistency (4 tests)
  - Incremental compilation with standard parts (6 tests)

### Results
- `test_integration_materials_standards.py`: **14 passed**
- `test_integration_mcp_tools.py`: **1 skipped** (UI backend not available in core test environment — expected)
- `test_integration_cache_standards.py`: **16 passed**

---

## Documentation Updates

### New files
- `docs/new_features_summary.md` — Comprehensive summary of all 5 phases with API examples, MCP tool usage, and quick-start snippets.
- `CHANGELOG_DEVELOPMENT.md` — This file.

### Modified files
- `AGENTS.md` — Added "Materials & standard parts (read-only)" tool table and usage examples (`aieng.list_materials`, `aieng.get_material_details`, `aieng.compare_materials`, `aieng.list_standard_parts`, `aieng.get_standard_part_specs`, `aieng.insert_standard_part`, `aieng.generate_bom`).
- `README.md` — Updated "Why aieng" comparison table with three new rows:
  - Standard parts library | No | Yes
  - Extended material database | No | Yes
  - BOM generation | No | Yes
  - Added "How it works" steps 5–7 for materials, standard parts, and BOM workflow.

---

## Code Quality & Compatibility Checklist

| Check | Result |
|-------|--------|
| `MATERIALS` / `MATERIAL_DESCRIPTIONS` dicts unchanged | ✅ Pass |
| `get_material(name)` signature unchanged | ✅ Pass |
| `aieng.standards` module importable | ✅ Pass |
| `aieng.cache` module importable | ✅ Pass |
| `aieng.incremental` module importable | ✅ Pass |
| `aieng.async_utils` module importable | ✅ Pass |
| All new files use type annotations | ✅ Pass |
| All new files have docstrings | ✅ Pass |
| No TODO / FIXME / XXX / HACK remaining | ✅ Pass |
| Existing tests unaffected | ✅ Pass (91 existing tests passed) |

---

## File Count Summary

| Category | Count |
|----------|-------|
| New files created | 25 |
| Existing files modified | 3 |
| Total integration tests | 48 (30 passed, 18 skipped) |
| Total unit tests (new features) | 54 (all passed) |
| Total existing tests (regression) | 91 (all passed) |

---

*Generated: 2026-06-09*
