from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from aieng import FORMAT_VERSION

EVIDENCE_REPORT_PATH = "validation/evidence_report.json"
VALIDATION_DIR = "validation/"

_VALIDATION_STATUS_PATH = "validation/status.yaml"
_EVIDENCE_INDEX_PATH = "results/evidence_index.json"


def write_evidence_report_package(
    package_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Generate validation/evidence_report.json from validation and results ledgers."""
    path = Path(package_path)
    if not path.exists():
        raise FileNotFoundError(f"package does not exist: {path}")
    if path.suffix != ".aieng":
        raise ValueError("package path must end with .aieng")

    try:
        with zipfile.ZipFile(path, mode="r") as package:
            names = set(package.namelist())
            if "manifest.json" not in names:
                raise ValueError("package is missing manifest.json")
            if EVIDENCE_REPORT_PATH in names and not overwrite:
                raise FileExistsError(f"{EVIDENCE_REPORT_PATH} already exists; use --overwrite to replace it")

            missing_sources = [
                member
                for member in (_VALIDATION_STATUS_PATH, _EVIDENCE_INDEX_PATH)
                if member not in names
            ]
            if missing_sources:
                raise FileNotFoundError(
                    "evidence report requires validation/status.yaml and "
                    "results/evidence_index.json; missing: " + ", ".join(missing_sources)
                )

            manifest = json.loads(package.read("manifest.json"))
            validation_status = yaml.safe_load(package.read(_VALIDATION_STATUS_PATH))
            evidence_index = json.loads(package.read(_EVIDENCE_INDEX_PATH))
            members = _read_members(package, exclude={"manifest.json", EVIDENCE_REPORT_PATH})
    except zipfile.BadZipFile as exc:
        raise ValueError(f"package is not a valid zip archive: {path}") from exc

    report = build_evidence_report(
        manifest=manifest,
        validation_status=validation_status,
        evidence_index=evidence_index,
    )

    resources = manifest.setdefault("resources", {})
    if not isinstance(resources, dict):
        raise ValueError("manifest resources must be an object")
    validation_resources = resources.setdefault("validation", {})
    if not isinstance(validation_resources, dict):
        raise ValueError("manifest resources.validation must be an object")
    validation_resources["evidence_report"] = EVIDENCE_REPORT_PATH

    manifest_json = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    report_json = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    existing_filenames = {info.filename for info, _ in members}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".aieng", dir=path.parent) as fh:
        temp_path = Path(fh.name)

    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as out:
            for info, data in members:
                out.writestr(info, data)
            if VALIDATION_DIR not in existing_filenames:
                out.writestr(VALIDATION_DIR, b"")
            out.writestr("manifest.json", manifest_json)
            out.writestr(EVIDENCE_REPORT_PATH, report_json)
        shutil.move(str(temp_path), path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return path


def build_evidence_report(
    *,
    manifest: dict[str, Any],
    validation_status: Any,
    evidence_index: Any,
) -> dict[str, Any]:
    if not isinstance(evidence_index, dict):
        raise ValueError("results/evidence_index.json must be a JSON object")
    if not isinstance(validation_status, dict):
        raise ValueError("validation/status.yaml must be a mapping")

    model_id = str(manifest.get("model_id") or "unknown_model")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Alpha contract: no claim maps and no automatic claim advancement.
    # The schema still requires `claims` and `claim_status_counts` for backwards
    # compatibility, so we emit zeroed values without inspecting any claim_map.
    status_counts = {
        "pass": 0,
        "fail": 0,
        "unsupported": 0,
        "partially_supported": 0,
        "needs_review": 0,
    }

    solver_mesh_status = validation_status.get("solver_mesh_status") if isinstance(validation_status, dict) else {}
    patch_status = validation_status.get("patch_status") if isinstance(validation_status, dict) else {}
    claim_policy = validation_status.get("claim_policy") if isinstance(validation_status, dict) else {}

    return {
        "format_version": FORMAT_VERSION,
        "report_id": "evidence_report_001",
        "model_id": model_id,
        "generated_at_utc": now,
        "source_files": [
            _VALIDATION_STATUS_PATH,
            _EVIDENCE_INDEX_PATH,
        ],
        "derived_view_policy": {
            "is_derived_view": True,
            "source_of_truth_is_elsewhere": True,
            "authoritative_sources": [
                _VALIDATION_STATUS_PATH,
                _EVIDENCE_INDEX_PATH,
            ],
            "no_claim_auto_advance": True,
        },
        "claim_status_counts": status_counts,
        "claims": [],
        "validation_state_snapshot": {
            "solver_execution": solver_mesh_status.get("solver_execution"),
            "mesh_generation": solver_mesh_status.get("mesh_generation"),
            "patch_execution": patch_status.get("patch_execution"),
            "forbidden_claims_count": len(claim_policy.get("forbidden_claims", [])) if isinstance(claim_policy, dict) and isinstance(claim_policy.get("forbidden_claims"), list) else 0,
        },
        "notes": [
            "This report is a generated consolidated read view.",
            "validation/status.yaml and results/evidence_index.json remain authoritative.",
        ],
    }


def _read_members(
    package: zipfile.ZipFile,
    *,
    exclude: set[str],
) -> list[tuple[zipfile.ZipInfo, bytes]]:
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    seen: set[str] = set()
    for info in package.infolist():
        if info.filename in exclude or info.filename in seen:
            continue
        seen.add(info.filename)
        data = b"" if info.is_dir() else package.read(info.filename)
        members.append((info, data))
    return members
