"""Tests for geometry_providers — pluggable CAD geometry context system."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.geometry_providers import (
    AdjacencyArc,
    EditImpact,
    GeometryContext,
    GeometryProvider,
    InterfaceEdge,
    StaticPackageProvider,
    _detect_bolt_patterns,
    _assign_face_roles,
    build_geometry_context,
    FaceInfo,
    FeatureInfo,
)

# ── test fixtures ─────────────────────────────────────────────────────────────

_TOPOLOGY: dict[str, Any] = {
    "format_version": "0.1",
    "entities": [
        {
            "id": "body_001",
            "type": "solid",
            "bounding_box": [0.0, 0.0, 0.0, 100.0, 50.0, 10.0],
        },
        # bottom face (normal -Z, near zmin)
        {
            "id": "face_001",
            "type": "face",
            "surface_type": "plane",
            "area": 5000.0,
            "normal": [0.0, 0.0, -1.0],
            "bounding_box": [0.0, 0.0, 0.0, 100.0, 50.0, 0.0],
        },
        # top face (normal +Z)
        {
            "id": "face_002",
            "type": "face",
            "surface_type": "plane",
            "area": 5000.0,
            "normal": [0.0, 0.0, 1.0],
            "bounding_box": [0.0, 0.0, 10.0, 100.0, 50.0, 10.0],
        },
        # bolt holes (4 cylinders, same radius)
        {
            "id": "face_003",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "bounding_box": [8.0, 8.0, 0.0, 12.0, 12.0, 10.0],
        },
        {
            "id": "face_004",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "bounding_box": [88.0, 8.0, 0.0, 92.0, 12.0, 10.0],
        },
        {
            "id": "face_005",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "bounding_box": [8.0, 38.0, 0.0, 12.0, 42.0, 10.0],
        },
        {
            "id": "face_006",
            "type": "face",
            "surface_type": "cylinder",
            "area": 251.3,
            "radius": 4.0,
            "bounding_box": [88.0, 38.0, 0.0, 92.0, 42.0, 10.0],
        },
        # side face
        {
            "id": "face_007",
            "type": "face",
            "surface_type": "plane",
            "area": 500.0,
            "normal": [1.0, 0.0, 0.0],
            "bounding_box": [100.0, 0.0, 0.0, 100.0, 50.0, 10.0],
        },
    ],
}

_FEATURE_GRAPH: dict[str, Any] = {
    "features": [
        {
            "id": "feat_plate_001",
            "type": "base_plate",
            "name": "Main plate",
            "geometry_refs": {"faces": ["face_001", "face_002"]},
            "parameters": {"length_mm": 100.0, "width_mm": 50.0, "thickness_mm": 10.0},
            "intent": {"role": "structural_base_candidate"},
        },
        {
            "id": "feat_hole_pattern_001",
            "type": "mounting_hole_pattern",
            "name": "Corner bolt holes",
            "geometry_refs": {"faces": ["face_003", "face_004", "face_005", "face_006"]},
            "parameters": {"hole_diameter_mm": 8.0, "count": 4},
            "intent": {"role": "mounting_candidate"},
            "relationships": [
                {
                    "type": "located_on",
                    "target_feature_id": "feat_plate_001",
                }
            ],
        },
    ]
}


def _make_package(tmp_path: Path, topology: bool = True, features: bool = True) -> Path:
    pkg = tmp_path / "test.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": "0.1"}))
        if topology:
            zf.writestr("geometry/topology_map.json", json.dumps(_TOPOLOGY))
        if features:
            zf.writestr("graph/feature_graph.json", json.dumps(_FEATURE_GRAPH))
    return pkg


# ── bolt pattern detection ────────────────────────────────────────────────────

def test_detect_bolt_patterns_groups_same_radius() -> None:
    faces = [
        FaceInfo("face_003", "cylinder", radius_mm=4.0),
        FaceInfo("face_004", "cylinder", radius_mm=4.0),
        FaceInfo("face_005", "cylinder", radius_mm=4.0),
        FaceInfo("face_006", "cylinder", radius_mm=4.0),
        FaceInfo("face_007", "plane"),
    ]
    groups = _detect_bolt_patterns(faces)
    assert len(groups) == 1
    assert len(groups[0]) == 4
    assert set(groups[0]) == {"face_003", "face_004", "face_005", "face_006"}


def test_detect_bolt_patterns_two_different_radii() -> None:
    faces = [
        FaceInfo("face_001", "cylinder", radius_mm=4.0),
        FaceInfo("face_002", "cylinder", radius_mm=4.0),
        FaceInfo("face_003", "cylinder", radius_mm=8.0),
        FaceInfo("face_004", "cylinder", radius_mm=8.0),
    ]
    groups = _detect_bolt_patterns(faces)
    assert len(groups) == 2


def test_detect_bolt_patterns_single_cylinder_no_group() -> None:
    faces = [FaceInfo("face_001", "cylinder", radius_mm=4.0)]
    groups = _detect_bolt_patterns(faces)
    assert groups == []


# ── face role assignment ──────────────────────────────────────────────────────

def test_assign_face_roles_bottom_face_gets_base_support() -> None:
    faces = [
        FaceInfo("face_001", "plane", area_mm2=5000.0, normal=[0.0, 0.0, -1.0], center=[50.0, 25.0, 0.0]),
    ]
    _assign_face_roles(faces, [0.0, 0.0, 0.0, 100.0, 50.0, 10.0])
    assert faces[0].engineering_role == "base_support"


def test_assign_face_roles_cylinder_gets_mounting_candidate() -> None:
    faces = [FaceInfo("face_003", "cylinder", radius_mm=4.0, center=[10.0, 10.0, 5.0])]
    _assign_face_roles(faces, [0.0, 0.0, 0.0, 100.0, 50.0, 10.0])
    assert faces[0].engineering_role == "mounting_candidate"


def test_assign_face_roles_top_face_gets_load_face() -> None:
    faces = [
        FaceInfo("face_002", "plane", area_mm2=5000.0, normal=[0.0, 0.0, 1.0], center=[50.0, 25.0, 10.0]),
    ]
    _assign_face_roles(faces, [0.0, 0.0, 0.0, 100.0, 50.0, 10.0])
    assert faces[0].engineering_role == "load_face"


# ── StaticPackageProvider ─────────────────────────────────────────────────────

def test_static_provider_can_provide_with_topology(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    provider = StaticPackageProvider()
    assert provider.can_provide(pkg) is True


def test_static_provider_cannot_provide_empty_package(tmp_path: Path) -> None:
    pkg = tmp_path / "empty.aieng"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("manifest.json", "{}")
    provider = StaticPackageProvider()
    assert provider.can_provide(pkg) is False


def test_static_provider_extracts_bounding_box(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = GeometryContext()
    StaticPackageProvider().enrich(pkg, ctx)
    assert ctx.bounding_box == [0.0, 0.0, 0.0, 100.0, 50.0, 10.0]


def test_static_provider_loads_faces(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = GeometryContext()
    StaticPackageProvider().enrich(pkg, ctx)
    face_ids = {f.face_id for f in ctx.faces}
    assert "face_001" in face_ids
    assert "face_003" in face_ids


def test_static_provider_loads_features(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = GeometryContext()
    StaticPackageProvider().enrich(pkg, ctx)
    feat_ids = {f.feature_id for f in ctx.features}
    assert "feat_plate_001" in feat_ids
    assert "feat_hole_pattern_001" in feat_ids


def test_static_provider_detects_bolt_pattern(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = GeometryContext()
    StaticPackageProvider().enrich(pkg, ctx)
    assert len(ctx.bolt_pattern_groups) == 1
    assert len(ctx.bolt_pattern_groups[0]) == 4


def test_static_provider_suggests_mounting_features_as_fixed(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = GeometryContext()
    StaticPackageProvider().enrich(pkg, ctx)
    # mounting_hole_pattern features override face-level heuristics
    for fid in ["face_003", "face_004", "face_005", "face_006"]:
        assert fid in ctx.suggested_fixed_face_ids


def test_static_provider_feature_role_mapping(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = GeometryContext()
    StaticPackageProvider().enrich(pkg, ctx)
    plate = next(f for f in ctx.features if f.feature_id == "feat_plate_001")
    holes = next(f for f in ctx.features if f.feature_id == "feat_hole_pattern_001")
    assert plate.engineering_role == "structural_base"
    assert holes.engineering_role == "mounting"


def test_static_provider_no_topology_no_crash(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path, topology=False, features=False)
    with zipfile.ZipFile(pkg, "a") as zf:
        zf.writestr("geometry/topology_map.json", "not-json")
    ctx = GeometryContext()
    StaticPackageProvider().enrich(pkg, ctx)  # must not raise
    assert len(ctx.warnings) > 0


# ── GeometryContext.to_llm_text ───────────────────────────────────────────────

def test_to_llm_text_contains_key_sections(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = build_geometry_context(pkg)
    text = ctx.to_llm_text()

    assert "BOUNDING BOX" in text
    assert "100.0" in text
    assert "FACES" in text
    assert "cylinder" in text
    assert "ENGINEERING FEATURES" in text
    assert "mounting_hole_pattern" in text
    assert "BOLT PATTERN CANDIDATES" in text
    assert "SUGGESTED FIXED SUPPORTS" in text
    assert "static_package" in text


def test_to_llm_text_shows_engineering_roles(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = build_geometry_context(pkg)
    text = ctx.to_llm_text()
    assert "mounting_candidate" in text or "mounting" in text


# ── GeometryProvider protocol ─────────────────────────────────────────────────

def test_static_package_provider_satisfies_protocol() -> None:
    provider = StaticPackageProvider()
    assert isinstance(provider, GeometryProvider)


def test_custom_provider_satisfies_protocol() -> None:
    """Any class with name, can_provide, enrich satisfies the protocol."""

    class DummyProvider:
        @property
        def name(self) -> str:
            return "dummy"

        def can_provide(self, _: Path) -> bool:
            return True

        def enrich(self, _: Path, ctx: GeometryContext) -> None:
            ctx.engineering_notes.append("from dummy provider")

    provider = DummyProvider()
    assert isinstance(provider, GeometryProvider)


def test_extra_provider_enriches_context(tmp_path: Path) -> None:
    """build_geometry_context calls extra_providers after StaticPackageProvider."""

    class NoteProvider:
        @property
        def name(self) -> str:
            return "note_provider"

        def can_provide(self, _: Path) -> bool:
            return True

        def enrich(self, _: Path, ctx: GeometryContext) -> None:
            ctx.engineering_notes.append("injected from NoteProvider")

    pkg = _make_package(tmp_path)
    ctx = build_geometry_context(pkg, extra_providers=[NoteProvider()])
    assert "note_provider" in ctx.providers_used
    assert any("NoteProvider" in n for n in ctx.engineering_notes)


def test_failing_extra_provider_adds_warning(tmp_path: Path) -> None:
    """A provider that raises must not crash build_geometry_context."""

    class BrokenProvider:
        @property
        def name(self) -> str:
            return "broken"

        def can_provide(self, _: Path) -> bool:
            return True

        def enrich(self, _: Path, ctx: GeometryContext) -> None:
            raise RuntimeError("simulated failure")

    pkg = _make_package(tmp_path)
    ctx = build_geometry_context(pkg, extra_providers=[BrokenProvider()])
    assert any("broken" in w for w in ctx.warnings)
    # static_package must still have run
    assert "static_package" in ctx.providers_used


# ── pointer syntax in to_llm_text ─────────────────────────────────────────────

def test_to_llm_text_includes_pointer_syntax_preamble(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "POINTER SYNTAX" in text
    assert "@face:<face_id>" in text
    assert "@feature:<feature_id>" in text
    assert "@edge:<edge_id>" in text
    assert "@group:<group_id>" in text


def test_to_llm_text_renders_faces_with_pointers(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "@face:face_001" in text
    assert "@face:face_003" in text


def test_to_llm_text_renders_features_with_pointers(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "@feature:feat_plate_001" in text
    assert "@feature:feat_hole_pattern_001" in text


def test_to_llm_text_renders_feature_relations_with_pointers(tmp_path: Path) -> None:
    """`located_on:feat_plate_001` → `@feature:... --located_on--> @feature:...`"""
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "@feature:feat_hole_pattern_001 --located_on--> @feature:feat_plate_001" in text


def test_to_llm_text_renders_bolt_groups_with_pointers(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "@group:bolt_pattern_001" in text
    assert "@face:face_003" in text


def test_to_llm_text_renders_suggested_faces_with_pointers(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "SUGGESTED FIXED SUPPORTS" in text
    # at least one suggested face should be rendered as a pointer
    assert "@face:face_003" in text or "@face:face_004" in text


# ── adjacency arc surfacing ───────────────────────────────────────────────────

_AAG: dict[str, Any] = {
    "schema_version": "0.1",
    "nodes": [
        {"id": "node_face_001", "topology_entity_id": "face_001", "entity_type": "face", "surface_type": "plane"},
        {"id": "node_face_002", "topology_entity_id": "face_002", "entity_type": "face", "surface_type": "plane"},
        {"id": "node_face_003", "topology_entity_id": "face_003", "entity_type": "face", "surface_type": "cylinder"},
    ],
    "arcs": [
        {
            "id": "arc_001",
            "source_node": "node_face_001",
            "target_node": "node_face_002",
            "shared_edge_ids": ["edge_010"],
            "adjacency_type": "edge_adjacent",
            "confidence": "high",
        },
        {
            "id": "arc_002",
            "source_node": "node_face_001",
            "target_node": "node_face_003",
            "shared_edge_ids": [],
            "adjacency_type": "inferred_from_topology",
            "confidence": "medium",
        },
    ],
}


def _make_package_with_aag(tmp_path: Path) -> Path:
    pkg = tmp_path / "aag.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": "0.1"}))
        zf.writestr("geometry/topology_map.json", json.dumps(_TOPOLOGY))
        zf.writestr("graph/feature_graph.json", json.dumps(_FEATURE_GRAPH))
        zf.writestr("graph/aag.json", json.dumps(_AAG))
    return pkg


def test_static_provider_loads_adjacency_arcs(tmp_path: Path) -> None:
    pkg = _make_package_with_aag(tmp_path)
    ctx = build_geometry_context(pkg)
    assert len(ctx.adjacency_arcs) == 2
    first = ctx.adjacency_arcs[0]
    assert first.from_face_id == "face_001"
    assert first.to_face_id == "face_002"
    assert first.confidence == "high"
    assert first.shared_edge_ids == ["edge_010"]


def test_to_llm_text_renders_adjacency_with_pointers(tmp_path: Path) -> None:
    pkg = _make_package_with_aag(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "FACE ADJACENCY" in text
    assert "@face:face_001 --edge_adjacent--> @face:face_002" in text
    assert "@edge:edge_010" in text


# ── interface graph surfacing ─────────────────────────────────────────────────

_INTERFACE_GRAPH: dict[str, Any] = {
    "edges": [
        {
            "source": {"feature_id": "feat_hole_pattern_001"},
            "target_kind": "boundary_condition",
            "target_label": "bc_fixed_001",
            "role": "fixed_support",
        },
        {
            "source": {"face_id": "face_002"},
            "target_kind": "load",
            "target_label": "load_top_001",
            "role": "applied_force",
        },
    ],
}


def _make_package_with_interface_graph(tmp_path: Path) -> Path:
    pkg = tmp_path / "iface.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": "0.1"}))
        zf.writestr("geometry/topology_map.json", json.dumps(_TOPOLOGY))
        zf.writestr("graph/feature_graph.json", json.dumps(_FEATURE_GRAPH))
        zf.writestr("objects/interface_graph.json", json.dumps(_INTERFACE_GRAPH))
    return pkg


def test_static_provider_loads_interface_edges(tmp_path: Path) -> None:
    pkg = _make_package_with_interface_graph(tmp_path)
    ctx = build_geometry_context(pkg)
    assert len(ctx.interface_edges) == 2
    feat_edge = next(e for e in ctx.interface_edges if e.target_kind == "boundary_condition")
    assert feat_edge.source_pointer == "@feature:feat_hole_pattern_001"
    assert feat_edge.target_label == "bc_fixed_001"
    assert feat_edge.role == "fixed_support"


def test_to_llm_text_renders_interface_edges_with_pointers(tmp_path: Path) -> None:
    pkg = _make_package_with_interface_graph(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "INTERFACE EDGES" in text
    assert "@feature:feat_hole_pattern_001 --boundary_condition--> bc_fixed_001" in text
    assert "@face:face_002 --load--> load_top_001" in text
    assert "role=fixed_support" in text


def test_static_provider_no_aag_no_crash(tmp_path: Path) -> None:
    """Packages without graph/aag.json must still build a context without warnings."""
    pkg = _make_package(tmp_path)
    ctx = build_geometry_context(pkg)
    assert ctx.adjacency_arcs == []
    assert ctx.interface_edges == []
    assert all("adjacency" not in w.lower() for w in ctx.warnings)


def test_to_llm_text_no_adjacency_section_when_absent(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "FACE ADJACENCY" not in text
    assert "INTERFACE EDGES" not in text


def test_adjacency_dataclass_round_trip() -> None:
    arc = AdjacencyArc(
        from_face_id="face_001",
        to_face_id="face_002",
        adjacency_type="edge_adjacent",
        confidence="high",
        shared_edge_ids=["edge_010"],
    )
    assert arc.from_face_id == "face_001"
    assert arc.shared_edge_ids == ["edge_010"]


def test_interface_edge_dataclass_round_trip() -> None:
    e = InterfaceEdge(
        source_pointer="@face:face_003",
        target_kind="load",
        target_label="load_001",
        role="applied_force",
    )
    assert e.source_pointer == "@face:face_003"
    assert e.target_kind == "load"


# ── edit-impact / revalidation_status surfacing ──────────────────────────────

_REVALIDATION_STALE: dict[str, Any] = {
    "schema_version": "0.2",
    "geometry_modified": True,
    "requires_revalidation": True,
    "reason": "geometry_changed",
    "triggering_tool": "cad.edit_parameter",
    "affected_artifacts": [
        "results/result_summary.json",
        "results/computed_metrics.json",
        "results/field_regions.json",
    ],
    "affected_domains": ["result_summary", "field_summaries", "solver_outputs"],
    "claim_advancement": "none",
    "recorded_at": "2026-05-26T10:00:00Z",
    "current_geometry_revision": 3,
    "last_validated_geometry_revision": 1,
    "stale_since_geometry_revision": 2,
    "validated_by_run_id": None,
}

_REVALIDATION_CLEAN: dict[str, Any] = {
    "schema_version": "0.2",
    "geometry_modified": False,
    "requires_revalidation": False,
    "reason": "solver_rerun_completed",
    "triggering_tool": "cae.run_solver",
    "affected_artifacts": [],
    "affected_domains": ["result_summary", "field_summaries", "solver_outputs"],
    "claim_advancement": "none",
    "recorded_at": "2026-05-26T11:00:00Z",
    "current_geometry_revision": 3,
    "last_validated_geometry_revision": 3,
    "stale_since_geometry_revision": None,
    "validated_by_run_id": "run_abc123",
}


def _make_package_with_revalidation(tmp_path: Path, status: dict[str, Any]) -> Path:
    pkg = tmp_path / f"reval_{status['requires_revalidation']}.aieng"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": "0.1"}))
        zf.writestr("geometry/topology_map.json", json.dumps(_TOPOLOGY))
        zf.writestr("graph/feature_graph.json", json.dumps(_FEATURE_GRAPH))
        zf.writestr("state/revalidation_status.json", json.dumps(status))
    return pkg


def test_static_provider_loads_stale_edit_impact(tmp_path: Path) -> None:
    pkg = _make_package_with_revalidation(tmp_path, _REVALIDATION_STALE)
    ctx = build_geometry_context(pkg)
    assert ctx.edit_impact is not None
    ei = ctx.edit_impact
    assert ei.requires_revalidation is True
    assert ei.reason == "geometry_changed"
    assert ei.triggering_tool == "cad.edit_parameter"
    assert "results/result_summary.json" in ei.affected_artifacts
    assert ei.current_geometry_revision == 3
    assert ei.last_validated_geometry_revision == 1
    assert ei.stale_since_geometry_revision == 2


def test_static_provider_loads_clean_edit_impact(tmp_path: Path) -> None:
    pkg = _make_package_with_revalidation(tmp_path, _REVALIDATION_CLEAN)
    ctx = build_geometry_context(pkg)
    assert ctx.edit_impact is not None
    assert ctx.edit_impact.requires_revalidation is False
    assert ctx.edit_impact.validated_by_run_id == "run_abc123"


def test_to_llm_text_renders_stale_edit_impact_section(tmp_path: Path) -> None:
    pkg = _make_package_with_revalidation(tmp_path, _REVALIDATION_STALE)
    text = build_geometry_context(pkg).to_llm_text()
    assert "EDIT IMPACT: STALE" in text
    assert "Geometry revision: 3" in text
    assert "last validated: 1" in text
    assert "stale since rev 2" in text
    assert "Triggered by: cad.edit_parameter" in text
    assert "Reason: geometry_changed" in text
    assert "@artifact:results/result_summary.json" in text
    assert "@artifact:results/computed_metrics.json" in text
    assert "Do NOT cite these artifacts as evidence" in text


def test_to_llm_text_renders_clean_edit_impact_section(tmp_path: Path) -> None:
    pkg = _make_package_with_revalidation(tmp_path, _REVALIDATION_CLEAN)
    text = build_geometry_context(pkg).to_llm_text()
    assert "EDIT IMPACT: clean" in text
    assert "geometry revision 3" in text
    assert "run_abc123" in text
    assert "EDIT IMPACT: STALE" not in text


def test_to_llm_text_omits_edit_impact_when_absent(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    ctx = build_geometry_context(pkg)
    assert ctx.edit_impact is None
    text = ctx.to_llm_text()
    assert "EDIT IMPACT" not in text


def test_pointer_syntax_preamble_includes_artifact(tmp_path: Path) -> None:
    pkg = _make_package(tmp_path)
    text = build_geometry_context(pkg).to_llm_text()
    assert "@artifact:<path>" in text


def test_edit_impact_dataclass_round_trip() -> None:
    ei = EditImpact(
        requires_revalidation=True,
        reason="geometry_changed",
        triggering_tool="cad.edit_parameter",
        affected_artifacts=["results/x.json"],
        affected_domains=["result_summary"],
        current_geometry_revision=2,
        last_validated_geometry_revision=1,
        stale_since_geometry_revision=2,
    )
    assert ei.requires_revalidation is True
    assert ei.affected_artifacts == ["results/x.json"]


def test_stale_edit_impact_truncates_long_affected_lists(tmp_path: Path) -> None:
    long_status = dict(_REVALIDATION_STALE)
    long_status["affected_artifacts"] = [f"results/file_{i:03d}.json" for i in range(20)]
    pkg = _make_package_with_revalidation(tmp_path, long_status)
    text = build_geometry_context(pkg).to_llm_text()
    assert "and 8 more affected artifact(s)" in text  # 20 - 12 shown = 8 hidden
    assert "@artifact:results/file_000.json" in text
    assert "@artifact:results/file_019.json" not in text


def test_clean_status_without_run_id_uses_fallback_phrase(tmp_path: Path) -> None:
    status = dict(_REVALIDATION_CLEAN)
    status["validated_by_run_id"] = None
    pkg = _make_package_with_revalidation(tmp_path, status)
    text = build_geometry_context(pkg).to_llm_text()
    assert "no edits since last validation" in text
