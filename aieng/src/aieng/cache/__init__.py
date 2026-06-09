"""Cache sub-package for aieng.

Provides geometry compilation caching, material data caching, and cache metrics.
"""
from __future__ import annotations

from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
from aieng.cache.material_cache import MaterialCache
from aieng.cache.metrics import CacheMetrics, get_cache_report, get_default_metrics

__all__ = [
    "CachedGeometry",
    "GeometryCache",
    "compute_shape_ir_hash",
    "MaterialCache",
    "CacheMetrics",
    "get_cache_report",
    "get_default_metrics",
]
