"""Incremental compilation system for Shape IR.

Compares old and new Shape IR payloads, identifies changed nodes, and recompiles
only the modified parts while reusing cached results for unchanged nodes.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from aieng.cache.geometry_cache import CachedGeometry, GeometryCache, compute_shape_ir_hash
from aieng.cache.metrics import get_default_metrics


@dataclass
class CompileResult:
    """Result of an incremental compilation."""

    full_payload: dict[str, Any]
    changed_nodes: list[str]
    unchanged_nodes: list[str]
    cached_results: dict[str, CachedGeometry]
    new_results: dict[str, CachedGeometry]
    merged_topology: dict[str, Any] | None = None
    merged_feature_graph: dict[str, Any] | None = None
    compile_time_s: float = 0.0
    from_cache: bool = False


class IncrementalCompiler:
    """Incremental Shape IR compiler that reuses cached results for unchanged nodes.

    Args:
        cache: ``GeometryCache`` instance for storing/retrieving per-node results.
    """

    def __init__(self, cache: GeometryCache | None = None) -> None:
        self._cache = cache or GeometryCache()
        self._metrics = get_default_metrics()

    # ── public API ────────────────────────────────────────────────────────────

    def compile(
        self,
        old_ir: dict[str, Any] | None,
        new_ir: dict[str, Any],
    ) -> CompileResult:
        """Compile a Shape IR payload incrementally.

        Compares ``old_ir`` against ``new_ir``, determines which nodes changed,
        and only recompiles the changed ones. Unchanged nodes are retrieved from
        the cache.

        Args:
            old_ir: Previous Shape IR payload (``None`` for full compile).
            new_ir: Current Shape IR payload.

        Returns:
            A ``CompileResult`` containing merged topology/feature graphs and
            per-node compilation results.
        """
        start = time.monotonic()
        changed = self._find_changed_nodes(old_ir or {}, new_ir)
        all_nodes = self._list_node_ids(new_ir)
        unchanged = [n for n in all_nodes if n not in changed]

        cached_results: dict[str, CachedGeometry] = {}
        new_results: dict[str, CachedGeometry] = {}

        # Retrieve unchanged nodes from cache
        for node_id in unchanged:
            node_payload = self._extract_node_payload(new_ir, node_id)
            if node_payload is None:
                changed.append(node_id)
                continue
            h = compute_shape_ir_hash(node_payload)
            cached = self._cache.get(h)
            if cached is not None:
                cached_results[node_id] = cached
                self._metrics.record_hit()
            else:
                # Cache miss for an unchanged node (e.g. TTL expired) -> recompile
                changed.append(node_id)
                self._metrics.record_miss()

        # Recompile changed nodes
        for node_id in changed:
            node_payload = self._extract_node_payload(new_ir, node_id)
            if node_payload is None:
                continue
            h = compute_shape_ir_hash(node_payload)
            self._metrics.record_miss()
            try:
                from aieng.converters.shape_ir import compile_shape_ir

                compiled = compile_shape_ir(node_payload)
                cg = CachedGeometry(
                    shape_ir_hash=h,
                    metadata={
                        "representation": compiled.get("representation"),
                        "runtime": compiled.get("runtime"),
                        "source": compiled.get("source"),
                        "source_path": compiled.get("source_path"),
                        "node_id": node_id,
                    },
                )
                self._cache.set(h, cg)
                self._metrics.record_set()
                new_results[node_id] = cg
            except Exception:
                self._metrics.record_error()
                # Error is non-fatal; continue with other nodes

        duration = time.monotonic() - start
        self._metrics.record_compile(duration)

        # Merge results into full payload structures
        merged_topo, merged_fg = self._merge_results(
            new_ir, cached_results, new_results
        )

        return CompileResult(
            full_payload=new_ir,
            changed_nodes=changed,
            unchanged_nodes=unchanged,
            cached_results=cached_results,
            new_results=new_results,
            merged_topology=merged_topo,
            merged_feature_graph=merged_fg,
            compile_time_s=round(duration, 3),
            from_cache=len(changed) == 0 and len(unchanged) > 0,
        )

    # ── internal helpers ──────────────────────────────────────────────────────

    def _find_changed_nodes(self, old_ir: dict[str, Any], new_ir: dict[str, Any]) -> list[str]:
        """Return a list of node IDs that differ between old and new IR."""
        old_nodes = self._index_nodes(old_ir)
        new_nodes = self._index_nodes(new_ir)

        changed: list[str] = []
        all_ids = set(old_nodes.keys()) | set(new_nodes.keys())
        for node_id in all_ids:
            old_node = old_nodes.get(node_id)
            new_node = new_nodes.get(node_id)
            if old_node is None or new_node is None:
                changed.append(node_id)
                continue
            if not self._nodes_equal(old_node, new_node):
                changed.append(node_id)
        return changed

    def _index_nodes(self, ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Index nodes by their ``id`` field for fast comparison."""
        nodes: dict[str, dict[str, Any]] = {}
        raw = ir.get("parts", ir.get("components", []))
        if not isinstance(raw, list):
            return nodes
        for idx, node in enumerate(raw, start=1):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or node.get("name") or f"node_{idx:03d}")
            nodes[node_id] = node
        return nodes

    def _list_node_ids(self, ir: dict[str, Any]) -> list[str]:
        return list(self._index_nodes(ir).keys())

    def _extract_node_payload(self, ir: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        """Extract a single-node payload suitable for hashing."""
        nodes = self._index_nodes(ir)
        node = nodes.get(node_id)
        if node is None:
            return None
        # Return a minimal payload that includes the node + global context
        return {
            "format_version": ir.get("format_version", "0.1"),
            "representation": ir.get("representation", "brep_build123d"),
            "parts": [node],
        }

    def _nodes_equal(self, a: dict[str, Any], b: dict[str, Any]) -> bool:
        """Deep-equality comparison of two node dicts (stable, key-ordered)."""
        return json.dumps(a, sort_keys=True, separators=(",", ":")) == json.dumps(
            b, sort_keys=True, separators=(",", ":")
        )

    def _merge_results(
        self,
        new_ir: dict[str, Any],
        cached: dict[str, CachedGeometry],
        new: dict[str, CachedGeometry],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Merge per-node cached/new results into full topology and feature graph.

        Returns ``(topology_map, feature_graph)`` or ``(None, None)`` if no
        results are available.
        """
        all_results = {**cached, **new}
        if not all_results:
            return None, None

        # Build a merged topology map from individual node results
        entities: list[dict[str, Any]] = []
        for node_id, cg in all_results.items():
            topo = cg.topology_map
            if topo and "entities" in topo:
                entities.extend(topo["entities"])
            else:
                # Fallback: create a minimal entity from the node
                entities.append(
                    {
                        "id": f"body_{node_id}",
                        "type": "solid",
                        "name": node_id,
                        "source_ir_node": node_id,
                    }
                )

        topology_map = {
            "format_version": "0.1",
            "metadata": {
                "extractor": "IncrementalCompiler",
                "extraction_mode": "incremental_from_shape_ir",
                "representation": new_ir.get("representation", "brep_build123d"),
                "compiled_nodes": len(all_results),
                "cached_nodes": len(cached),
                "new_nodes": len(new),
            },
            "entities": entities,
        }

        # Build a merged feature graph
        features: list[dict[str, Any]] = []
        for node_id, cg in all_results.items():
            fg = cg.feature_graph
            if fg and "features" in fg:
                features.extend(fg["features"])
            else:
                features.append(
                    {
                        "id": f"feat_{node_id}",
                        "type": "unknown_feature",
                        "name": node_id,
                        "geometry_refs": {"entities": [f"body_{node_id}"]},
                    }
                )

        feature_graph = {
            "format_version": "0.1",
            "features": features,
            "metadata": {
                "recognizer": "IncrementalCompiler",
                "source_geometry": "geometry/shape_ir.json",
                "representation": new_ir.get("representation", "brep_build123d"),
            },
        }

        return topology_map, feature_graph
