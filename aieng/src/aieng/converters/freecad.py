"""FreeCAD reference converter (Phase 20).

Two modes:

* **offline** — parses the FCStd file as a zip + Document.xml. Requires no
  FreeCAD installation. Reaches at most L0 + L2 + L3-candidate (heuristic
  feature naming) because the underlying B-rep geometry cannot be reliably
  traversed without FreeCAD/OCC.
* **runtime** — uses the FreeCAD Python API when importable. Currently the
  reference path detects runtime availability and still defers actual STEP
  export + topology extraction to ``aieng extract-topology --backend occ``
  on the converted package; the converter itself does not run FreeCAD GUI
  operations or modify geometry.

The converter writes no solver, mesh, or CAD-edit evidence. It only converts
what FCStd actually exposes.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aieng import FORMAT_VERSION

from .base import (
    CAPABILITY_LEVEL_NAMES,
    ConversionResult,
    Converter,
    ConverterCapabilityProfile,
    ConverterError,
    CoverageCategory,
    EmittedResource,
    SupportedLevel,
    UncertaintyNote,
    UnsupportedItem,
)


_MOUNTING_HOLE_PATTERNS = (
    re.compile(r"mounting.?hole", re.IGNORECASE),
    re.compile(r"^hole[_\d]", re.IGNORECASE),
)

_HOLE_PATTERNS = (
    re.compile(r"hole", re.IGNORECASE),
    re.compile(r"bore", re.IGNORECASE),
)

_BASE_PLATE_PATTERNS = (
    re.compile(r"base.?plate", re.IGNORECASE),
    re.compile(r"plate", re.IGNORECASE),
    re.compile(r"^body$", re.IGNORECASE),
)

_FLANGE_PATTERNS = (
    re.compile(r"flange", re.IGNORECASE),
)

_RIB_PATTERNS = (
    re.compile(r"rib", re.IGNORECASE),
)

_FILLET_PATTERNS = (
    re.compile(r"fillet", re.IGNORECASE),
    re.compile(r"round", re.IGNORECASE),
)


class FreeCADConverter:
    """Offline-capable FreeCAD reference converter."""

    converter_id = "freecad_reference"
    source_system = "FreeCAD"
    display_name = "FreeCAD reference converter"
    converter_version = "0.1.0"

    def capability_profile(self) -> ConverterCapabilityProfile:
        levels = (
            SupportedLevel(
                level=0,
                name=CAPABILITY_LEVEL_NAMES[0],
                supported=True,
                notes=("Always: records source FCStd metadata, byte size, sha256.",),
            ),
            SupportedLevel(
                level=1,
                name=CAPABILITY_LEVEL_NAMES[1],
                supported=False,
                conditional_requirements=(
                    "FreeCAD runtime importable AND OCC/CadQuery installed",
                    "Or a STEP export performed externally and imported via aieng import-step",
                ),
                notes=(
                    "Offline FCStd parsing does not produce stable topology IDs. "
                    "Run `aieng extract-topology --backend occ` on a STEP export instead.",
                ),
            ),
            SupportedLevel(
                level=2,
                name=CAPABILITY_LEVEL_NAMES[2],
                supported=True,
                notes=(
                    "Object registry is built from FCStd Document.xml object names.",
                ),
            ),
            SupportedLevel(
                level=3,
                name=CAPABILITY_LEVEL_NAMES[3],
                supported=True,
                notes=(
                    "Feature candidates derived from heuristic naming rules. "
                    "All features are marked with recognition.confidence='medium' "
                    "or 'low' and an explicit uncertainty note; they are NOT "
                    "treated as confirmed CAD feature truth.",
                ),
            ),
            SupportedLevel(
                level=4,
                name=CAPABILITY_LEVEL_NAMES[4],
                supported=True,
                notes=(
                    "Editability metadata is recorded for FCStd parameters "
                    "(parameter_source='freecad_property', writeback_strategy='none'). "
                    "The converter does NOT perform any edit.",
                ),
            ),
            SupportedLevel(
                level=5,
                name=CAPABILITY_LEVEL_NAMES[5],
                supported=False,
                conditional_requirements=(
                    "Future FreeCAD scripted-rebuild adapter (out of scope for the reference converter)",
                ),
                notes=(
                    "Writeback strategy metadata is not yet emitted by this reference converter; "
                    "the contract is in place for future implementations.",
                ),
            ),
        )
        return ConverterCapabilityProfile(
            converter_id=self.converter_id,
            source_system=self.source_system,
            supported_levels=levels,
            display_name=self.display_name,
            converter_version=self.converter_version,
            source_file_extensions=(".FCStd", ".fcstd"),
            notes=(
                "Reference converter — intentionally narrow. Other FreeCAD adapters may extend or replace it.",
                "Never runs solvers, meshers, optimizers, or CAD edits.",
            ),
        )

    def convert(
        self,
        source_path: Path,
        *,
        model_id: str,
        runtime_mode: str = "auto",
        options: Mapping[str, Any] | None = None,
    ) -> ConversionResult:
        if not source_path.exists():
            raise ConverterError(f"source file does not exist: {source_path}")
        if not source_path.is_file():
            raise ConverterError(f"source path is not a file: {source_path}")

        resolved_mode = self._resolve_runtime_mode(runtime_mode)

        try:
            with zipfile.ZipFile(source_path, mode="r") as archive:
                if "Document.xml" not in set(archive.namelist()):
                    raise ConverterError(
                        f"source file is not a recognizable FCStd archive (missing Document.xml): {source_path}"
                    )
                document_xml = archive.read("Document.xml")
        except zipfile.BadZipFile as exc:
            raise ConverterError(f"source file is not a valid FCStd zip archive: {source_path}") from exc

        parsed = _parse_fcstd_document(document_xml)

        sha = hashlib.sha256(source_path.read_bytes()).hexdigest()

        object_registry, registry_uncertainty = _build_object_registry(parsed["objects"])
        feature_graph, feature_uncertainty, feature_unsupported = _build_feature_graph(parsed["objects"])

        package_files: dict[str, bytes] = {}
        emitted: list[EmittedResource] = []

        package_files["objects/object_registry.json"] = (
            json.dumps(object_registry, indent=2, sort_keys=True) + "\n"
        ).encode()
        emitted.append(EmittedResource(
            path="objects/object_registry.json",
            kind="object_registry",
            level=2,
        ))

        package_files["graph/feature_graph.json"] = (
            json.dumps(feature_graph, indent=2, sort_keys=True) + "\n"
        ).encode()
        emitted.append(EmittedResource(
            path="graph/feature_graph.json",
            kind="feature_graph",
            level=3,
        ))

        readme = _build_readme(parsed, source_path, sha)
        package_files["README_FOR_AI.md"] = readme.encode()

        # Source FCStd is recorded as a referenced artifact for traceability,
        # but we do not copy the binary into geometry/source.step (that path is
        # reserved for STEP). We expose the source bytes under provenance/.
        package_files["provenance/source.fcstd"] = source_path.read_bytes()
        emitted.append(EmittedResource(
            path="provenance/source.fcstd",
            kind="geometry",
            level=0,
            notes=("Original FCStd archive preserved for traceability.",),
        ))

        unsupported = list(feature_unsupported) + [
            UnsupportedItem(
                category="topology",
                status="missing",
                description=(
                    "Offline FCStd parsing cannot produce stable face/edge/body IDs. "
                    "Run aieng extract-topology --backend occ on a STEP export to reach L1."
                ),
            ),
            UnsupportedItem(
                category="simulation_setup",
                status="missing",
                description="FCStd Document.xml does not carry simulation setup; provide it externally if needed.",
            ),
            UnsupportedItem(
                category="materials",
                status="missing",
                description="FreeCAD material data was not extracted by the reference converter; provide externally if needed.",
            ),
            UnsupportedItem(
                category="protected_regions",
                status="missing",
                description="Protected regions must be provided by the engineer; not inferred from FCStd alone.",
            ),
            UnsupportedItem(
                category="writeback_strategy",
                status="unsupported",
                description="Reference converter does not emit writeback strategy metadata at L5.",
            ),
        ]

        uncertainty = list(registry_uncertainty) + list(feature_uncertainty)
        if not parsed["objects"]:
            uncertainty.append(UncertaintyNote(
                scope="source_metadata",
                description="FCStd Document.xml contained zero objects.",
            ))

        declared_levels = (
            SupportedLevel(level=0, name=CAPABILITY_LEVEL_NAMES[0]),
            SupportedLevel(level=2, name=CAPABILITY_LEVEL_NAMES[2]),
            SupportedLevel(level=3, name=CAPABILITY_LEVEL_NAMES[3]),
            SupportedLevel(level=4, name=CAPABILITY_LEVEL_NAMES[4]),
        )
        achieved_levels = list(declared_levels)
        if not parsed["objects"]:
            # No feature candidates means we did not actually reach L3.
            achieved_levels = [
                level
                for level in achieved_levels
                if level.level in {0, 2}
            ]
        if not any(
            isinstance(feature.get("parameters"), dict) and feature["parameters"]
            for feature in feature_graph.get("features", [])
        ):
            # No editable parameters extracted -> did not reach L4.
            achieved_levels = [
                level for level in achieved_levels if level.level != 4
            ]

        coverage = _build_coverage_categories(
            parsed=parsed,
            feature_graph=feature_graph,
            resolved_mode=resolved_mode,
        )

        return ConversionResult(
            model_id=model_id,
            converter_id=self.converter_id,
            source_system=self.source_system,
            converter_version=self.converter_version,
            display_name=self.display_name,
            runtime_mode=resolved_mode,
            source_filename=source_path.name,
            source_byte_size=source_path.stat().st_size,
            source_content_sha256=sha,
            source_document_metadata=parsed["document_metadata"],
            declared_levels=declared_levels,
            achieved_levels=tuple(achieved_levels),
            emitted_resources=emitted,
            unsupported=unsupported,
            uncertainty=uncertainty,
            coverage_categories=coverage,
            package_files=package_files,
            notes=(
                f"Converted from FCStd source via {self.converter_id} (runtime_mode={resolved_mode}).",
                "No solver, mesher, optimizer, or CAD edit was executed by the converter.",
            ),
        )

    @staticmethod
    def _resolve_runtime_mode(requested: str) -> str:
        if requested == "offline":
            return "offline"
        if requested == "runtime":
            return "runtime" if _freecad_runtime_available() else "offline"
        # auto
        return "runtime" if _freecad_runtime_available() else "offline"


def _freecad_runtime_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("FreeCAD") is not None
    except Exception:  # pragma: no cover - defensive
        return False


def _parse_fcstd_document(document_xml: bytes) -> dict[str, Any]:
    """Parse FCStd Document.xml into a small structured dict.

    Returns ``{"document_metadata": {...}, "objects": [...]}`` where each
    object has ``{"name": str, "type": str, "id": str | None, "label": str | None,
    "properties": {str: Any}}``.
    """
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise ConverterError(f"FCStd Document.xml is not valid XML: {exc}") from exc

    document_metadata: dict[str, Any] = {}
    for key in ("SchemaVersion", "ProgramVersion", "FileVersion"):
        value = root.attrib.get(key)
        if value:
            document_metadata[key.lower()] = value

    object_entries: dict[str, dict[str, Any]] = {}

    objects_block = root.find("Objects")
    if objects_block is not None:
        for obj in objects_block.findall("Object"):
            name = obj.attrib.get("name")
            if not name:
                continue
            object_entries[name] = {
                "name": name,
                "type": obj.attrib.get("type") or "Unknown",
                "id": obj.attrib.get("id"),
                "label": None,
                "properties": {},
            }

    object_data_block = root.find("ObjectData")
    if object_data_block is not None:
        for obj in object_data_block.findall("Object"):
            name = obj.attrib.get("name")
            if not name or name not in object_entries:
                continue
            entry = object_entries[name]
            properties_block = obj.find("Properties")
            if properties_block is None:
                continue
            for prop in properties_block.findall("Property"):
                prop_name = prop.attrib.get("name")
                if not prop_name:
                    continue
                value = _extract_property_value(prop)
                if value is None:
                    continue
                if prop_name == "Label" and isinstance(value, str):
                    entry["label"] = value
                else:
                    entry["properties"][prop_name] = value

    return {
        "document_metadata": document_metadata,
        "objects": list(object_entries.values()),
    }


def _extract_property_value(prop: ET.Element) -> Any:
    """Best-effort extraction of a single FCStd Property element's value."""
    float_el = prop.find("Float")
    if float_el is not None:
        value = float_el.attrib.get("value")
        if value is not None:
            try:
                return float(value)
            except ValueError:
                return None
    integer_el = prop.find("Integer")
    if integer_el is not None:
        value = integer_el.attrib.get("value")
        if value is not None:
            try:
                return int(value)
            except ValueError:
                return None
    bool_el = prop.find("Bool")
    if bool_el is not None:
        value = bool_el.attrib.get("value")
        if value in {"true", "false"}:
            return value == "true"
    string_el = prop.find("String")
    if string_el is not None:
        return string_el.attrib.get("value")
    return None


def _build_object_registry(objects: list[dict[str, Any]]) -> tuple[dict[str, Any], list[UncertaintyNote]]:
    uncertainty: list[UncertaintyNote] = []
    entries = []
    seen_ids: set[str] = set()
    for obj in objects:
        oid = f"obj_{_slug(obj['name'])}"
        if oid in seen_ids:
            oid = f"obj_{_slug(obj['name'])}_{len(seen_ids)}"
        seen_ids.add(oid)
        entries.append(
            {
                "id": oid,
                "kind": "feature",
                "type": obj["type"],
                "name": obj.get("label") or obj["name"],
                "defined_in": "graph/feature_graph.json",
                "referenced_by": ["graph/feature_graph.json"],
                "roles": ["freecad_object"],
                "status": "generated_index",
            }
        )
    return (
        {
            "format": "aieng.object_registry",
            "format_version": FORMAT_VERSION,
            "source_files": ["graph/feature_graph.json"],
            "objects": entries,
            "relationships": [],
            "notes": [
                "Generated index from FCStd Document.xml objects.",
                "Object registry is not the source of truth; graph/feature_graph.json and the source FCStd remain authoritative.",
            ],
        },
        uncertainty,
    )


def _build_feature_graph(
    objects: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[UncertaintyNote], list[UnsupportedItem]]:
    features: list[dict[str, Any]] = []
    uncertainty: list[UncertaintyNote] = []
    unsupported: list[UnsupportedItem] = []

    for obj in objects:
        candidate_type, confidence = _classify_feature(obj)
        feature_id = f"feat_{_slug(obj['name'])}"
        parameters = _extract_feature_parameters(obj)
        editability = "proposal_allowed" if parameters else "semantic_only"
        feature = {
            "id": feature_id,
            "type": candidate_type,
            "name": obj.get("label") or obj["name"],
            "geometry_refs": {},
            "parameters": parameters,
            "parameter_source": "converter_extracted",
            "editable": bool(parameters),
            "editability": editability,
            "writeback_strategy": "none",
            "editability_reason": (
                "Parameters were lifted from FreeCAD property values for proposals only. "
                "The reference converter does NOT regenerate geometry; an external "
                "FreeCAD scripted-rebuild adapter would be required to execute edits."
            ),
            "parameter_confidence": "medium" if parameters else "low",
            "recognition": {
                "method": "freecad_name_heuristic",
                "confidence": confidence,
                "uncertainty_note": (
                    "Feature type was inferred from FCStd object name/type, not from "
                    "confirmed CAD feature semantics."
                ),
                "source_object": obj["name"],
                "source_type": obj["type"],
            },
        }
        features.append(feature)
        uncertainty.append(
            UncertaintyNote(
                scope="feature_candidate",
                description=(
                    f"Feature {feature_id} was classified as '{candidate_type}' "
                    f"from FCStd object name '{obj['name']}' / type '{obj['type']}'. "
                    "Treat as candidate, not confirmed truth."
                ),
                affected_ids=(feature_id,),
            )
        )

    if any(feature["type"] == "unknown_feature" for feature in features):
        unsupported.append(
            UnsupportedItem(
                category="features",
                status="partial",
                description=(
                    "Some FCStd objects could not be classified by name and were "
                    "recorded as 'unknown_feature'. Engineer review recommended."
                ),
            )
        )

    return (
        {
            "format_version": FORMAT_VERSION,
            "features": features,
            "metadata": {
                "source_mode": "converter",
                "converter_id": "freecad_reference",
                "recognition_method": "freecad_name_heuristic",
                "notes": [
                    "All feature candidates are heuristic. Confirmation requires CAD "
                    "feature tree access (runtime mode) or engineer review.",
                ],
            },
        },
        uncertainty,
        unsupported,
    )


def _extract_feature_parameters(obj: dict[str, Any]) -> dict[str, Any]:
    raw = obj.get("properties") or {}
    # Keep only numeric parameters as semantic edit-handle candidates.
    parameters: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            parameters[key] = value
    return parameters


def _classify_feature(obj: dict[str, Any]) -> tuple[str, str]:
    """Return (feature_type, confidence) using FCStd name and type heuristics.

    Returns only values from the feature_graph schema enum:
    base_plate, mounting_hole, mounting_hole_pattern, rib, fillet, chamfer,
    boss, flange, interface_face, unknown_feature.
    Heuristic uncertainty is recorded in recognition.confidence and
    uncertainty_notes rather than in a candidate-suffixed type string.
    """
    name = obj.get("name", "")
    type_name = obj.get("type", "")
    label = obj.get("label") or ""
    haystack = f"{name} {type_name} {label}"

    if _matches_any(haystack, _MOUNTING_HOLE_PATTERNS):
        return ("mounting_hole", "medium")
    if _matches_any(haystack, _HOLE_PATTERNS) or "Hole" in type_name:
        # We do not know whether the hole is a mounting hole or another kind;
        # mark unknown and let downstream review confirm.
        return ("unknown_feature", "low")
    if _matches_any(haystack, _FLANGE_PATTERNS):
        return ("flange", "medium")
    if _matches_any(haystack, _RIB_PATTERNS):
        return ("rib", "low")
    if _matches_any(haystack, _FILLET_PATTERNS):
        return ("fillet", "low")
    if _matches_any(haystack, _BASE_PLATE_PATTERNS) or type_name == "Part::Box":
        return ("base_plate", "medium")
    return ("unknown_feature", "low")


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return cleaned or "object"


def _build_coverage_categories(
    *,
    parsed: dict[str, Any],
    feature_graph: dict[str, Any],
    resolved_mode: str,
) -> list[CoverageCategory]:
    """Build the adaptive per-category coverage record for an FCStd offline conversion.

    Accurately reflects what the reference converter can and cannot extract
    without modifying geometry or running external tools.
    """
    objects = parsed["objects"]
    features = feature_graph.get("features", [])
    has_params = any(
        isinstance(f.get("parameters"), dict) and f["parameters"] for f in features
    )

    categories: list[CoverageCategory] = [
        CoverageCategory(
            category="geometry",
            status="missing",
            missing_items=[
                "B-rep geometry (requires FreeCAD runtime STEP export "
                "or external `aieng import-step` before topology extraction)"
            ],
            notes=(
                "Offline FCStd parsing does not produce STEP geometry. "
                "The source FCStd is preserved under provenance/source.fcstd."
            ),
        ),
        CoverageCategory(
            category="topology",
            status="missing",
            missing_items=[
                "stable face/edge/body IDs "
                "(requires `aieng extract-topology --backend occ` on a STEP export)"
            ],
        ),
        CoverageCategory(
            category="object_registry",
            status="complete" if objects else "missing",
            resources_emitted=("objects/object_registry.json",) if objects else (),
            notes="Object names and types lifted directly from FCStd Document.xml.",
        ),
        CoverageCategory(
            category="stable_references",
            status="partial" if objects else "missing",
            inferred_items=[
                "Object IDs are slug-derived from FCStd names; "
                "they are not stable across renames and are not confirmed CAD stable references."
            ] if objects else [],
        ),
        CoverageCategory(
            category="features",
            status="partial" if features else "missing",
            resources_emitted=("graph/feature_graph.json",) if features else (),
            inferred_items=[
                "Feature types inferred from FCStd object name/type via regex heuristics; "
                "treat all as candidates requiring engineer review."
            ] if features else [],
        ),
        CoverageCategory(
            category="parameters",
            status="partial" if has_params else ("inferred" if features else "missing"),
            resources_emitted=("graph/feature_graph.json",) if has_params else (),
            inferred_items=(
                ["Numeric FCStd property values lifted as parameter proposals."]
                if has_params else []
            ),
            missing_items=(
                ["Non-numeric, computed, and constrained parameters not extracted."]
                if features else []
            ),
        ),
        CoverageCategory(
            category="assemblies",
            status="unknown",
            notes="Reference converter does not inspect FCStd assembly structure.",
        ),
        CoverageCategory(
            category="materials",
            status="missing",
            missing_items=["Material assignments not extracted by the reference converter."],
        ),
        CoverageCategory(
            category="loads",
            status="missing",
            missing_items=["Load definitions not present in FCStd Document.xml."],
        ),
        CoverageCategory(
            category="boundary_conditions",
            status="missing",
            missing_items=["Boundary condition definitions not present in FCStd Document.xml."],
        ),
        CoverageCategory(
            category="mesh",
            status="missing",
            missing_items=["Mesh not generated; run an external mesher on exported geometry."],
        ),
        CoverageCategory(
            category="solver_deck",
            status="missing",
            missing_items=["No solver deck present; provide externally if needed."],
        ),
        CoverageCategory(
            category="cad_cae_mappings",
            status="missing",
            missing_items=["CAD-to-CAE mappings not established; requires geometry and mesh first."],
        ),
        CoverageCategory(
            category="editability_metadata",
            status="partial" if has_params else ("partial" if features else "missing"),
            resources_emitted=("graph/feature_graph.json",) if features else (),
            inferred_items=(
                ["parameter_source and writeback_strategy recorded for all feature candidates."]
                if features else []
            ),
            notes=(
                "Parameters are proposals only. "
                "The converter does not execute edits or regenerate geometry."
            ),
        ),
        CoverageCategory(
            category="writeback_metadata",
            status="unsupported",
            notes=(
                "L5 writeback metadata (roundtrip rebuild strategy) is not emitted "
                "by the reference converter. A future FreeCAD scripted-rebuild adapter "
                "would be required."
            ),
        ),
    ]
    return categories


def _build_readme(parsed: dict[str, Any], source_path: Path, sha: str) -> str:
    objects = parsed["objects"]
    metadata = parsed["document_metadata"]
    lines = [
        "# FreeCAD-converted .aieng package\n",
        "This package was produced by the `freecad_reference` converter.\n",
        f"Source file: `{source_path.name}` (sha256={sha[:16]}...)\n",
        f"FreeCAD document metadata: `{json.dumps(metadata, sort_keys=True)}`\n",
        "\n## Boundary\n",
        "- `.aieng` is a CAD/CAE-to-AI semantic conversion and packaging format.\n",
        "- The converter did NOT run a solver, mesher, optimizer, or CAD edit.\n",
        "- All feature candidates are heuristic; treat them as candidates, not truth.\n",
        "- See `provenance/conversion_manifest.json` for the structured per-conversion record.\n",
        "\n## Objects discovered\n",
    ]
    if not objects:
        lines.append("- (none)\n")
    else:
        for obj in objects:
            label = obj.get("label") or obj["name"]
            lines.append(f"- `{obj['name']}` (type={obj['type']}) label={label!r}\n")
    return "".join(lines)
