"""Asynchronous parallel processing utilities for geometry operations.

Provides concurrent compilation, standard-part insertion, and preview generation
with controlled worker pools and graceful error handling.
"""
from __future__ import annotations

import concurrent.futures
import time
from typing import Any

from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
from aieng.cache.metrics import get_default_metrics


def async_recompile_parts(
    parts: list[dict[str, Any]],
    *,
    max_workers: int = 4,
    cache: GeometryCache | None = None,
    timeout_per_part: int = 120,
) -> list[dict[str, Any]]:
    """Recompile multiple Shape IR parts in parallel.

    Args:
        parts: List of Shape IR payload dicts (one per part).
        max_workers: Maximum concurrent compilation workers.
        cache: Optional ``GeometryCache`` to check before compiling.
        timeout_per_part: Seconds allowed per part compilation.

    Returns:
        A list of result dicts in the same order as ``parts``.
        Each result has keys: ``status``, ``hash``, ``cached``, ``result`` or ``error``.
    """
    metrics = get_default_metrics()
    cache = cache or GeometryCache()

    def _compile_one(idx: int, payload: dict[str, Any]) -> dict[str, Any]:
        h = compute_shape_ir_hash(payload)
        # Check cache
        cached = cache.get(h)
        if cached is not None:
            metrics.record_hit()
            return {
                "index": idx,
                "status": "ok",
                "hash": h,
                "cached": True,
                "result": cached,
            }
        metrics.record_miss()
        start = time.monotonic()
        try:
            # Compile via the shape_ir converter
            from aieng.converters.shape_ir import compile_shape_ir

            compiled = compile_shape_ir(payload)
            duration = time.monotonic() - start
            metrics.record_compile(duration)

            # Build a minimal CachedGeometry (caller may enrich with STEP/topo later)
            cg = CachedGeometry(
                shape_ir_hash=h,
                metadata={
                    "representation": compiled.get("representation"),
                    "runtime": compiled.get("runtime"),
                    "source": compiled.get("source"),
                    "source_path": compiled.get("source_path"),
                },
            )
            cache.set(h, cg)
            metrics.record_set()
            return {
                "index": idx,
                "status": "ok",
                "hash": h,
                "cached": False,
                "result": cg,
                "compile_time_s": round(duration, 3),
            }
        except Exception as exc:
            metrics.record_error()
            return {
                "index": idx,
                "status": "error",
                "hash": h,
                "cached": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    results: list[dict[str, Any]] = [None] * len(parts)  # type: ignore[list-item]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_compile_one, i, p): i for i, p in enumerate(parts)
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result(timeout=timeout_per_part)
                results[res["index"]] = res
            except Exception as exc:
                idx = futures[future]
                results[idx] = {
                    "index": idx,
                    "status": "error",
                    "error": f"Thread execution failed: {exc}",
                }

    return results


def async_insert_standard_parts(
    project_id: str,
    parts: list[dict[str, Any]],
    *,
    max_workers: int = 4,
    active_settings: Any | None = None,
    cache: GeometryCache | None = None,
) -> list[dict[str, Any]]:
    """Batch-insert standard parts into a project in parallel.

    Args:
        project_id: Target project identifier.
        parts: List of standard-part request dicts. Each dict should contain:
            ``part_type``, ``parameters``, optional ``position``,
            ``orientation``, ``part_name``, ``preset_name``.
        max_workers: Maximum concurrent insertion workers.
        active_settings: Backend settings object (passed to ``insert_standard_part``).
        cache: Optional ``GeometryCache`` for recompilation caching.

    Returns:
        A list of result dicts in the same order as ``parts``.
    """
    if not parts:
        return []

    # Import here to avoid circular dependencies at module load time
    try:
        from aieng_ui.backend.app.standards_bridge import insert_standard_part
    except ImportError:
        # Fallback for when the UI backend is not on PYTHONPATH
        try:
            from aieng.standards_bridge import insert_standard_part  # type: ignore[import-not-found]
        except ImportError:
            # Final fallback: return errors for all parts when the bridge is unavailable
            return [
                {
                    "index": i,
                    "status": "error",
                    "error": "standards_bridge not available in this environment",
                }
                for i in range(len(parts))
            ]

    metrics = get_default_metrics()
    cache = cache or GeometryCache()
    results: list[dict[str, Any]] = [None] * len(parts)  # type: ignore[list-item]

    def _insert_one(idx: int, req: dict[str, Any]) -> dict[str, Any]:
        start = time.monotonic()
        try:
            result = insert_standard_part(
                active_settings=active_settings,
                project_id=project_id,
                package_path=None,
                part_type=req["part_type"],
                parameters=req.get("parameters", {}),
                position=req.get("position"),
                orientation=req.get("orientation"),
                part_name=req.get("part_name"),
                preset_name=req.get("preset_name"),
            )
            duration = time.monotonic() - start
            metrics.record_compile(duration)
            return {"index": idx, "status": "ok", "result": result, "duration_s": round(duration, 3)}
        except Exception as exc:
            metrics.record_error()
            return {"index": idx, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_insert_one, i, p): i for i, p in enumerate(parts)}
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                results[res["index"]] = res
            except Exception as exc:
                idx = futures[future]
                results[idx] = {"index": idx, "status": "error", "error": f"Thread failed: {exc}"}

    return results


def async_generate_previews(
    project_ids: list[str],
    *,
    max_workers: int = 4,
    active_settings: Any | None = None,
    size: int = 480,
) -> list[dict[str, Any]]:
    """Generate thumbnail previews for multiple projects in parallel.

    Args:
        project_ids: List of project identifiers.
        max_workers: Maximum concurrent preview workers.
        active_settings: Backend settings object.
        size: Thumbnail size in pixels.

    Returns:
        A list of result dicts in the same order as ``project_ids``.
    """
    try:
        from aieng_ui.backend.app.cad_generation import render_mesh_thumbnail
    except ImportError:
        from aieng.cache.geometry_cache import GeometryCache
        render_mesh_thumbnail = None  # type: ignore[assignment]

    results: list[dict[str, Any]] = [None] * len(project_ids)  # type: ignore[list-item]

    def _generate_one(idx: int, pid: str) -> dict[str, Any]:
        try:
            # Attempt to read the project's STL and render a thumbnail
            # This is a best-effort operation; failures are non-fatal
            if render_mesh_thumbnail is None:
                return {"index": idx, "status": "skipped", "reason": "thumbnail renderer unavailable"}

            # Resolve project path via project_io if available
            stl_bytes = b""
            try:
                from aieng_ui.backend.app.project_io import get_project, resolve_project_path

                project = get_project(active_settings, pid)
                pkg = resolve_project_path(active_settings, pid, project.get("aieng_file"))
                if pkg and pkg.exists():
                    import zipfile

                    with zipfile.ZipFile(pkg, "r") as zf:
                        if "geometry/preview.stl" in zf.namelist():
                            stl_bytes = zf.read("geometry/preview.stl")
            except Exception:
                pass

            if not stl_bytes:
                return {"index": idx, "status": "skipped", "reason": "no STL preview available"}

            thumbnail_b64 = render_mesh_thumbnail(stl_bytes, size=size)
            return {
                "index": idx,
                "status": "ok",
                "project_id": pid,
                "thumbnail_base64": thumbnail_b64,
                "size": size,
            }
        except Exception as exc:
            return {"index": idx, "status": "error", "project_id": pid, "error": f"{type(exc).__name__}: {exc}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_generate_one, i, pid): i for i, pid in enumerate(project_ids)}
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                results[res["index"]] = res
            except Exception as exc:
                idx = futures[future]
                results[idx] = {"index": idx, "status": "error", "error": f"Thread failed: {exc}"}

    return results
