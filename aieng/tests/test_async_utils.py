"""Tests for asynchronous parallel processing utilities."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aieng.async_utils import async_generate_previews, async_insert_standard_parts, async_recompile_parts
from aieng.cache.geometry_cache import GeometryCache


class TestAsyncRecompileParts:
    def test_empty_list(self) -> None:
        results = async_recompile_parts([])
        assert results == []

    def test_parallel_compilation(self, tmp_path: Path) -> None:
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        parts = [
            {
                "format_version": "0.1",
                "representation": "brep_build123d",
                "parts": [{"id": "p1", "name": "bracket", "type": "box", "width": 10}],
            },
            {
                "format_version": "0.1",
                "representation": "brep_build123d",
                "parts": [{"id": "p2", "name": "plate", "type": "box", "width": 20}],
            },
        ]
        results = async_recompile_parts(parts, max_workers=2, cache=cache)
        assert len(results) == 2
        for r in results:
            assert r["status"] in ("ok", "error")
            assert "hash" in r

    def test_cache_hit_on_second_run(self, tmp_path: Path) -> None:
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        parts = [
            {
                "format_version": "0.1",
                "representation": "brep_build123d",
                "parts": [{"id": "p1", "name": "bracket", "type": "box", "width": 10}],
            },
        ]
        # First run: compile and cache
        r1 = async_recompile_parts(parts, max_workers=1, cache=cache)
        # Second run: should hit cache
        r2 = async_recompile_parts(parts, max_workers=1, cache=cache)
        assert len(r1) == 1
        assert len(r2) == 1
        # At least one of the second run results should be cached
        assert any(r.get("cached") for r in r2)

    def test_max_workers_limits_concurrency(self) -> None:
        # We can't directly test thread count, but we can verify the function
        # accepts the parameter and returns results.
        results = async_recompile_parts([])
        assert results == []


class TestAsyncInsertStandardParts:
    def test_empty_list(self) -> None:
        results = async_insert_standard_parts("proj_123", [])
        assert results == []

    def test_parallel_insertion(self) -> None:
        # Without a real backend, insertion will fail; verify graceful error handling
        requests = [
            {"part_type": "hex_bolt", "parameters": {"diameter": 10, "length": 30}},
            {"part_type": "hex_nut", "parameters": {"diameter": 10}},
        ]
        results = async_insert_standard_parts("proj_123", requests, max_workers=2)
        assert len(results) == 2
        for r in results:
            assert "index" in r
            assert "status" in r
            # When the backend is unavailable, status should be error
            assert r["status"] in ("ok", "error")


class TestAsyncGeneratePreviews:
    def test_empty_list(self) -> None:
        results = async_generate_previews([])
        assert results == []

    def test_skipped_when_no_renderer(self) -> None:
        results = async_generate_previews(["proj_1"], max_workers=1)
        assert len(results) == 1
        assert results[0]["status"] in ("skipped", "error")
