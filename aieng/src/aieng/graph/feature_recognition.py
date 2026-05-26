from __future__ import annotations

from typing import Any

from aieng import FORMAT_VERSION

NUMERIC_TYPES = (int, float)


class RuleBasedFeatureRecognizer:
    """Deterministic Phase 3 recognizer that works only from topology_map.json."""

    def recognize(self, topology_map: dict[str, Any], aag: dict[str, Any] | None = None) -> dict[str, Any]:
        entities = [entity for entity in topology_map.get("entities", []) if isinstance(entity, dict)]
        faces = [entity for entity in entities if entity.get("type") == "face"]
        edges = [entity for entity in entities if entity.get("type") == "edge"]
        aag_face_index = self._aag_face_index(aag)
        recognition_context = self._recognition_context(topology_map)

        features: list[dict[str, Any]] = []
        referenced_faces: set[str] = set()
        referenced_edges: set[str] = set()

        base_feature = self._base_plate_feature(faces, aag_face_index, recognition_context)
        if base_feature is not None:
            features.append(base_feature)
            referenced_faces.update(base_feature["geometry_refs"].get("faces", []))

        hole_features = self._hole_features(faces, aag_face_index, recognition_context)
        features.extend(hole_features)
        for feature in hole_features:
            referenced_faces.update(feature["geometry_refs"].get("faces", []))

        pattern_feature = self._hole_pattern_feature(hole_features, recognition_context)
        if pattern_feature is not None:
            features.append(pattern_feature)
            referenced_faces.update(pattern_feature["geometry_refs"].get("faces", []))

        unknown_feature = self._unknown_feature(faces, edges, referenced_faces, referenced_edges, recognition_context)
        if unknown_feature is not None:
            features.append(unknown_feature)

        return {
            "format_version": FORMAT_VERSION,
            "metadata": {
                "recognizer": "RuleBasedFeatureRecognizer",
                "source": "geometry/topology_map.json",
                "limitations": [
                    "Rule-based candidate recognition only.",
                    "Features are not guaranteed engineering truth.",
                    "No CAD kernel, STEP parsing, machine learning, or LLM calls were used.",
                ],
                "aag_used": bool(aag_face_index),
                "recognition_profile": (
                    "real_topology_quality_rules_v1"
                    if recognition_context["real_topology"]
                    else "mock_topology_baseline_rules_v1"
                ),
            },
            "features": features,
        }

    def _recognition_context(self, topology_map: dict[str, Any]) -> dict[str, bool]:
        metadata = topology_map.get("metadata") if isinstance(topology_map, dict) else None
        if not isinstance(metadata, dict):
            return {"real_topology": False}
        return {
            "real_topology": metadata.get("real_step_parsing") is True and metadata.get("extraction_backend") == "occ"
        }

    def _base_plate_feature(
        self,
        faces: list[dict[str, Any]],
        aag_face_index: dict[str, dict[str, Any]],
        recognition_context: dict[str, bool],
    ) -> dict[str, Any] | None:
        planar_faces = [
            face for face in faces
            if face.get("surface_type") == "plane" and isinstance(face.get("area"), NUMERIC_TYPES)
        ]
        if not planar_faces:
            return None
        largest = max(planar_faces, key=lambda face: (float(face.get("area", 0.0)), str(face.get("id", ""))))
        feature = {
            "id": "feat_base_plate_001",
            "type": "base_plate",
            "name": "Base plate candidate",
            "geometry_refs": {"faces": [largest["id"]]},
            "parameters": {"area_mm2": largest.get("area")},
            "parameter_source": "mock",
            "parameter_confidence": "low",
            "editable": True,
            "editability": "semantic_only",
            "writeback_strategy": "semantic_parameter_update_only",
            "editability_reason": (
                "Rule-based/mock parameter exposed for AI understanding and semantic patching only; "
                "no executable CAD regeneration source is attached."
            ),
            "intent": {"role": "structural_base_candidate"},
            "recognition": {
                "method": "rule_based_largest_planar_face",
                "confidence": "medium",
                "uncertainty_notes": [
                    "Largest planar face is a structural-base candidate, not confirmed design intent.",
                    "Candidate should be reviewed against user intent and CAD semantics before writeback.",
                ],
            },
        }
        if recognition_context.get("real_topology"):
            feature["recognition"]["signals"] = {
                "real_topology": True,
                "has_area": isinstance(largest.get("area"), NUMERIC_TYPES),
                "aag_neighbors": len(aag_face_index.get(str(largest.get("id")), {}).get("adjacent_face_ids", set())),
            }
        self._attach_aag_metadata(feature, largest.get("id"), aag_face_index)
        return feature

    def _hole_features(
        self,
        faces: list[dict[str, Any]],
        aag_face_index: dict[str, dict[str, Any]],
        recognition_context: dict[str, bool],
    ) -> list[dict[str, Any]]:
        cylindrical_faces = sorted(
            [
                face for face in faces
                if face.get("surface_type") == "cylinder" and isinstance(face.get("radius"), NUMERIC_TYPES)
            ],
            key=lambda face: str(face.get("id", "")),
        )
        features: list[dict[str, Any]] = []
        for index, face in enumerate(cylindrical_faces, start=1):
            radius = float(face["radius"])
            feature = {
                "id": f"feat_hole_{index:03d}",
                "type": "mounting_hole",
                "name": "Cylindrical hole candidate",
                "geometry_refs": {"faces": [face["id"]]},
                "parameters": {
                    "radius_mm": radius,
                    "diameter_mm": radius * 2.0,
                },
                "parameter_source": "mock",
                "parameter_confidence": "low",
                "editable": True,
                "editability": "semantic_only",
                "writeback_strategy": "semantic_parameter_update_only",
                "editability_reason": (
                    "Cylinder radius was exposed as a semantic candidate parameter; "
                    "editing it does not imply arbitrary STEP/OCP geometry write-back."
                ),
                "intent": {"role": "mounting_or_passage_candidate"},
                "recognition": {
                    "method": "rule_based_cylindrical_face",
                    "confidence": "medium" if self._is_numeric_vec3(face.get("axis")) else "low",
                    "uncertainty_notes": [
                        "Cylindrical face may represent mounting hole, passage, or other cylindrical feature.",
                        "No CAD feature history was used; semantics remain candidate-level.",
                    ],
                },
            }
            if recognition_context.get("real_topology"):
                feature["recognition"]["signals"] = {
                    "real_topology": True,
                    "axis_available": self._is_numeric_vec3(face.get("axis")),
                    "radius_positive": radius > 0,
                }
            self._attach_aag_metadata(feature, face.get("id"), aag_face_index)
            features.append(feature)
        return features

    def _is_numeric_vec3(self, value: Any) -> bool:
        return isinstance(value, list) and len(value) == 3 and all(isinstance(item, NUMERIC_TYPES) for item in value)

    def _attach_aag_metadata(
        self,
        feature: dict[str, Any],
        face_id: Any,
        aag_face_index: dict[str, dict[str, Any]],
    ) -> None:
        if not isinstance(face_id, str):
            return
        aag_entry = aag_face_index.get(face_id)
        if aag_entry is None:
            return
        recognition = feature.setdefault("recognition", {})
        if isinstance(recognition, dict):
            recognition["aag_node_ids"] = [aag_entry["node_id"]]
            recognition["adjacent_face_ids"] = sorted(aag_entry["adjacent_face_ids"])

    def _aag_face_index(self, aag: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not isinstance(aag, dict):
            return {}
        nodes = aag.get("nodes")
        arcs = aag.get("arcs")
        if not isinstance(nodes, list) or not isinstance(arcs, list):
            return {}

        face_to_node: dict[str, str] = {}
        node_to_face: dict[str, str] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            face_id = node.get("topology_entity_id")
            if isinstance(node_id, str) and isinstance(face_id, str):
                face_to_node[face_id] = node_id
                node_to_face[node_id] = face_id

        face_adjacency: dict[str, set[str]] = {face_id: set() for face_id in face_to_node}
        for arc in arcs:
            if not isinstance(arc, dict):
                continue
            source_node = arc.get("source_node")
            target_node = arc.get("target_node")
            if not isinstance(source_node, str) or not isinstance(target_node, str):
                continue
            source_face = node_to_face.get(source_node)
            target_face = node_to_face.get(target_node)
            if source_face and target_face and source_face != target_face:
                face_adjacency[source_face].add(target_face)
                face_adjacency[target_face].add(source_face)

        result: dict[str, dict[str, Any]] = {}
        for face_id, node_id in face_to_node.items():
            result[face_id] = {
                "node_id": node_id,
                "adjacent_face_ids": face_adjacency.get(face_id, set()),
            }
        return result

    def _hole_pattern_feature(
        self,
        hole_features: list[dict[str, Any]],
        recognition_context: dict[str, bool],
    ) -> dict[str, Any] | None:
        if len(hole_features) < 2:
            return None

        groups: dict[float, list[dict[str, Any]]] = {}
        for feature in hole_features:
            radius = feature.get("parameters", {}).get("radius_mm")
            if isinstance(radius, NUMERIC_TYPES):
                groups.setdefault(round(float(radius), 3), []).append(feature)

        if not groups:
            return None
        _, grouped_features = max(groups.items(), key=lambda item: (len(item[1]), -item[0]))
        if len(grouped_features) < 2:
            return None

        children = [feature["id"] for feature in grouped_features]
        face_ids: list[str] = []
        diameters: set[float] = set()
        for feature in grouped_features:
            face_ids.extend(feature.get("geometry_refs", {}).get("faces", []))
            diameter = feature.get("parameters", {}).get("diameter_mm")
            if isinstance(diameter, NUMERIC_TYPES):
                diameters.add(round(float(diameter), 3))

        parameters: dict[str, Any] = {"count": len(grouped_features)}
        if len(diameters) == 1:
            parameters["diameter_mm"] = sorted(diameters)[0]

        all_axis_available = True
        for feature in grouped_features:
            signals = feature.get("recognition", {}).get("signals") if isinstance(feature.get("recognition"), dict) else None
            if not isinstance(signals, dict) or signals.get("axis_available") is not True:
                all_axis_available = False
                break

        high_confidence = (
            recognition_context.get("real_topology")
            and len(grouped_features) >= 4
            and len(diameters) == 1
            and all_axis_available
        )

        return {
            "id": "feat_hole_pattern_001",
            "type": "mounting_hole_pattern",
            "name": "Cylindrical hole pattern candidate",
            "geometry_refs": {"faces": sorted(set(face_ids))},
            "children": children,
            "parameters": parameters,
            "parameter_source": "mock",
            "parameter_confidence": "low",
            "editable": True,
            "editability": "semantic_only",
            "writeback_strategy": "semantic_parameter_update_only",
            "editability_reason": (
                "Hole-pattern parameters support semantic proposals and protected-region checks only; "
                "CAD write-back requires an explicit parametric regeneration source."
            ),
            "intent": {"role": "mounting_interface_candidate"},
            "recognition": {
                "method": "rule_based_grouped_cylindrical_faces",
                "confidence": "high" if high_confidence else "medium",
                "uncertainty_notes": [
                    "Pattern grouping is geometric and does not prove manufacturing intent by itself.",
                    "Pattern should be confirmed against interfaces/constraints before execution.",
                ],
                "signals": {
                    "real_topology": bool(recognition_context.get("real_topology")),
                    "hole_count": len(grouped_features),
                    "single_diameter_group": len(diameters) == 1,
                    "axis_available_for_all_holes": all_axis_available,
                },
            },
        }

    def _unknown_feature(
        self,
        faces: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        referenced_faces: set[str],
        referenced_edges: set[str],
        recognition_context: dict[str, bool],
    ) -> dict[str, Any] | None:
        remaining_faces = sorted(
            str(face["id"]) for face in faces
            if isinstance(face.get("id"), str) and face["id"] not in referenced_faces
        )
        remaining_edges = sorted(
            str(edge["id"]) for edge in edges
            if isinstance(edge.get("id"), str) and edge["id"] not in referenced_edges
        )
        if not remaining_faces and not remaining_edges:
            return None

        return {
            "id": "feat_unknown_001",
            "type": "unknown_feature",
            "name": "Unclassified topology entities",
            "geometry_refs": {
                "faces": remaining_faces,
                "edges": remaining_edges,
            },
            "parameters": {},
            "parameter_source": "mock",
            "parameter_confidence": "low",
            "editable": False,
            "editability": "not_editable",
            "writeback_strategy": "none",
            "editability_reason": "Unclassified fallback geometry has no safe parameterized edit handle.",
            "intent": {"role": "unclassified_geometry"},
            "recognition": {
                "method": "fallback_unclassified_entities",
                "confidence": "low",
                "uncertainty_notes": [
                    "Unclassified entities require manual review or improved recognition rules.",
                ],
                "signals": {
                    "real_topology": bool(recognition_context.get("real_topology")),
                    "remaining_faces": len(remaining_faces),
                    "remaining_edges": len(remaining_edges),
                },
            },
        }
