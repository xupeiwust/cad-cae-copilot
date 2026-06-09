"""Geometry compilation cache system.

Caches compiled geometry results (STEP, topology, feature graph, thumbnails)
using SHA256(Shape IR JSON) as the cache key. Supports in-memory LRU cache
and persistent disk cache with TTL.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CachedGeometry:
    """A single cached geometry compilation result."""

    shape_ir_hash: str
    step_path: str | None = None
    topology_map: dict[str, Any] | None = None
    feature_graph: dict[str, Any] | None = None
    thumbnail_path: str | None = None
    stl_path: str | None = None
    glb_path: str | None = None
    created_at: float = field(default_factory=time.time)
    source_mtime: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape_ir_hash": self.shape_ir_hash,
            "step_path": self.step_path,
            "topology_map": self.topology_map,
            "feature_graph": self.feature_graph,
            "thumbnail_path": self.thumbnail_path,
            "stl_path": self.stl_path,
            "glb_path": self.glb_path,
            "created_at": self.created_at,
            "source_mtime": self.source_mtime,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CachedGeometry":
        return cls(
            shape_ir_hash=data["shape_ir_hash"],
            step_path=data.get("step_path"),
            topology_map=data.get("topology_map"),
            feature_graph=data.get("feature_graph"),
            thumbnail_path=data.get("thumbnail_path"),
            stl_path=data.get("stl_path"),
            glb_path=data.get("glb_path"),
            created_at=data.get("created_at", 0.0),
            source_mtime=data.get("source_mtime", 0.0),
            metadata=data.get("metadata", {}),
        )


class GeometryCache:
    """Thread-safe geometry compilation cache with memory + disk tiers.

    Args:
        cache_dir: Directory for persistent disk cache. Defaults to ``.aieng_cache/``
            under the current working directory.
        ttl_seconds: Time-to-live for cache entries in seconds (default 24h).
        max_memory_entries: Maximum in-memory entries before LRU eviction
            (default 1000).
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_seconds: int = 86400,
        max_memory_entries: int = 1000,
    ) -> None:
        self._cache_dir = cache_dir or Path(".aieng_cache")
        self._ttl_seconds = ttl_seconds
        self._max_memory_entries = max_memory_entries
        self._memory: OrderedDict[str, CachedGeometry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._errors = 0
        # Ensure disk cache directory exists
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # ── public API ────────────────────────────────────────────────────────────

    def get(self, shape_ir_hash: str) -> CachedGeometry | None:
        """Retrieve a cached result by its Shape IR hash.

        Checks memory first, then disk. Returns ``None`` if expired or missing.
        """
        with self._lock:
            # 1. Memory tier
            cached = self._memory.get(shape_ir_hash)
            if cached is not None:
                if self._is_expired(cached):
                    self._memory.pop(shape_ir_hash, None)
                    self._misses += 1
                    return None
                self._memory.move_to_end(shape_ir_hash)
                self._hits += 1
                return cached

            # 2. Disk tier
            disk_entry = self._read_disk_entry(shape_ir_hash)
            if disk_entry is not None:
                if self._is_expired(disk_entry):
                    self._delete_disk_entry(shape_ir_hash)
                    self._misses += 1
                    return None
                # Promote to memory
                self._memory[shape_ir_hash] = disk_entry
                self._memory.move_to_end(shape_ir_hash)
                self._enforce_memory_limit()
                self._hits += 1
                return disk_entry

            self._misses += 1
            return None

    def set(self, shape_ir_hash: str, result: CachedGeometry) -> None:
        """Store a compilation result in both memory and disk caches."""
        result.shape_ir_hash = shape_ir_hash
        result.created_at = time.time()
        with self._lock:
            self._memory[shape_ir_hash] = result
            self._memory.move_to_end(shape_ir_hash)
            self._enforce_memory_limit()
            self._write_disk_entry(shape_ir_hash, result)

    def invalidate(self, project_id: str | None = None) -> None:
        """Invalidate cache entries.

        If ``project_id`` is given, only entries whose metadata contains that
        project_id are removed. Otherwise the entire cache is cleared.
        """
        with self._lock:
            if project_id is None:
                self._memory.clear()
                self._clear_disk_cache()
                return

            # Selective invalidation by project_id
            to_remove = [
                h
                for h, entry in self._memory.items()
                if entry.metadata.get("project_id") == project_id
            ]
            for h in to_remove:
                self._memory.pop(h, None)
                self._delete_disk_entry(h)

    def clear(self) -> None:
        """Clear all cache tiers."""
        with self._lock:
            self._memory.clear()
            self._clear_disk_cache()

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "errors": self._errors,
                "hit_rate": self._hits / total if total > 0 else 0.0,
                "memory_entries": len(self._memory),
                "max_memory_entries": self._max_memory_entries,
                "ttl_seconds": self._ttl_seconds,
                "cache_dir": str(self._cache_dir),
            }

    # ── internal helpers ──────────────────────────────────────────────────────

    def _is_expired(self, entry: CachedGeometry) -> bool:
        return (time.time() - entry.created_at) > self._ttl_seconds

    def _enforce_memory_limit(self) -> None:
        while len(self._memory) > self._max_memory_entries:
            self._memory.popitem(last=False)

    def _entry_dir(self, shape_ir_hash: str) -> Path:
        # Shard by first 2 chars to avoid huge flat directories
        return self._cache_dir / shape_ir_hash[:2] / shape_ir_hash

    def _read_disk_entry(self, shape_ir_hash: str) -> CachedGeometry | None:
        entry_dir = self._entry_dir(shape_ir_hash)
        meta_path = entry_dir / "metadata.json"
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            cached = CachedGeometry.from_dict(data)
            # Load referenced files into memory for fast access
            if cached.step_path and Path(cached.step_path).exists():
                cached.metadata["step_bytes"] = Path(cached.step_path).read_bytes()
            if cached.stl_path and Path(cached.stl_path).exists():
                cached.metadata["stl_bytes"] = Path(cached.stl_path).read_bytes()
            if cached.glb_path and Path(cached.glb_path).exists():
                cached.metadata["glb_bytes"] = Path(cached.glb_path).read_bytes()
            return cached
        except Exception:
            self._errors += 1
            return None

    def _write_disk_entry(self, shape_ir_hash: str, result: CachedGeometry) -> None:
        entry_dir = self._entry_dir(shape_ir_hash)
        try:
            entry_dir.mkdir(parents=True, exist_ok=True)
            # Write metadata (filter out non-JSON-serializable bytes from metadata)
            meta_path = entry_dir / "metadata.json"
            safe_meta = {
                k: v for k, v in result.metadata.items() if not isinstance(v, bytes)
            }
            safe_dict = result.to_dict()
            safe_dict["metadata"] = safe_meta
            meta_path.write_text(
                json.dumps(safe_dict, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            # Write binary artifacts if present in metadata
            if "step_bytes" in result.metadata:
                step_path = entry_dir / "generated.step"
                step_path.write_bytes(result.metadata["step_bytes"])
                result.step_path = str(step_path)
            if "stl_bytes" in result.metadata:
                stl_path = entry_dir / "preview.stl"
                stl_path.write_bytes(result.metadata["stl_bytes"])
                result.stl_path = str(stl_path)
            if "glb_bytes" in result.metadata:
                glb_path = entry_dir / "preview.glb"
                glb_path.write_bytes(result.metadata["glb_bytes"])
                result.glb_path = str(glb_path)
            # Update metadata with final paths
            safe_dict = result.to_dict()
            safe_dict["metadata"] = safe_meta
            meta_path.write_text(
                json.dumps(safe_dict, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception:
            self._errors += 1

    def _delete_disk_entry(self, shape_ir_hash: str) -> None:
        entry_dir = self._entry_dir(shape_ir_hash)
        try:
            if entry_dir.exists():
                import shutil

                shutil.rmtree(entry_dir, ignore_errors=True)
        except Exception:
            pass

    def _clear_disk_cache(self) -> None:
        try:
            if self._cache_dir.exists():
                import shutil

                shutil.rmtree(self._cache_dir, ignore_errors=True)
                self._cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


# ── convenience helpers ───────────────────────────────────────────────────────

def compute_shape_ir_hash(payload: dict[str, Any]) -> str:
    """Compute a stable SHA256 hash of a Shape IR payload.

    Sorts keys and normalises so equivalent payloads produce identical hashes.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
