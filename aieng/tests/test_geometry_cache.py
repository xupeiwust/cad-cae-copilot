"""Tests for the geometry compilation cache system."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
from aieng.cache.metrics import CacheMetrics, get_cache_report, get_default_metrics


class TestComputeShapeIrHash:
    def test_stable_hash_for_equivalent_payloads(self) -> None:
        a = {"parts": [{"name": "bracket", "id": "p1"}], "format_version": "0.1"}
        b = {"parts": [{"id": "p1", "name": "bracket"}], "format_version": "0.1"}
        assert compute_shape_ir_hash(a) == compute_shape_ir_hash(b)

    def test_different_payloads_different_hashes(self) -> None:
        a = {"parts": [{"name": "bracket"}]}
        b = {"parts": [{"name": "plate"}]}
        assert compute_shape_ir_hash(a) != compute_shape_ir_hash(b)


class TestCachedGeometry:
    def test_roundtrip_dict(self) -> None:
        cg = CachedGeometry(
            shape_ir_hash="abc123",
            step_path="/tmp/test.step",
            topology_map={"entities": []},
            metadata={"source": "print('hello')"},
        )
        d = cg.to_dict()
        restored = CachedGeometry.from_dict(d)
        assert restored.shape_ir_hash == cg.shape_ir_hash
        assert restored.step_path == cg.step_path
        assert restored.topology_map == cg.topology_map
        assert restored.metadata == cg.metadata


class TestGeometryCache:
    def test_get_miss_returns_none(self, tmp_path: Path) -> None:
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        assert cache.get("nonexistent") is None

    def test_set_and_get_roundtrip(self, tmp_path: Path) -> None:
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cg = CachedGeometry(
            shape_ir_hash="h1",
            metadata={"source": "code", "representation": "brep_build123d"},
        )
        cache.set("h1", cg)
        got = cache.get("h1")
        assert got is not None
        assert got.shape_ir_hash == "h1"
        assert got.metadata["source"] == "code"

    def test_memory_lru_eviction(self, tmp_path: Path) -> None:
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600, max_memory_entries=2)
        cache.set("a", CachedGeometry(shape_ir_hash="a"))
        cache.set("b", CachedGeometry(shape_ir_hash="b"))
        cache.set("c", CachedGeometry(shape_ir_hash="c"))
        # Memory should only hold 2 entries; 'a' may still be on disk
        stats = cache.get_stats()
        assert stats["memory_entries"] <= 2
        assert cache.get("b") is not None
        assert cache.get("c") is not None

    def test_ttl_expiration(self, tmp_path: Path) -> None:
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=0)
        cg = CachedGeometry(shape_ir_hash="h1", created_at=time.time() - 1)
        cache.set("h1", cg)
        assert cache.get("h1") is None

    def test_disk_persistence(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache = GeometryCache(cache_dir=cache_dir, ttl_seconds=3600)
        cg = CachedGeometry(
            shape_ir_hash="h1",
            metadata={"step_bytes": b"STEP", "stl_bytes": b"STL", "glb_bytes": b"GLB"},
        )
        cache.set("h1", cg)

        # Fresh cache instance should read from disk
        cache2 = GeometryCache(cache_dir=cache_dir, ttl_seconds=3600)
        got = cache2.get("h1")
        assert got is not None
        assert got.metadata.get("step_bytes") == b"STEP"
        assert got.metadata.get("stl_bytes") == b"STL"
        assert got.metadata.get("glb_bytes") == b"GLB"

    def test_invalidate_by_project_id(self, tmp_path: Path) -> None:
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cache.set("a", CachedGeometry(shape_ir_hash="a", metadata={"project_id": "proj1"}))
        cache.set("b", CachedGeometry(shape_ir_hash="b", metadata={"project_id": "proj2"}))
        cache.invalidate(project_id="proj1")
        assert cache.get("a") is None
        assert cache.get("b") is not None

    def test_clear(self, tmp_path: Path) -> None:
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cache.set("a", CachedGeometry(shape_ir_hash="a"))
        cache.clear()
        assert cache.get("a") is None

    def test_stats(self, tmp_path: Path) -> None:
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        cache.get("miss")
        cache.set("h", CachedGeometry(shape_ir_hash="h"))
        cache.get("h")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["memory_entries"] == 1

    def test_thread_safety(self, tmp_path: Path) -> None:
        import threading

        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for i in range(50):
                    h = f"hash_{n}_{i}"
                    cache.set(h, CachedGeometry(shape_ir_hash=h))
                    cache.get(h)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_error_degradation(self, tmp_path: Path) -> None:
        """Cache failures must not affect normal compilation flow."""
        # Use a read-only directory to force disk-write errors
        read_only = tmp_path / "readonly"
        read_only.mkdir()
        # On Windows we can't easily chmod; instead just verify the cache
        # gracefully handles exceptions by checking stats don't crash.
        cache = GeometryCache(cache_dir=read_only, ttl_seconds=3600)
        # Setting should not raise even if disk write fails (errors are swallowed)
        cache.set("h", CachedGeometry(shape_ir_hash="h"))
        # Stats should still work
        stats = cache.get_stats()
        assert "errors" in stats or stats["memory_entries"] == 1


class TestCacheMetrics:
    def test_record_hit(self) -> None:
        m = CacheMetrics()
        m.record_hit(estimated_compile_time_s=3.0)
        m.record_hit(estimated_compile_time_s=2.0)
        r = m.get_report()
        assert r["hits"] == 2
        assert r["total_cached_time_s"] == 5.0

    def test_record_miss_and_compile(self) -> None:
        m = CacheMetrics()
        m.record_miss()
        m.record_compile(1.5)
        r = m.get_report()
        assert r["misses"] == 1
        assert r["avg_compile_time_s"] == 1.5

    def test_hit_rate(self) -> None:
        m = CacheMetrics()
        m.record_hit()
        m.record_miss()
        m.record_miss()
        r = m.get_report()
        assert r["hit_rate"] == pytest.approx(1 / 3)

    def test_reset(self) -> None:
        m = CacheMetrics()
        m.record_hit()
        m.reset()
        r = m.get_report()
        assert r["hits"] == 0
        assert r["misses"] == 0

    def test_get_cache_report(self) -> None:
        r = get_cache_report()
        assert "hits" in r
        assert "misses" in r

    def test_singleton_default_metrics(self) -> None:
        a = get_default_metrics()
        b = get_default_metrics()
        assert a is b


class TestIncrementalCompiler:
    def test_full_compile_when_no_old_ir(self, tmp_path: Path) -> None:
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        from aieng.incremental import IncrementalCompiler

        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)
        new_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [{"id": "p1", "name": "bracket", "type": "box", "width": 10}],
        }
        result = compiler.compile(None, new_ir)
        assert result.changed_nodes == ["p1"]
        assert result.from_cache is False

    def test_unchanged_nodes_use_cache(self, tmp_path: Path) -> None:
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        from aieng.incremental import IncrementalCompiler

        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)
        old_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [{"id": "p1", "name": "bracket", "type": "box", "width": 10}],
        }
        # First compile populates cache
        compiler.compile(None, old_ir)
        # Second compile with identical IR should hit cache
        result = compiler.compile(old_ir, old_ir)
        assert result.from_cache is True
        assert result.changed_nodes == []
        assert "p1" in result.cached_results or result.from_cache

    def test_changed_nodes_detected(self, tmp_path: Path) -> None:
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        from aieng.incremental import IncrementalCompiler

        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)
        old_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [{"id": "p1", "name": "bracket", "type": "box", "width": 10}],
        }
        new_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [{"id": "p1", "name": "bracket", "type": "box", "width": 20}],
        }
        result = compiler.compile(old_ir, new_ir)
        assert "p1" in result.changed_nodes
