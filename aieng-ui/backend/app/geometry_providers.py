"""Pluggable CAD geometry context providers for AI preprocessing.

Architecture:
  Each CAD tool (NX, SolidWorks, ...) can implement GeometryProvider
  to enrich the shared GeometryContext.  The context is then rendered as
  engineering text for the LLM preprocessing prompt.

  The .aieng package format is the CAD-neutral handoff: topology_map.json and
  feature_graph.json are written by each tool's adapter.  StaticPackageProvider
  reads that format and is always available.  Tool-specific providers add richer
  data when their tool is present.

Adding a new CAD tool:
  1. Write an adapter that exports geometry to .aieng (topology_map.json etc.).
  2. Optionally write a GeometryProvider subclass for live, richer inspection.
  3. Register it via build_geometry_context(extra_providers=[YourProvider()]).
"""
from __future__ import annotations

import json
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class FaceInfo:
    face_id: str
    surface_type: str                   # "plane" | "cylinder" | "other"
    area_mm2: float | None = None
    normal: list[float] | None = None   # unit vector, planes only
    radius_mm: float | None = None      # cylinders only
    center: list[float] | None = None   # [x, y, z] centroid
    engineering_role: str = "unknown"   # "mounting_candidate" | "load_face" | "base" | ...
    role_confidence: str = "low"        # "high" | "medium" | "low"
    role_notes: list[str] = field(default_factory=list)


@dataclass
class FeatureInfo:
    feature_id: str
    feature_type: str                   # "base_plate" | "mounting_hole" | "rib" | ...
    name: str = ""
    face_ids: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    engineering_role: str = "unknown"   # "structural_base" | "mounting" | "stiffener" | ...
    related_features: list[str] = field(default_factory=list)  # "located_on:feat_xxx"


@dataclass
class AdjacencyArc:
    """A face-to-face adjacency edge derived from AAG or topology."""
    from_face_id: str
    to_face_id: str
    adjacency_type: str = "unknown"     # "edge_adjacent" | "inferred_from_topology" | ...
    confidence: str = "low"             # "high" | "medium" | "low"
    shared_edge_ids: list[str] = field(default_factory=list)


@dataclass
class InterfaceEdge:
    """A feature/face → external attachment edge (BC, load, constraint, mate)."""
    source_pointer: str                 # e.g. "@feature:feat_hole_001" or "@face:face_003"
    target_kind: str                    # "boundary_condition" | "load" | "constraint" | "mate" | ...
    target_label: str                   # human-readable target descriptor
    role: str = ""                      # e.g. "fixed_support" | "applied_force" | "planar_mate"


@dataclass
class EditImpact:
    """Cross-artifact lineage state derived from state/revalidation_status.json.

    Tells the LLM what is currently stale (and therefore must not be used as
    evidence) and which previous edit caused it.
    """
    requires_revalidation: bool = False
    reason: str | None = None                           # e.g. "geometry_changed"
    triggering_tool: str | None = None                  # e.g. "cad.edit_parameter"
    affected_artifacts: list[str] = field(default_factory=list)
    affected_domains: list[str] = field(default_factory=list)
    current_geometry_revision: int = 0
    last_validated_geometry_revision: int | None = None
    stale_since_geometry_revision: int | None = None
    validated_by_run_id: str | None = None
    recorded_at: str | None = None


@dataclass
class GeometryContext:
    """CAD-tool-neutral geometry context for AI preprocessing."""

    bounding_box: list[float] = field(default_factory=list)  # [xmin,ymin,zmin,xmax,ymax,zmax]
    faces: list[FaceInfo] = field(default_factory=list)
    features: list[FeatureInfo] = field(default_factory=list)
    bolt_pattern_groups: list[list[str]] = field(default_factory=list)
    suggested_fixed_face_ids: list[str] = field(default_factory=list)
    suggested_load_face_ids: list[str] = field(default_factory=list)
    adjacency_arcs: list[AdjacencyArc] = field(default_factory=list)
    interface_edges: list[InterfaceEdge] = field(default_factory=list)
    edit_impact: EditImpact | None = None
    engineering_notes: list[str] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_llm_text(self) -> str:
        """Render context as plain engineering text for the LLM prompt.

        Uses an explicit pointer addressing scheme so the LLM can reference
        entities precisely in its tool calls and proposals:
          @face:<face_id>       — a single B-Rep face
          @feature:<feature_id> — an engineering feature (hole pattern, plate, rib, ...)
          @edge:<edge_id>       — a single B-Rep edge
          @group:<group_id>     — a named selection group (e.g. a bolt pattern)
          @artifact:<path>      — a package-internal artifact (e.g. a result file)
        """
        lines: list[str] = []

        # Pointer-syntax preamble: teach the LLM the addressing convention.
        lines.append("POINTER SYNTAX (use these pointers when proposing CAD/CAE actions):")
        lines.append("  @face:<face_id>       a single B-Rep face")
        lines.append("  @feature:<feature_id> an engineering feature")
        lines.append("  @edge:<edge_id>       a single B-Rep edge")
        lines.append("  @group:<group_id>     a named selection group (e.g. bolt pattern)")
        lines.append("  @artifact:<path>      a package-internal artifact path")
        lines.append("")

        # Edit-impact preamble: surface stale state BEFORE the LLM sees geometry,
        # so any proposal it makes is aware of what's currently untrusted.
        ei = self.edit_impact
        if ei is not None:
            if ei.requires_revalidation:
                lines.append("EDIT IMPACT: STALE — downstream evidence requires revalidation.")
                lines.append(
                    f"  Geometry revision: {ei.current_geometry_revision}"
                    f" (last validated: {ei.last_validated_geometry_revision if ei.last_validated_geometry_revision is not None else 'never'};"
                    f" stale since rev {ei.stale_since_geometry_revision if ei.stale_since_geometry_revision is not None else '?'})"
                )
                if ei.triggering_tool:
                    lines.append(f"  Triggered by: {ei.triggering_tool}")
                if ei.reason:
                    lines.append(f"  Reason: {ei.reason}")
                if ei.affected_artifacts:
                    for path in ei.affected_artifacts[:12]:
                        lines.append(f"    - @artifact:{path}")
                    if len(ei.affected_artifacts) > 12:
                        lines.append(
                            f"    ... and {len(ei.affected_artifacts) - 12} more affected artifact(s)"
                        )
                if ei.affected_domains:
                    lines.append(f"  Affected domains: {', '.join(ei.affected_domains)}")
                lines.append(
                    "  -> Do NOT cite these artifacts as evidence until a fresh solver run validates the current geometry revision."
                )
            else:
                validated = (
                    f"validated by run {ei.validated_by_run_id}"
                    if ei.validated_by_run_id
                    else "no edits since last validation"
                )
                lines.append(
                    f"EDIT IMPACT: clean (geometry revision {ei.current_geometry_revision}, {validated})."
                )
            lines.append("")

        if len(self.bounding_box) == 6:
            bb = self.bounding_box
            dx = bb[3] - bb[0]
            dy = bb[4] - bb[1]
            dz = bb[5] - bb[2]
            lines.append(f"BOUNDING BOX: {dx:.1f} × {dy:.1f} × {dz:.1f} mm")

        planes = [f for f in self.faces if f.surface_type == "plane"]
        cylinders = [f for f in self.faces if f.surface_type == "cylinder"]
        lines.append(
            f"\nFACES: {len(self.faces)} total "
            f"({len(planes)} planar, {len(cylinders)} cylindrical)"
        )
        for face in sorted(self.faces, key=lambda f: -(f.area_mm2 or 0))[:25]:
            parts = [f"@face:{face.face_id}", face.surface_type]
            if face.area_mm2 is not None:
                parts.append(f"area={face.area_mm2:.1f}mm²")
            if face.normal:
                n = face.normal
                parts.append(f"normal=[{n[0]:.2f},{n[1]:.2f},{n[2]:.2f}]")
            if face.radius_mm is not None:
                parts.append(f"radius={face.radius_mm:.2f}mm")
            if face.center:
                c = face.center
                parts.append(f"center=[{c[0]:.1f},{c[1]:.1f},{c[2]:.1f}]")
            if face.engineering_role != "unknown":
                parts.append(f"-> {face.engineering_role} [{face.role_confidence}]")
            lines.append("  " + "  ".join(parts))
        if len(self.faces) > 25:
            lines.append(f"  ... and {len(self.faces) - 25} more faces")

        if self.features:
            lines.append(f"\nENGINEERING FEATURES: {len(self.features)}")
            for feat in self.features:
                parts = [f"@feature:{feat.feature_id}", feat.feature_type]
                if feat.name and feat.name != feat.feature_type:
                    parts.append(f'"{feat.name}"')
                if feat.face_ids:
                    face_ptrs = ", ".join(f"@face:{fid}" for fid in feat.face_ids)
                    parts.append(f"faces=[{face_ptrs}]")
                if feat.parameters:
                    param_str = ", ".join(
                        f"{k}={v}" for k, v in list(feat.parameters.items())[:4]
                    )
                    parts.append(f"params={{{param_str}}}")
                if feat.engineering_role != "unknown":
                    parts.append(f"-> {feat.engineering_role}")
                lines.append("  " + "  ".join(parts))
            for feat in self.features:
                for rel in feat.related_features:
                    # rel is "rel_type:target_feature_id"; pointer-format the target.
                    if ":" in rel:
                        rel_type, target = rel.split(":", 1)
                        lines.append(
                            f"  [relation] @feature:{feat.feature_id} --{rel_type}--> @feature:{target}"
                        )
                    else:
                        lines.append(f"  [relation] @feature:{feat.feature_id} {rel}")

        if self.bolt_pattern_groups:
            lines.append("\nBOLT PATTERN CANDIDATES:")
            for i, group in enumerate(self.bolt_pattern_groups, 1):
                first = next((f for f in self.faces if f.face_id == group[0]), None)
                r = f"{first.radius_mm:.1f}mm" if first and first.radius_mm else "?"
                members = ", ".join(f"@face:{fid}" for fid in group)
                lines.append(
                    f"  @group:bolt_pattern_{i:03d}  {len(group)} holes, r={r}, members=[{members}]"
                )

        if self.adjacency_arcs:
            lines.append(f"\nFACE ADJACENCY: {len(self.adjacency_arcs)} arc(s)")
            # Prefer high-confidence arcs first; cap rendering for token budget.
            sorted_arcs = sorted(
                self.adjacency_arcs,
                key=lambda a: (0 if a.confidence == "high" else 1 if a.confidence == "medium" else 2),
            )
            for arc in sorted_arcs[:20]:
                via = f" via [{', '.join(f'@edge:{e}' for e in arc.shared_edge_ids)}]" if arc.shared_edge_ids else ""
                lines.append(
                    f"  @face:{arc.from_face_id} --{arc.adjacency_type}--> @face:{arc.to_face_id}"
                    f"  [{arc.confidence}]{via}"
                )
            if len(self.adjacency_arcs) > 20:
                lines.append(f"  ... and {len(self.adjacency_arcs) - 20} more arcs")

        if self.interface_edges:
            lines.append(f"\nINTERFACE EDGES: {len(self.interface_edges)} (geometry <-> simulation/assembly)")
            for edge in self.interface_edges[:20]:
                role = f"  role={edge.role}" if edge.role else ""
                lines.append(
                    f"  {edge.source_pointer} --{edge.target_kind}--> {edge.target_label}{role}"
                )
            if len(self.interface_edges) > 20:
                lines.append(f"  ... and {len(self.interface_edges) - 20} more interface edges")

        if self.suggested_fixed_face_ids:
            ptrs = ", ".join(f"@face:{fid}" for fid in self.suggested_fixed_face_ids)
            lines.append(f"\nSUGGESTED FIXED SUPPORTS: [{ptrs}]")
        if self.suggested_load_face_ids:
            ptrs = ", ".join(f"@face:{fid}" for fid in self.suggested_load_face_ids)
            lines.append(f"\nSUGGESTED LOAD SURFACES: [{ptrs}]")

        if self.engineering_notes:
            lines.append("\nENGINEERING NOTES:")
            for note in self.engineering_notes:
                lines.append(f"  • {note}")

        lines.append(f"\nData source(s): {', '.join(self.providers_used) or 'none'}")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  [warning] {w}")

        return "\n".join(lines)


# ── provider protocol ─────────────────────────────────────────────────────────

@runtime_checkable
class GeometryProvider(Protocol):
    """Protocol for CAD geometry context providers.

    To add support for a new CAD tool, implement these three methods.
    Providers must never raise — append to ctx.warnings instead.
    """

    @property
    def name(self) -> str:
        """Short identifier, e.g. 'nx', 'solidworks'."""
        ...

    def can_provide(self, package_path: Path) -> bool:
        """Return True if this provider can contribute data for this package."""
        ...

    def enrich(self, package_path: Path, ctx: GeometryContext) -> None:
        """Enrich ctx in place.  Must not raise."""
        ...


# ── heuristics helpers ────────────────────────────────────────────────────────

def _face_center_from_bbox(bbox: list[float]) -> list[float] | None:
    if len(bbox) != 6:
        return None
    return [
        (bbox[0] + bbox[3]) / 2,
        (bbox[1] + bbox[4]) / 2,
        (bbox[2] + bbox[5]) / 2,
    ]


def _detect_bolt_patterns(faces: list[FaceInfo]) -> list[list[str]]:
    """Group cylindrical faces with the same radius (±8%) into bolt patterns."""
    cylinders = [f for f in faces if f.surface_type == "cylinder" and f.radius_mm is not None]
    if len(cylinders) < 2:
        return []

    groups: list[list[str]] = []
    assigned: set[str] = set()
    for face in cylinders:
        if face.face_id in assigned:
            continue
        r = face.radius_mm
        assert r is not None
        group = [face.face_id]
        assigned.add(face.face_id)
        for other in cylinders:
            if other.face_id in assigned:
                continue
            if other.radius_mm is not None and abs(other.radius_mm - r) / max(r, 1e-9) <= 0.08:
                group.append(other.face_id)
                assigned.add(other.face_id)
        if len(group) >= 2:
            groups.append(group)
    return groups


def _assign_face_roles(faces: list[FaceInfo], bbox: list[float]) -> None:
    """Heuristically assign engineering roles to faces based on geometry."""
    if len(bbox) != 6:
        return
    zmin, zmax = bbox[2], bbox[5]
    z_range = max(zmax - zmin, 1e-9)

    for face in faces:
        if face.surface_type == "cylinder":
            face.engineering_role = "mounting_candidate"
            face.role_confidence = "medium"
            face.role_notes.append("Cylindrical face — likely bolt hole or pin")

        elif face.surface_type == "plane" and face.normal:
            n = face.normal
            abs_nz = abs(n[2])
            abs_nx = abs(n[0])
            abs_ny = abs(n[1])

            # bottom face (normal pointing -Z, near zmin)
            if n[2] < -0.85 and face.center and (face.center[2] - zmin) / z_range < 0.2:
                face.engineering_role = "base_support"
                face.role_confidence = "medium"
                face.role_notes.append("Bottom-facing plane near zmin — likely mounting base")

            # top face (normal +Z)
            elif n[2] > 0.85 and face.center and (zmax - face.center[2]) / z_range < 0.2:
                face.engineering_role = "load_face"
                face.role_confidence = "low"
                face.role_notes.append("Top-facing plane — candidate for distributed load")

            # end/side faces (primary surface when large)
            elif abs_nx > 0.85 or abs_ny > 0.85:
                if face.area_mm2 and face.area_mm2 > 0:
                    face.engineering_role = "end_face"
                    face.role_confidence = "low"
                    face.role_notes.append("Side-facing plane — candidate for point/distributed load")


def _build_engineering_notes(ctx: GeometryContext) -> list[str]:
    notes: list[str] = []
    mounting_candidates = [f for f in ctx.faces if f.engineering_role == "mounting_candidate"]
    if mounting_candidates:
        notes.append(
            f"{len(mounting_candidates)} cylindrical face(s) detected — "
            "likely bolt holes or pin connections; good fixed-support candidates."
        )
    if ctx.bolt_pattern_groups:
        for group in ctx.bolt_pattern_groups:
            first = next((f for f in ctx.faces if f.face_id == group[0]), None)
            r = f"{first.radius_mm:.1f}mm" if first and first.radius_mm else "?"
            notes.append(
                f"Bolt pattern: {len(group)} holes at radius={r} — "
                "apply fixed BC to all faces in the pattern for bolt connection."
            )
    base_faces = [f for f in ctx.faces if f.engineering_role == "base_support"]
    if base_faces:
        notes.append(
            f"{len(base_faces)} bottom-facing planar face(s) — "
            "consider fixed support if the part rests on a surface."
        )
    return notes


# ── StaticPackageProvider ─────────────────────────────────────────────────────

class StaticPackageProvider:
    """Reads topology_map.json and feature_graph.json from the .aieng package.

    Always available — no external tool required.  Applied heuristics to assign
    engineering roles to faces and detect bolt patterns.
    """

    @property
    def name(self) -> str:
        return "static_package"

    def can_provide(self, package_path: Path) -> bool:
        if not package_path.exists():
            return False
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                names = zf.namelist()
                return "geometry/topology_map.json" in names or "graph/feature_graph.json" in names
        except Exception:
            return False

    def enrich(self, package_path: Path, ctx: GeometryContext) -> None:  # noqa: C901
        try:
            self._load_topology(package_path, ctx)
        except Exception as exc:
            ctx.warnings.append(f"static_package: topology load error: {exc}")
        try:
            self._load_features(package_path, ctx)
        except Exception as exc:
            ctx.warnings.append(f"static_package: feature graph load error: {exc}")
        try:
            self._apply_heuristics(ctx)
        except Exception as exc:
            ctx.warnings.append(f"static_package: heuristics error: {exc}")
        try:
            self._load_adjacency(package_path, ctx)
        except Exception as exc:
            ctx.warnings.append(f"static_package: adjacency load error: {exc}")
        try:
            self._load_interface_graph(package_path, ctx)
        except Exception as exc:
            ctx.warnings.append(f"static_package: interface graph load error: {exc}")
        try:
            self._load_edit_impact(package_path, ctx)
        except Exception as exc:
            ctx.warnings.append(f"static_package: edit impact load error: {exc}")
        try:
            self._load_setup_hints(package_path, ctx)
        except Exception:
            pass

    def _read_json(self, package_path: Path, member: str, ctx: GeometryContext) -> dict[str, Any] | None:
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                if member not in zf.namelist():
                    return None
                raw = zf.read(member)
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    ctx.warnings.append(f"static_package: {member} is not valid JSON: {exc}")
                    return None
        except Exception as exc:
            ctx.warnings.append(f"static_package: could not read {member}: {exc}")
            return None

    def _load_topology(self, package_path: Path, ctx: GeometryContext) -> None:
        topo = self._read_json(package_path, "geometry/topology_map.json", ctx)
        if not topo:
            return
        entities = topo.get("entities") or []
        solids = [e for e in entities if e.get("type") == "solid"]
        faces_raw = [e for e in entities if e.get("type") == "face"]

        # bounding box from first solid or computed from faces
        bbox: list[float] = []
        if solids:
            bbox = solids[0].get("bounding_box") or []
        if not bbox and faces_raw:
            all_boxes = [e.get("bounding_box") for e in faces_raw if e.get("bounding_box")]
            if all_boxes:
                bbox = [
                    min(b[0] for b in all_boxes),
                    min(b[1] for b in all_boxes),
                    min(b[2] for b in all_boxes),
                    max(b[3] for b in all_boxes),
                    max(b[4] for b in all_boxes),
                    max(b[5] for b in all_boxes),
                ]
        if bbox:
            ctx.bounding_box = bbox

        for e in faces_raw:
            raw_bbox = e.get("bounding_box") or []
            center = _face_center_from_bbox(raw_bbox) if raw_bbox else None
            ctx.faces.append(FaceInfo(
                face_id=str(e.get("id", "?")),
                surface_type=str(e.get("surface_type", "other")),
                area_mm2=float(e["area"]) if e.get("area") is not None else None,
                normal=e.get("normal"),
                radius_mm=float(e["radius"]) if e.get("radius") is not None else None,
                center=center,
            ))

    def _load_features(self, package_path: Path, ctx: GeometryContext) -> None:
        graph = self._read_json(package_path, "graph/feature_graph.json", ctx)
        if not graph:
            return
        feats_raw = graph.get("features") or graph.get("nodes") or []

        for f in feats_raw:
            ftype = str(f.get("type", "unknown"))
            refs = f.get("geometry_refs") or {}
            face_ids = refs.get("faces") or []
            intent_role = (f.get("intent") or {}).get("role", "")
            relationships = f.get("relationships") or []
            related: list[str] = []
            for rel in relationships:
                rel_type = rel.get("type", "")
                target = rel.get("target_feature_id") or rel.get("source_feature_id")
                if rel_type and target:
                    related.append(f"{rel_type}:{target}")

            eng_role = _feature_type_to_role(ftype, intent_role)
            ctx.features.append(FeatureInfo(
                feature_id=str(f.get("id", "?")),
                feature_type=ftype,
                name=str(f.get("name") or ""),
                face_ids=[str(fid) for fid in face_ids],
                parameters=dict(f.get("parameters") or {}),
                engineering_role=eng_role,
                related_features=related,
            ))

    def _apply_heuristics(self, ctx: GeometryContext) -> None:
        if ctx.bounding_box:
            _assign_face_roles(ctx.faces, ctx.bounding_box)
        ctx.bolt_pattern_groups = _detect_bolt_patterns(ctx.faces)

        # derive suggested faces from heuristics
        for group in ctx.bolt_pattern_groups:
            for fid in group:
                if fid not in ctx.suggested_fixed_face_ids:
                    ctx.suggested_fixed_face_ids.append(fid)

        base_faces = [f.face_id for f in ctx.faces if f.engineering_role == "base_support"]
        for fid in base_faces:
            if fid not in ctx.suggested_fixed_face_ids:
                ctx.suggested_fixed_face_ids.append(fid)

        load_faces = [f.face_id for f in ctx.faces if f.engineering_role == "load_face"]
        for fid in load_faces:
            if fid not in ctx.suggested_load_face_ids:
                ctx.suggested_load_face_ids.append(fid)

        # feature-level suggestions override face-level when available
        mounting_feats = [
            feat for feat in ctx.features if feat.engineering_role == "mounting"
        ]
        if mounting_feats:
            feature_fixed_fids: list[str] = []
            for feat in mounting_feats:
                feature_fixed_fids.extend(feat.face_ids)
            if feature_fixed_fids:
                ctx.suggested_fixed_face_ids = feature_fixed_fids

        ctx.engineering_notes = _build_engineering_notes(ctx)

    def _load_adjacency(self, package_path: Path, ctx: GeometryContext) -> None:
        """Read graph/aag.json arcs into ctx.adjacency_arcs.

        AAG node ids are `node_<face_id>`; we strip that prefix back to the
        underlying face_id so pointer syntax (`@face:<face_id>`) stays consistent.
        """
        aag = self._read_json(package_path, "graph/aag.json", ctx)
        if not aag:
            return
        for arc in aag.get("arcs") or []:
            if not isinstance(arc, dict):
                continue
            src = str(arc.get("source_node") or "")
            tgt = str(arc.get("target_node") or "")
            if not src or not tgt:
                continue
            from_face = src[5:] if src.startswith("node_") else src
            to_face = tgt[5:] if tgt.startswith("node_") else tgt
            shared = [str(e) for e in (arc.get("shared_edge_ids") or []) if e]
            ctx.adjacency_arcs.append(AdjacencyArc(
                from_face_id=from_face,
                to_face_id=to_face,
                adjacency_type=str(arc.get("adjacency_type") or "unknown"),
                confidence=str(arc.get("confidence") or "low"),
                shared_edge_ids=shared,
            ))

    def _load_interface_graph(self, package_path: Path, ctx: GeometryContext) -> None:
        """Read objects/interface_graph.json edges into ctx.interface_edges.

        The interface graph cross-references features/faces with simulation
        attachments (boundary conditions, loads, constraints) and assembly mates.
        Schema is permissive — we accept either an `edges` list or per-interface
        entries that name a source feature/face and a target kind/label.
        """
        graph = self._read_json(package_path, "objects/interface_graph.json", ctx)
        if not graph:
            return

        def _make_pointer(raw: dict[str, Any]) -> str | None:
            for key in ("feature_id", "feature"):
                v = raw.get(key)
                if isinstance(v, str) and v:
                    return f"@feature:{v}"
            for key in ("face_id", "face"):
                v = raw.get(key)
                if isinstance(v, str) and v:
                    return f"@face:{v}"
            ptr = raw.get("pointer") or raw.get("source_pointer")
            if isinstance(ptr, str) and ptr.startswith("@"):
                return ptr
            return None

        edges_raw = graph.get("edges") or graph.get("interfaces") or graph.get("links") or []
        if not isinstance(edges_raw, list):
            return
        for entry in edges_raw:
            if not isinstance(entry, dict):
                continue
            src_ptr = _make_pointer(entry.get("source") if isinstance(entry.get("source"), dict) else entry)
            if not src_ptr:
                continue
            target_kind = str(entry.get("target_kind") or entry.get("kind") or entry.get("type") or "interface")
            target_label = str(
                entry.get("target_label")
                or entry.get("label")
                or entry.get("target_id")
                or entry.get("name")
                or "?"
            )
            role = str(entry.get("role") or "")
            ctx.interface_edges.append(InterfaceEdge(
                source_pointer=src_ptr,
                target_kind=target_kind,
                target_label=target_label,
                role=role,
            ))

    def _load_edit_impact(self, package_path: Path, ctx: GeometryContext) -> None:
        """Read state/revalidation_status.json into ctx.edit_impact.

        Lets the LLM see, in the same prompt, whether prior edits have
        invalidated downstream evidence. Silently no-ops if absent.
        """
        rs = self._read_json(package_path, "state/revalidation_status.json", ctx)
        if not rs:
            return
        ctx.edit_impact = EditImpact(
            requires_revalidation=bool(rs.get("requires_revalidation")),
            reason=rs.get("reason"),
            triggering_tool=rs.get("triggering_tool"),
            affected_artifacts=[str(a) for a in (rs.get("affected_artifacts") or []) if a],
            affected_domains=[str(d) for d in (rs.get("affected_domains") or []) if d],
            current_geometry_revision=int(rs.get("current_geometry_revision") or 0),
            last_validated_geometry_revision=rs.get("last_validated_geometry_revision"),
            stale_since_geometry_revision=rs.get("stale_since_geometry_revision"),
            validated_by_run_id=rs.get("validated_by_run_id"),
            recorded_at=rs.get("recorded_at"),
        )

    def _load_setup_hints(self, package_path: Path, ctx: GeometryContext) -> None:
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                names = zf.namelist()
                if "task/engineering_setup_draft.json" in names:
                    draft = json.loads(zf.read("task/engineering_setup_draft.json"))
                    mat = (draft.get("material") or {}).get("name")
                    if mat:
                        ctx.engineering_notes.append(f"Setup draft material hint: {mat}")
                    sim = draft.get("simulation") or {}
                    if sim.get("fixed"):
                        ctx.engineering_notes.append(
                            f"Setup draft fixed candidates: {sim['fixed']}"
                        )
        except Exception:
            pass


def _feature_type_to_role(ftype: str, intent_role: str) -> str:
    type_map = {
        "mounting_hole": "mounting",
        "mounting_hole_pattern": "mounting",
        "base_plate": "structural_base",
        "rib": "stiffener",
        "fillet": "stress_relief",
        "chamfer": "stress_relief",
        "boss": "contact_point",
        "flange": "connection_face",
        "interface_face": "load_face",
    }
    if ftype in type_map:
        return type_map[ftype]
    intent_map = {
        "structural_base_candidate": "structural_base",
        "mounting_candidate": "mounting",
        "tip_load": "load_face",
        "fixed_support": "mounting",
    }
    return intent_map.get(intent_role, "unknown")


# ── public entry point ────────────────────────────────────────────────────────

def build_geometry_context(
    package_path: Path,
    extra_providers: list[Any] | None = None,
) -> GeometryContext:
    """Build a GeometryContext from the .aieng package.

    Always runs StaticPackageProvider first. Pass additional providers via
    extra_providers if a tool-specific live-inspection provider becomes
    available; build123d-generated topology is already canonical for our
    pipeline so no extras are required for the default text-to-CAD flow.
    """
    ctx = GeometryContext()
    providers: list[Any] = [StaticPackageProvider()] + (extra_providers or [])
    for provider in providers:
        try:
            if provider.can_provide(package_path):
                provider.enrich(package_path, ctx)
                ctx.providers_used.append(provider.name)
        except Exception as exc:
            ctx.warnings.append(f"{getattr(provider, 'name', '?')}: unexpected error: {exc}")
    return ctx
