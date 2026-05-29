from __future__ import annotations

import importlib.util
from typing import Any, Protocol, runtime_checkable

from aieng import FORMAT_VERSION

NORMALIZED_STEP_PATH = "geometry/normalized.step"

_MOCK_ENTITIES: list[dict[str, Any]] = [
    {
        "id": "body_001",
        "type": "solid",
        "name": "mock_bracket_body",
        "bounding_box": [0.0, 0.0, 0.0, 120.0, 80.0, 50.0],
        "face_ids": [
            "face_base_top",
            "face_base_bottom",
            "face_base_front",
            "face_base_back",
            "face_left_flange",
            "face_right_flange",
            "face_hole_001_cyl",
            "face_hole_002_cyl",
            "face_hole_003_cyl",
            "face_hole_004_cyl",
        ],
    },
    {
        "id": "face_base_top",
        "type": "face",
        "surface_type": "plane",
        "body_id": "body_001",
        "bounding_box": [0.0, 0.0, 10.0, 120.0, 80.0, 10.0],
        "area": 9200.0,
        "normal": [0.0, 0.0, 1.0],
        "adjacent_entity_ids": ["face_base_front", "face_base_back", "face_left_flange", "face_right_flange"],
        "edge_ids": ["edge_base_front_top", "edge_base_back_top"],
    },
    {
        "id": "face_base_bottom",
        "type": "face",
        "surface_type": "plane",
        "body_id": "body_001",
        "bounding_box": [0.0, 0.0, 0.0, 120.0, 80.0, 0.0],
        "area": 9600.0,
        "normal": [0.0, 0.0, -1.0],
        "adjacent_entity_ids": ["face_base_front", "face_base_back"],
    },
    {
        "id": "face_base_front",
        "type": "face",
        "surface_type": "plane",
        "body_id": "body_001",
        "bounding_box": [0.0, 0.0, 0.0, 120.0, 0.0, 10.0],
        "area": 1200.0,
        "normal": [0.0, -1.0, 0.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_bottom"],
        "edge_ids": ["edge_base_front_top"],
    },
    {
        "id": "face_base_back",
        "type": "face",
        "surface_type": "plane",
        "body_id": "body_001",
        "bounding_box": [0.0, 80.0, 0.0, 120.0, 80.0, 10.0],
        "area": 1200.0,
        "normal": [0.0, 1.0, 0.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_bottom"],
        "edge_ids": ["edge_base_back_top"],
    },
    {
        "id": "face_left_flange",
        "type": "face",
        "surface_type": "plane",
        "body_id": "body_001",
        "bounding_box": [0.0, 0.0, 10.0, 10.0, 80.0, 50.0],
        "area": 3200.0,
        "normal": [-1.0, 0.0, 0.0],
        "adjacent_entity_ids": ["face_base_top"],
    },
    {
        "id": "face_right_flange",
        "type": "face",
        "surface_type": "plane",
        "body_id": "body_001",
        "bounding_box": [110.0, 0.0, 10.0, 120.0, 80.0, 50.0],
        "area": 3200.0,
        "normal": [1.0, 0.0, 0.0],
        "adjacent_entity_ids": ["face_base_top"],
    },
    {
        "id": "face_hole_001_cyl",
        "type": "face",
        "surface_type": "cylinder",
        "body_id": "body_001",
        "bounding_box": [15.0, 15.0, 0.0, 25.0, 25.0, 10.0],
        "area": 314.159,
        "radius": 5.0,
        "axis": [0.0, 0.0, 1.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_bottom"],
    },
    {
        "id": "face_hole_002_cyl",
        "type": "face",
        "surface_type": "cylinder",
        "body_id": "body_001",
        "bounding_box": [95.0, 15.0, 0.0, 105.0, 25.0, 10.0],
        "area": 314.159,
        "radius": 5.0,
        "axis": [0.0, 0.0, 1.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_bottom"],
    },
    {
        "id": "face_hole_003_cyl",
        "type": "face",
        "surface_type": "cylinder",
        "body_id": "body_001",
        "bounding_box": [15.0, 55.0, 0.0, 25.0, 65.0, 10.0],
        "area": 314.159,
        "radius": 5.0,
        "axis": [0.0, 0.0, 1.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_bottom"],
    },
    {
        "id": "face_hole_004_cyl",
        "type": "face",
        "surface_type": "cylinder",
        "body_id": "body_001",
        "bounding_box": [95.0, 55.0, 0.0, 105.0, 65.0, 10.0],
        "area": 314.159,
        "radius": 5.0,
        "axis": [0.0, 0.0, 1.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_bottom"],
    },
    {
        "id": "edge_base_front_top",
        "type": "edge",
        "curve_type": "line",
        "body_id": "body_001",
        "bounding_box": [0.0, 0.0, 10.0, 120.0, 0.0, 10.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_front"],
        "face_ids": ["face_base_top", "face_base_front"],
    },
    {
        "id": "edge_base_back_top",
        "type": "edge",
        "curve_type": "line",
        "body_id": "body_001",
        "bounding_box": [0.0, 80.0, 10.0, 120.0, 80.0, 10.0],
        "adjacent_entity_ids": ["face_base_top", "face_base_back"],
        "face_ids": ["face_base_top", "face_base_back"],
    },
]


@runtime_checkable
class GeometryBackend(Protocol):
    """Protocol for pluggable geometry extraction backends."""

    name: str

    def extract_topology(self, normalized_step_bytes: bytes) -> dict[str, Any]:
        """Return a topology map for normalized STEP bytes."""


class MockGeometryBackend:
    """Deterministic mock backend for Phase 2–7A tests and demos.

    Does not inspect or parse STEP content. Returns a fixed bracket-like
    topology map with stable IDs and Phase 7A backend metadata fields.
    """

    name: str = "mock"

    def extract_topology(self, normalized_step_bytes: bytes) -> dict[str, Any]:
        _ = normalized_step_bytes
        return {
            "format_version": FORMAT_VERSION,
            "metadata": {
                "extractor": "MockGeometryBackend",
                "extraction_backend": "mock",
                "extraction_mode": "mock_generated",
                "real_step_parsing": False,
                "source_geometry": NORMALIZED_STEP_PATH,
                "adjacency_evidence": "mock",
                "limitations": [
                    "Mock topology only; no STEP parsing performed.",
                    "IDs are deterministic within this fixture, not derived from CAD kernel persistent naming.",
                ],
            },
            "entities": list(_MOCK_ENTITIES),
        }


class OCCGeometryBackend:
    """OCC geometry backend.

    Phase 7B.1: detects optional OCC runtime without importing it.
    Phase 7B.2: performs experimental real STEP extraction when OCP/CadQuery is installed.
    """

    name: str = "occ"

    def extract_topology(self, normalized_step_bytes: bytes) -> dict[str, Any]:
        runtime = detect_occ_runtime()
        if not runtime["available"]:
            raise NotImplementedError(
                "OCC geometry backend requires an optional geometry dependency. "
                "Install OCP/CadQuery: pip install cadquery "
                "(or pip install aieng-format[geometry] once the extra is populated). "
                "Real STEP extraction (Phase 7B.2) requires OCP. "
                f"Detection result: {runtime['message']}"
            )
        if runtime["provider"] == "pythonocc-core":
            raise NotImplementedError(
                "pythonocc-core is detected but Phase 7B.2 only implements OCP/CadQuery-based "
                "STEP extraction. Install CadQuery instead: pip install cadquery"
            )
        return _extract_topology_ocp(normalized_step_bytes)


def detect_occ_runtime() -> dict[str, Any]:
    """Detect available OCC geometry runtime without importing heavy modules.

    Uses importlib.util.find_spec to check package availability without side effects.
    Checks OCP (CadQuery) first because Phase 7B.2 implements OCP extraction.
    Returns a dict with keys: available (bool), provider (str | None), message (str).
    """
    if importlib.util.find_spec("OCP") is not None:
        return {
            "available": True,
            "provider": "OCP",
            "message": "OCP import succeeded",
        }
    if importlib.util.find_spec("OCC") is not None:
        return {
            "available": True,
            "provider": "pythonocc-core",
            "message": "OCC.Core import succeeded",
        }
    return {
        "available": False,
        "provider": None,
        "message": "No supported OCC runtime found. Install pythonocc-core or OCP/CadQuery.",
    }


def _extract_topology_ocp(normalized_step_bytes: bytes) -> dict[str, Any]:
    """Perform real STEP topology extraction using OCP (Phase 7B.2 spike).

    All OCP imports are lazy — no OCP module is imported at module load time.
    Writes bytes to a temporary file for OCP's file-based reader, then removes it.
    """
    import os
    import tempfile

    try:
        from OCP.STEPControl import STEPControl_Reader
        from OCP.IFSelect import IFSelect_RetDone
    except ImportError as exc:
        raise NotImplementedError(
            f"OCP module import failed despite runtime detection: {exc}. "
            "Try reinstalling: pip install cadquery"
        ) from exc

    fd, temp_path = tempfile.mkstemp(suffix=".step")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(normalized_step_bytes)

        reader = STEPControl_Reader()
        status = reader.ReadFile(temp_path)
        if status != IFSelect_RetDone:
            raise ValueError(
                f"OCC/OCP STEPControl_Reader failed to read STEP data (status={status}). "
                "The file may be malformed or contain unsupported STEP entities."
            )

        n_roots = reader.NbRootsForTransfer()
        if n_roots == 0:
            raise ValueError(
                "OCC/OCP found no transferable shapes in the STEP file. "
                "The file may be empty or contain only non-geometry data."
            )

        reader.TransferRoots()
        shape = reader.OneShape()

    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    entities = _build_entities_ocp(shape)

    if not any(e["type"] in ("solid", "face") for e in entities):
        raise ValueError(
            "OCC/OCP extracted no solid or face entities from the STEP data. "
            "The shape may be empty or contain unsupported geometry types."
        )

    return {
        "format_version": FORMAT_VERSION,
        "metadata": {
            "extraction_backend": "occ",
            "runtime_provider": "OCP",
            "extraction_mode": "parsed_from_step",
            "real_step_parsing": True,
            "source_geometry": NORMALIZED_STEP_PATH,
            "adjacency_evidence": "real",
            "phase": "7B.2",
            "limitations": [
                "experimental OCP-based topology extraction",
                "stable IDs are deterministic only for this backend traversal order",
                "feature recognition remains separate and rule-based",
                "geometry validity is not fully certified",
            ],
        },
        "entities": entities,
    }


def _build_entities_ocp(shape: Any) -> list[dict[str, Any]]:
    """Traverse an OCP shape and build a list of topology entity dicts.

    All OCP imports are lazy. Properties that cannot be computed are omitted
    rather than invented. Uses TopTools_IndexedMapOfShape / MapShapesAndAncestors
    for orientation-independent, stable edge→face adjacency mapping.
    """
    from OCP.TopExp import TopExp_Explorer, TopExp
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import (
        TopTools_IndexedMapOfShape,
        TopTools_IndexedDataMapOfShapeListOfShape,
    )
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    entities: list[dict[str, Any]] = []

    def _add_bbox(obj: Any, box: Any) -> None:
        try:
            BRepBndLib.Add_s(obj, box)
        except AttributeError:
            BRepBndLib.Add(obj, box)

    def _surface(face: Any) -> Any:
        try:
            return BRep_Tool.Surface_s(face)
        except AttributeError:
            return BRep_Tool.Surface(face)

    def _surface_props(face: Any, props: Any) -> None:
        try:
            BRepGProp.SurfaceProperties_s(face, props)
        except AttributeError:
            BRepGProp.SurfaceProperties(face, props)

    def _cast_solid(s: Any) -> Any:
        try:
            return TopoDS.Solid_s(s)
        except AttributeError:
            return TopoDS.Solid(s)

    def _cast_face(s: Any) -> Any:
        try:
            return TopoDS.Face_s(s)
        except AttributeError:
            return TopoDS.Face(s)

    def bbox_of(obj: Any) -> list[float] | None:
        try:
            box = Bnd_Box()
            _add_bbox(obj, box)
            return list(box.Get())
        except Exception:
            return None

    # --- Solids ---
    solid_count = 0
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solid_count += 1
        body_id = f"body_{solid_count:03d}"
        try:
            solid = _cast_solid(exp.Current())
        except Exception:
            solid = exp.Current()
        entity: dict[str, Any] = {"id": body_id, "type": "solid"}
        bb = bbox_of(solid)
        if bb:
            entity["bounding_box"] = bb
        entities.append(entity)
        exp.Next()

    # If no explicit solids, treat the root shape as one body.
    if solid_count == 0:
        entity = {"id": "body_001", "type": "solid"}
        bb = bbox_of(shape)
        if bb:
            entity["bounding_box"] = bb
        entities.append(entity)

    dominant_body_id = f"body_{solid_count:03d}" if solid_count > 0 else "body_001"

    # --- Build stable edge and face maps using TopTools (orientation-independent) ---
    # TopTools_IndexedMapOfShape assigns stable 1-based indices to each unique shape.
    edge_map = TopTools_IndexedMapOfShape()
    face_map = TopTools_IndexedMapOfShape()
    try:
        TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
    except AttributeError:
        TopExp.MapShapes(shape, TopAbs_EDGE, edge_map)
        TopExp.MapShapes(shape, TopAbs_FACE, face_map)

    # edge_to_face_map: for each edge, list of adjacent faces
    edge_to_face_ttools: TopTools_IndexedDataMapOfShapeListOfShape = (
        TopTools_IndexedDataMapOfShapeListOfShape()
    )
    try:
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_to_face_ttools)
    except AttributeError:
        TopExp.MapShapesAndAncestors(shape, TopAbs_EDGE, TopAbs_FACE, edge_to_face_ttools)

    # Build edge index → edge_id mapping (1-based TopTools indices)
    edge_idx_to_id: dict[int, str] = {}
    edge_entities: list[dict[str, Any]] = []
    for i in range(1, edge_map.Size() + 1):
        edge_id = f"edge_{i:03d}"
        edge_idx_to_id[i] = edge_id
        edge = edge_map.FindKey(i)
        entity = {"id": edge_id, "type": "edge"}
        bb = bbox_of(edge)
        if bb:
            entity["bounding_box"] = bb
        edge_entities.append(entity)

    # Build face index → face_id mapping
    face_idx_to_id: dict[int, str] = {}
    face_entities: list[dict[str, Any]] = []
    for i in range(1, face_map.Size() + 1):
        face_id = f"face_{i:03d}"
        face_idx_to_id[i] = face_id
        face = _cast_face(face_map.FindKey(i))
        entity = {"id": face_id, "type": "face", "body_id": dominant_body_id}

        bb = bbox_of(face)
        if bb:
            entity["bounding_box"] = bb

        try:
            props = GProp_GProps()
            _surface_props(face, props)
            area = props.Mass()
            if area > 0:
                entity["area"] = area
        except Exception:
            pass

        try:
            surf = _surface(face)
            if surf is not None:
                adaptor = GeomAdaptor_Surface(surf)
                surf_type = adaptor.GetType()
                if surf_type == GeomAbs_Plane:
                    entity["surface_type"] = "plane"
                    try:
                        d = adaptor.Plane().Axis().Direction()
                        entity["normal"] = [d.X(), d.Y(), d.Z()]
                    except Exception:
                        pass
                elif surf_type == GeomAbs_Cylinder:
                    entity["surface_type"] = "cylinder"
                    try:
                        cyl = adaptor.Cylinder()
                        entity["radius"] = cyl.Radius()
                        ax = cyl.Axis().Direction()
                        entity["axis"] = [ax.X(), ax.Y(), ax.Z()]
                    except Exception:
                        pass
                else:
                    surf_name = str(surf_type).lower()
                    if "bspline" in surf_name:
                        entity["surface_type"] = "bspline"
                    elif "bezier" in surf_name:
                        entity["surface_type"] = "bezier"
                    elif "sphere" in surf_name:
                        entity["surface_type"] = "sphere"
                    elif "cone" in surf_name:
                        entity["surface_type"] = "cone"
                    elif "torus" in surf_name:
                        entity["surface_type"] = "torus"
                    elif "revolution" in surf_name:
                        entity["surface_type"] = "surface_of_revolution"
                    elif "extrusion" in surf_name:
                        entity["surface_type"] = "surface_of_extrusion"
                    else:
                        entity["surface_type"] = "freeform"
                    entity["freeform"] = True
                    try:
                        entity["uv_bounds"] = [
                            float(adaptor.FirstUParameter()),
                            float(adaptor.LastUParameter()),
                            float(adaptor.FirstVParameter()),
                            float(adaptor.LastVParameter()),
                        ]
                    except Exception:
                        pass
        except Exception:
            pass

        face_entities.append(entity)

    # --- Build edge→faces and face→edges from edge_to_face_ttools ---
    edge_to_faces: dict[str, list[str]] = {}
    face_to_edges: dict[str, set[str]] = {fid: set() for fid in face_idx_to_id.values()}
    face_adjacent: dict[str, set[str]] = {fid: set() for fid in face_idx_to_id.values()}

    for i in range(1, edge_to_face_ttools.Size() + 1):
        edge_shape = edge_to_face_ttools.FindKey(i)
        face_list = edge_to_face_ttools.FindFromIndex(i)

        # Find which edge_id this corresponds to
        try:
            edge_idx = edge_map.FindIndex(edge_shape)
        except Exception:
            continue
        edge_id = edge_idx_to_id.get(edge_idx)
        if edge_id is None:
            continue

        adj_face_ids: list[str] = []
        for face_shape_item in face_list:
            try:
                face_idx = face_map.FindIndex(face_shape_item)
            except Exception:
                continue
            fid = face_idx_to_id.get(face_idx)
            if fid:
                adj_face_ids.append(fid)
                face_to_edges[fid].add(edge_id)

        if adj_face_ids:
            edge_to_faces[edge_id] = sorted(adj_face_ids)
            # Build face adjacency through shared edges
            sorted_fids = sorted(adj_face_ids)
            for idx_a, fa in enumerate(sorted_fids):
                for fb in sorted_fids[idx_a + 1:]:
                    face_adjacent[fa].add(fb)
                    face_adjacent[fb].add(fa)

    # Annotate edge entities
    for edge_entity in edge_entities:
        eid = edge_entity["id"]
        if eid in edge_to_faces:
            edge_entity["face_ids"] = edge_to_faces[eid]
            edge_entity["adjacent_entity_ids"] = edge_to_faces[eid]

    # Annotate face entities
    for face_entity in face_entities:
        fid = face_entity["id"]
        e_ids = sorted(face_to_edges.get(fid, set()))
        if e_ids:
            face_entity["edge_ids"] = e_ids
        adj = sorted(face_adjacent.get(fid, set()))
        if adj:
            face_entity["adjacent_entity_ids"] = adj

    entities.extend(face_entities)
    entities.extend(edge_entities)
    return entities


SUPPORTED_BACKENDS: dict[str, type[MockGeometryBackend | OCCGeometryBackend]] = {
    "mock": MockGeometryBackend,
    "occ": OCCGeometryBackend,
}


def get_backend(name: str) -> MockGeometryBackend | OCCGeometryBackend:
    """Return an instantiated backend for the given name.

    Raises ValueError for unknown backend names.
    """
    backend_cls = SUPPORTED_BACKENDS.get(name)
    if backend_cls is None:
        supported = ", ".join(sorted(SUPPORTED_BACKENDS))
        raise ValueError(f"Unknown geometry backend {name!r}. Supported backends: {supported}")
    return backend_cls()
