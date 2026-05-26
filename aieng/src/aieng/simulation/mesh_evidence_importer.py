from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from aieng.results.evidence_writer import record_evidence_package

SUPPORTED_MESH_FORMATS = {"gmsh_msh"}
SUPPORTED_VERIFICATION_STATUSES = {"available", "missing", "unverified", "schema_validated"}
_GMSH_MSH_PARSER_ID = "gmsh_msh_ascii_summary_v1"
_MESH_ARTIFACT_DIR = "results/mesh_artifacts/"
_MESH_EXTENSION_BY_FORMAT = {"gmsh_msh": ".msh"}

_KNOWN_MESH_QUALITY_KEYS = ("min_element_quality", "max_aspect_ratio")


def import_mesh_evidence_package(
    package_path: str | Path,
    *,
    mesh_file: str | Path,
    mesh_format: str,
    producer_tool: str,
    claim_support: list[str],
    verification_status: str = "unverified",
    evidence_id: str | None = None,
    reference_only: bool = False,
    package_artifact_path: str | None = None,
    notes: list[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Import an external mesh artifact as evidence-only writeback.

    This function intentionally does NOT update claim verification status.
    It records only known, directly observed mesh metadata.
    """
    package = Path(package_path)
    mesh_path = Path(mesh_file)

    if not mesh_path.exists():
        raise FileNotFoundError(f"mesh file does not exist: {mesh_path}")

    normalized_format = mesh_format.strip().lower()
    if normalized_format not in SUPPORTED_MESH_FORMATS:
        raise ValueError(
            f"unsupported mesh format {mesh_format!r}; supported formats: {', '.join(sorted(SUPPORTED_MESH_FORMATS))}"
        )

    if verification_status not in SUPPORTED_VERIFICATION_STATUSES:
        raise ValueError(f"unsupported verification status: {verification_status}")

    text = _read_utf8_text(mesh_path)
    summary = _scan_known_mesh_summary(text)
    final_evidence_id = _resolve_evidence_id(package, "mesh_evidence", evidence_id)
    artifact_path, artifact_payload = _resolve_artifact_location(
        final_evidence_id,
        mesh_path,
        mesh_format=normalized_format,
        reference_only=reference_only,
        package_path=package_artifact_path,
    )
    structured_payload = _build_structured_payload(
        mesh_format=normalized_format,
        summary=summary,
        artifact=artifact_payload,
    )
    if not reference_only:
        _ensure_package_member_absent(package, artifact_path)

    import_notes: list[str] = [
        "[import-mesh-evidence] evidence-only import: no automatic claim status update performed.",
        f"[import-mesh-evidence] format={normalized_format}",
        f"[import-mesh-evidence] line_count={summary['line_count']}",
        f"[import-mesh-evidence] mesh_summary={summary}",
        f"[import-mesh-evidence] structured_parser_status={structured_payload['parser']['status']}",
    ]
    if notes:
        import_notes.extend(notes)

    out = record_evidence_package(
        package,
        evidence_type="mesh_evidence",
        producer_kind="external_cae",
        producer_tool=producer_tool,
        artifact_kind="result_file",
        artifact_path=artifact_path,
        claim_support=claim_support,
        evidence_id=final_evidence_id,
        verification_status=verification_status,
        structured_payload=structured_payload,
        notes=import_notes,
    )
    if not reference_only:
        _write_package_artifact(package, artifact_path, mesh_path.read_bytes())
    return out, summary


def _read_utf8_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"mesh file must be UTF-8 text for deterministic parsing: {path}") from exc


def _scan_known_mesh_summary(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    found_quality: dict[str, Any] = {}

    summary: dict[str, Any] = {
        "line_count": len(lines),
        "detected_format": "unknown",
        "format_version": None,
        "nodes_declared": None,
        "elements_declared": None,
        "element_blocks_declared": None,
        "quality_metrics_present": False,
    }

    # Gmsh v2/v4 ASCII signature
    if any(line.strip() == "$MeshFormat" for line in lines):
        summary["detected_format"] = "gmsh"
        summary["format_version"] = _gmsh_version(lines)
        summary["nodes_declared"] = _gmsh_declared_count(lines, "$Nodes")
        summary["elements_declared"] = _gmsh_declared_count(lines, "$Elements")
        summary["element_blocks_declared"] = _gmsh_declared_block_count(lines, "$Elements")

    summary["quality_metrics_present"] = bool(found_quality)
    summary["quality_metrics_not_found"] = [k for k in _KNOWN_MESH_QUALITY_KEYS if k not in found_quality]
    return summary


def _gmsh_declared_count(lines: list[str], section_tag: str) -> int | None:
    for idx, line in enumerate(lines):
        if line.strip() != section_tag:
            continue
        for probe in lines[idx + 1 :]:
            stripped = probe.strip()
            if not stripped:
                continue
            if stripped.startswith("$"):
                return None
            tokens = stripped.split()
            parsed_ints: list[int] = []
            for token in tokens:
                try:
                    parsed_ints.append(int(token))
                except ValueError:
                    break
            if not parsed_ints:
                return None

            # Gmsh v2: first line after $Nodes/$Elements is the total count.
            if len(parsed_ints) == 1:
                return parsed_ints[0]

            # Gmsh v4: section header usually begins with
            # numEntityBlocks numNodes(min/max tags...) / numElements(min/max tags...).
            if len(parsed_ints) >= 2:
                return parsed_ints[1]

            return None
        return None
    return None


def _gmsh_version(lines: list[str]) -> str | None:
    for idx, line in enumerate(lines):
        if line.strip() != "$MeshFormat":
            continue
        for probe in lines[idx + 1 :]:
            stripped = probe.strip()
            if not stripped:
                continue
            if stripped.startswith("$"):
                return None
            return stripped.split()[0]
        return None
    return None


def _gmsh_declared_block_count(lines: list[str], section_tag: str) -> int | None:
    for idx, line in enumerate(lines):
        if line.strip() != section_tag:
            continue
        for probe in lines[idx + 1 :]:
            stripped = probe.strip()
            if not stripped:
                continue
            if stripped.startswith("$"):
                return None
            tokens = stripped.split()
            if len(tokens) < 2:
                return None
            try:
                return int(tokens[0])
            except ValueError:
                return None
        return None
    return None


def _build_structured_payload(
    *,
    mesh_format: str,
    summary: dict[str, Any],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    parser_status = "matched" if summary.get("detected_format") != "unknown" else "unsupported"
    return {
        "payload_type": "mesh_artifact_summary",
        "mesh_format": mesh_format,
        "parser": {
            "kind": "deterministic_utf8_section_scan",
            "parser_id": _GMSH_MSH_PARSER_ID,
            "status": parser_status,
        },
        "artifact": artifact,
        "summary": {
            "format_version": summary.get("format_version"),
            "nodes_declared": summary.get("nodes_declared"),
            "elements_declared": summary.get("elements_declared"),
            "element_blocks_declared": summary.get("element_blocks_declared"),
            "quality_metrics": {
                "status": "unknown",
                "metrics_present": bool(summary.get("quality_metrics_present") is True),
                "observed_keys": [],
            },
        },
    }


def _resolve_artifact_location(
    evidence_id: str,
    mesh_path: Path,
    *,
    mesh_format: str,
    reference_only: bool,
    package_path: str | None,
) -> tuple[str, dict[str, Any]]:
    if reference_only:
        external_path = str(mesh_path)
        return external_path, {
            "storage_mode": "external_reference",
            "external_path": external_path,
            "source_path": external_path,
        }

    package_member = package_path.strip() if isinstance(package_path, str) and package_path.strip() else ""
    if not package_member:
        suffix = _MESH_EXTENSION_BY_FORMAT.get(mesh_format, ".mesh")
        package_member = f"{_MESH_ARTIFACT_DIR}{evidence_id}{suffix}"
    package_member = package_member.replace("\\", "/")
    if package_member.startswith(("/", "\\")) or (len(package_member) > 1 and package_member[1] == ":"):
        raise ValueError("--package-path must be a relative path inside the .aieng package")
    if ".." in Path(package_member).parts:
        raise ValueError("--package-path must not contain '..'")
    return package_member, {
        "storage_mode": "copied_into_package",
        "package_path": package_member,
        "source_path": str(mesh_path),
    }


def _resolve_evidence_id(package_path: Path, evidence_type: str, evidence_id: str | None) -> str:
    final_evidence_id = evidence_id.strip() if isinstance(evidence_id, str) else ""
    if final_evidence_id:
        return final_evidence_id

    try:
        with zipfile.ZipFile(package_path, mode="r") as package:
            evidence_index = json.loads(package.read("results/evidence_index.json"))
    except KeyError as exc:
        raise FileNotFoundError(
            f"missing evidence scaffold resources: results/evidence_index.json; run 'aieng write-evidence-scaffold {package_path}'"
        ) from exc
    existing_ids = {
        item.get("evidence_id")
        for item in evidence_index.get("evidence_items", [])
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }
    prefix = "ev_mesh_evidence" if evidence_type == "mesh_evidence" else f"ev_{evidence_type}"
    max_num = 0
    for existing_id in existing_ids:
        if not isinstance(existing_id, str) or not existing_id.startswith(f"{prefix}_"):
            continue
        suffix = existing_id.removeprefix(f"{prefix}_")
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return f"{prefix}_{max_num + 1:03d}"


def _ensure_package_member_absent(package_path: Path, member: str) -> None:
    with zipfile.ZipFile(package_path, mode="r") as package:
        if member in set(package.namelist()):
            raise FileExistsError(f"{member} already exists in package")


def _write_package_artifact(package_path: Path, member: str, data: bytes) -> None:
    with zipfile.ZipFile(package_path, mode="r") as package:
        names = set(package.namelist())
        if member in names:
            raise FileExistsError(f"{member} already exists in package")
        members = [(info, b"" if info.is_dir() else package.read(info.filename)) for info in package.infolist()]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=package_path.parent) as fh:
        temp_path = Path(fh.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out:
            for info, raw in members:
                out.writestr(info, raw)
            if _MESH_ARTIFACT_DIR not in names:
                out.writestr(_MESH_ARTIFACT_DIR, b"")
            out.writestr(member, data)
        shutil.move(str(temp_path), package_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
