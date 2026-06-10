"""Integration tests for cache system with standard parts.

Tests:
- Standard part compilation result caching and reuse
- Cache consistency after batch insertion
- Incremental compilation behavior with standard part insertions
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest

from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
from aieng.cache.metrics import CacheMetrics, get_cache_report, get_default_metrics
from aieng.incremental import IncrementalCompiler
from aieng.standards import hex_bolt, hex_nut, deep_groove_ball_bearing, washer
from aieng.standards.fasteners import METRIC_BOLT_PRESETS, METRIC_NUT_PRESETS, METRIC_WASHER_PRESETS


class TestStandardPartCacheAndReuse:
    """Test caching and reuse of standard part compilation results."""

    def test_cache_standard_part_shape_ir(self, tmp_path: Path) -> None:
        """A standard part Shape IR payload should be cacheable by hash."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        payload = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [bolt],
        }
        h = compute_shape_ir_hash(payload)

        # Store in cache
        cg = CachedGeometry(
            shape_ir_hash=h,
            metadata={"part_type": "hex_bolt", "preset": "M8", "source": "standards"},
        )
        cache.set(h, cg)

        # Retrieve from cache
        retrieved = cache.get(h)
        assert retrieved is not None
        assert retrieved.shape_ir_hash == h
        assert retrieved.metadata["part_type"] == "hex_bolt"

    def test_cache_hit_avoids_recompilation(self, tmp_path: Path) -> None:
        """Identical standard part payloads should hit cache on second access."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        payload = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [bolt],
        }
        h = compute_shape_ir_hash(payload)

        cache.set(h, CachedGeometry(shape_ir_hash=h, metadata={"cached": True}))
        stats_before = cache.get_stats()

        # Second access
        cache.get(h)
        stats_after = cache.get_stats()
        assert stats_after["hits"] == stats_before["hits"] + 1

    def test_different_presets_different_hashes(self, tmp_path: Path) -> None:
        """Different presets must produce different cache keys."""
        bolt_m8 = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        bolt_m10 = hex_bolt(**METRIC_BOLT_PRESETS["M10"])

        payload_m8 = {"format_version": "0.1", "representation": "brep_build123d", "parts": [bolt_m8]}
        payload_m10 = {"format_version": "0.1", "representation": "brep_build123d", "parts": [bolt_m10]}

        h8 = compute_shape_ir_hash(payload_m8)
        h10 = compute_shape_ir_hash(payload_m10)
        assert h8 != h10

    def test_cache_multiple_standard_part_types(self, tmp_path: Path) -> None:
        """Cache should hold multiple distinct standard part types simultaneously."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        parts = [
            ("hex_bolt", hex_bolt(**METRIC_BOLT_PRESETS["M8"])),
            ("hex_nut", hex_nut(**METRIC_NUT_PRESETS["M8"])),
            ("washer", washer(**METRIC_WASHER_PRESETS["M8"])),
        ]

        hashes: list[str] = []
        for part_type, node in parts:
            payload = {"format_version": "0.1", "representation": "brep_build123d", "parts": [node]}
            h = compute_shape_ir_hash(payload)
            cache.set(h, CachedGeometry(shape_ir_hash=h, metadata={"part_type": part_type}))
            hashes.append(h)

        # Verify all are retrievable
        for h, (part_type, _) in zip(hashes, parts):
            retrieved = cache.get(h)
            assert retrieved is not None
            assert retrieved.metadata["part_type"] == part_type

    def test_ttl_expiration_for_standard_parts(self, tmp_path: Path) -> None:
        """Cache entries should expire after TTL."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=0)
        bolt = hex_bolt()
        payload = {"format_version": "0.1", "representation": "brep_build123d", "parts": [bolt]}
        h = compute_shape_ir_hash(payload)

        cg = CachedGeometry(shape_ir_hash=h, created_at=time.time() - 1)
        cache.set(h, cg)
        assert cache.get(h) is None

    def test_disk_persistence_for_standard_parts(self, tmp_path: Path) -> None:
        """Standard part cache entries should survive cache instance restart."""
        cache_dir = tmp_path / "cache"
        cache = GeometryCache(cache_dir=cache_dir, ttl_seconds=3600)
        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M10"])
        payload = {"format_version": "0.1", "representation": "brep_build123d", "parts": [bolt]}
        h = compute_shape_ir_hash(payload)

        cache.set(h, CachedGeometry(shape_ir_hash=h, metadata={"part_type": "hex_bolt", "preset": "M10"}))

        # Fresh instance
        cache2 = GeometryCache(cache_dir=cache_dir, ttl_seconds=3600)
        retrieved = cache2.get(h)
        assert retrieved is not None
        assert retrieved.metadata["part_type"] == "hex_bolt"


class TestBatchInsertionCacheConsistency:
    """Test cache consistency after batch standard part insertions."""

    def _make_minimal_package(self, tmp_path: Path, parts: list[dict[str, Any]] | None = None) -> Path:
        """Create a minimal .aieng package with shape_ir.json."""
        pkg = tmp_path / "test.aieng"
        shape_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": parts or [],
        }
        fg = {"features": []}
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("geometry/shape_ir.json", json.dumps(shape_ir, indent=2))
            zf.writestr("graph/feature_graph.json", json.dumps(fg, indent=2))
        return pkg

    def test_batch_insert_updates_shape_ir(self, tmp_path: Path) -> None:
        """Batch inserting parts should update the package Shape IR."""
        pkg = self._make_minimal_package(tmp_path)

        # Simulate adding nodes directly to shape_ir (as batch_insert would)
        with zipfile.ZipFile(pkg, "r") as zf:
            payload = json.loads(zf.read("geometry/shape_ir.json").decode("utf-8"))

        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        nut = hex_nut(**METRIC_NUT_PRESETS["M8"])
        payload["parts"].extend([bolt, nut])

        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("geometry/shape_ir.json", json.dumps(payload, indent=2))
            zf.writestr("graph/feature_graph.json", json.dumps({"features": []}))

        # Verify updated package
        with zipfile.ZipFile(pkg, "r") as zf:
            updated = json.loads(zf.read("geometry/shape_ir.json").decode("utf-8"))
        assert len(updated["parts"]) == 2
        assert updated["parts"][0]["id"] == "hex_bolt"
        assert updated["parts"][1]["id"] == "hex_nut"

    def test_cache_keys_remain_stable_after_batch_insert(self, tmp_path: Path) -> None:
        """Existing cache keys should remain valid after new parts are added."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        old_payload = {"format_version": "0.1", "representation": "brep_build123d", "parts": [bolt]}
        old_hash = compute_shape_ir_hash(old_payload)
        cache.set(old_hash, CachedGeometry(shape_ir_hash=old_hash, metadata={"version": 1}))

        # Simulate batch insert adding a nut
        nut = hex_nut(**METRIC_NUT_PRESETS["M8"])
        new_payload = {"format_version": "0.1", "representation": "brep_build123d", "parts": [bolt, nut]}
        new_hash = compute_shape_ir_hash(new_payload)

        # Old hash should still be in cache
        assert cache.get(old_hash) is not None
        # New hash should be different
        assert old_hash != new_hash

    def test_project_invalidation_clears_standard_part_cache(self, tmp_path: Path) -> None:
        """Invalidating a project should clear its standard part cache entries."""
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        bolt = hex_bolt()
        payload = {"format_version": "0.1", "representation": "brep_build123d", "parts": [bolt]}
        h = compute_shape_ir_hash(payload)

        cache.set(h, CachedGeometry(shape_ir_hash=h, metadata={"project_id": "proj_std"}))
        assert cache.get(h) is not None

        cache.invalidate(project_id="proj_std")
        assert cache.get(h) is None

    def test_metrics_record_batch_operations(self) -> None:
        """Cache metrics should record hits/misses during batch operations."""
        metrics = CacheMetrics()
        # Simulate a batch where first part misses and second hits
        metrics.record_miss()
        metrics.record_compile(2.5)
        metrics.record_hit(estimated_compile_time_s=2.5)

        report = metrics.get_report()
        assert report["hits"] == 1
        assert report["misses"] == 1
        assert report["total_cached_time_s"] == 2.5


class TestIncrementalCompilationWithStandardParts:
    """Test incremental compiler behavior when standard parts are inserted."""

    def test_full_compile_when_no_old_ir(self, tmp_path: Path) -> None:
        """IncrementalCompiler should do full compile when old_ir is None."""
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)

        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        new_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [bolt],
        }
        result = compiler.compile(None, new_ir)
        assert result.changed_nodes == ["hex_bolt"]
        assert result.from_cache is False

    def test_unchanged_standard_part_uses_cache(self, tmp_path: Path) -> None:
        """Recompiling identical IR with a standard part should hit cache."""
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)

        bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [bolt],
        }
        # First compile
        compiler.compile(None, ir)
        # Second compile with identical IR
        result = compiler.compile(ir, ir)
        assert result.from_cache is True
        assert result.changed_nodes == []

    def test_changed_standard_part_detected(self, tmp_path: Path) -> None:
        """Changing a standard part parameter should mark it as changed."""
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)

        old_bolt = hex_bolt(**METRIC_BOLT_PRESETS["M8"])
        new_bolt = hex_bolt(**METRIC_BOLT_PRESETS["M10"])
        old_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [old_bolt],
        }
        new_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [new_bolt],
        }
        result = compiler.compile(old_ir, new_ir)
        assert "hex_bolt" in result.changed_nodes
        assert result.from_cache is False

    def test_adding_new_standard_part_detected(self, tmp_path: Path) -> None:
        """Adding a new standard part to existing IR should detect it as changed."""
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)

        old_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [hex_bolt(**METRIC_BOLT_PRESETS["M8"])],
        }
        new_ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [
                hex_bolt(**METRIC_BOLT_PRESETS["M8"]),
                hex_nut(**METRIC_NUT_PRESETS["M8"]),
            ],
        }
        result = compiler.compile(old_ir, new_ir)
        # The new part must be detected as changed
        assert "hex_nut" in result.changed_nodes
        # The compiler may conservatively also mark the existing bolt as changed
        # due to list-order or deep-equality nuances; we only require the new part
        # to be in changed_nodes.

    def test_merged_topology_after_standard_part_compile(self, tmp_path: Path) -> None:
        """IncrementalCompiler should produce a merged topology map."""
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)

        ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [
                hex_bolt(**METRIC_BOLT_PRESETS["M6"]),
                hex_nut(**METRIC_NUT_PRESETS["M6"]),
            ],
        }
        result = compiler.compile(None, ir)
        assert result.merged_topology is not None
        assert "entities" in result.merged_topology
        assert result.merged_topology["metadata"]["compiled_nodes"] == 2

    def test_merged_feature_graph_after_standard_part_compile(self, tmp_path: Path) -> None:
        """IncrementalCompiler should produce a merged feature graph."""
        pytest.importorskip("aieng.converters.shape_ir", reason="shape_ir converter not available")
        cache = GeometryCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)
        compiler = IncrementalCompiler(cache=cache)

        ir = {
            "format_version": "0.1",
            "representation": "brep_build123d",
            "parts": [deep_groove_ball_bearing(bore=20.0, outer_diameter=47.0)],
        }
        result = compiler.compile(None, ir)
        assert result.merged_feature_graph is not None
        assert "features" in result.merged_feature_graph
