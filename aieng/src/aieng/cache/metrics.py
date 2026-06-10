"""Cache metrics and monitoring.

Records cache hit/miss rates, compilation times, and cache sizes for
observability and performance tuning.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class CacheMetrics:
    """Thread-safe metrics collector for the geometry cache system.

    Maintains rolling windows of recent compilation times and cache events.
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._errors = 0
        self._compilations: deque[float] = deque(maxlen=max_history)
        self._cache_sets: deque[float] = deque(maxlen=max_history)
        self._cache_gets: deque[float] = deque(maxlen=max_history)
        self._total_compile_time_s = 0.0
        self._total_cached_time_s = 0.0  # Time saved by cache hits

    # ── event recording ────────────────────────────────────────────────────────

    def record_hit(self, estimated_compile_time_s: float = 5.0) -> None:
        """Record a cache hit. ``estimated_compile_time_s`` is the time saved."""
        with self._lock:
            self._hits += 1
            self._total_cached_time_s += estimated_compile_time_s
            self._cache_gets.append(time.time())

    def record_miss(self) -> None:
        """Record a cache miss."""
        with self._lock:
            self._misses += 1
            self._cache_gets.append(time.time())

    def record_compile(self, duration_s: float) -> None:
        """Record a successful compilation."""
        with self._lock:
            self._compilations.append(duration_s)
            self._total_compile_time_s += duration_s

    def record_set(self) -> None:
        """Record a cache write."""
        with self._lock:
            self._cache_sets.append(time.time())

    def record_error(self) -> None:
        """Record a cache system error (does not affect normal compilation)."""
        with self._lock:
            self._errors += 1

    # ── reporting ─────────────────────────────────────────────────────────────

    def get_report(self) -> dict[str, Any]:
        """Return a comprehensive metrics report."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            recent_compiles = list(self._compilations)
            avg_compile_time = (
                sum(recent_compiles) / len(recent_compiles) if recent_compiles else 0.0
            )
            return {
                "hits": self._hits,
                "misses": self._misses,
                "errors": self._errors,
                "hit_rate": hit_rate,
                "total_requests": total,
                "avg_compile_time_s": round(avg_compile_time, 3),
                "total_compile_time_s": round(self._total_compile_time_s, 3),
                "total_cached_time_s": round(self._total_cached_time_s, 3),
                "time_saved_ratio": (
                    round(self._total_cached_time_s / max(self._total_compile_time_s, 0.001), 2)
                    if self._total_compile_time_s > 0
                    else 0.0
                ),
                "recent_compile_count": len(recent_compiles),
                "recent_set_count": len(self._cache_sets),
                "recent_get_count": len(self._cache_gets),
            }

    def reset(self) -> None:
        """Reset all counters and history."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._errors = 0
            self._compilations.clear()
            self._cache_sets.clear()
            self._cache_gets.clear()
            self._total_compile_time_s = 0.0
            self._total_cached_time_s = 0.0


# ── module-level convenience ──────────────────────────────────────────────────

_default_metrics: CacheMetrics | None = None
_default_lock = threading.Lock()


def get_default_metrics() -> CacheMetrics:
    """Return the singleton default metrics instance."""
    global _default_metrics
    if _default_metrics is None:
        with _default_lock:
            if _default_metrics is None:
                _default_metrics = CacheMetrics()
    return _default_metrics


def get_cache_report() -> dict[str, Any]:
    """Return the default metrics report."""
    return get_default_metrics().get_report()
