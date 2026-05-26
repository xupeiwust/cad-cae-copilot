from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REFERENCE_RE = re.compile(r"^@aieng\[([^#\]\s]+)#([A-Za-z0-9_.-]+)\]$")
_ALLOWED_REF_EXTENSIONS = (".json", ".yaml", ".yml")

_REF_KIND_CHOICES = {
    "feature",
    "topology",
    "interface",
    "claim",
    "evidence",
    "trace",
    "patch",
    "constraint",
    "protected_region",
    "cae_mapping",
    "completeness_item",
    "task_spec_item",
    "all",
}


@dataclass(frozen=True)
class RefRecord:
    ref: str
    kind: str
    resource_path: str
    record_id: str
    record: Any


@dataclass(frozen=True)
class RefCheckMessage:
    level: str
    text: str


class ReferenceResolutionError(ValueError):
    """Raised when a canonical @aieng[...] reference cannot be resolved."""


def format_ref(resource_path: str, record_id: str) -> str:
    return f"@aieng[{resource_path}#{record_id}]"


def parse_ref(reference: str) -> tuple[str, str]:
    match = _REFERENCE_RE.match(reference.strip())
    if match is None:
        raise ReferenceResolutionError(
            "malformed reference; expected @aieng[<resource-path>#<id>]"
        )
    resource_path, record_id = match.group(1), match.group(2)
    if not resource_path.endswith(_ALLOWED_REF_EXTENSIONS):
        raise ReferenceResolutionError(
            "invalid resource path extension in reference; expected .json, .yaml, or .yml"
        )
    return resource_path, record_id


def list_refs(package_path: str | Path, *, kind: str = "all") -> list[RefRecord]:
    kind_name = kind.strip().lower()
    if kind_name not in _REF_KIND_CHOICES:
        raise ValueError(f"unsupported --type value: {kind}; expected one of {sorted(_REF_KIND_CHOICES)}")

    with zipfile.ZipFile(Path(package_path)) as zf:
        entries = _build_ref_records(zf)

    if kind_name == "all":
        return entries
    return [entry for entry in entries if entry.kind == kind_name]


def inspect_ref(package_path: str | Path, reference: str) -> dict[str, Any]:
    resource_path, record_id = parse_ref(reference)
    wanted = format_ref(resource_path, record_id)

    with zipfile.ZipFile(Path(package_path)) as zf:
        entries = _build_ref_records(zf)

    found = next((entry for entry in entries if entry.ref == wanted), None)
    if found is None:
        raise ReferenceResolutionError(f"reference does not resolve: {wanted}")

    related_refs = _derive_related_refs(found.record)

    return {
        "ref": found.ref,
        "resource_path": found.resource_path,
        "id": found.record_id,
        "kind": found.kind,
        "record": found.record,
        "related_refs": sorted(set(related_refs)),
    }


def ref_check_package(package_path: str | Path) -> tuple[bool, list[RefCheckMessage]]:
    messages: list[RefCheckMessage] = []

    with zipfile.ZipFile(Path(package_path)) as zf:
        by_ref = {entry.ref: entry for entry in _build_ref_records(zf)}
        by_kind_and_id: dict[tuple[str, str], RefRecord] = {
            (entry.kind, entry.record_id): entry
            for entry in by_ref.values()
        }

    if not by_ref:
        messages.append(RefCheckMessage("WARN", "ref-check found no resolvable records"))
        return True, messages

    messages.append(RefCheckMessage("PASS", f"ref-check indexed {len(by_ref)} canonical references"))

    claim_records = [entry for entry in by_ref.values() if entry.kind == "claim"]
    evidence_records = [entry for entry in by_ref.values() if entry.kind == "evidence"]
    trace_records = [entry for entry in by_ref.values() if entry.kind == "trace"]

    evidence_ids = {entry.record_id for entry in evidence_records}
    claim_ids = {entry.record_id for entry in claim_records}

    ok = True

    for claim in claim_records:
        record = claim.record if isinstance(claim.record, dict) else {}
        ids = record.get("actual_evidence_ids")
        if not isinstance(ids, list):
            continue
        for evidence_id in ids:
            if not isinstance(evidence_id, str):
                ok = False
                messages.append(
                    RefCheckMessage(
                        "FAIL",
                        f"{claim.ref} field 'actual_evidence_ids' contains non-string evidence ID",
                    )
                )
                continue
            if evidence_id.endswith(".md") or "/" in evidence_id:
                ok = False
                messages.append(
                    RefCheckMessage(
                        "FAIL",
                        f"{claim.ref} field 'actual_evidence_ids' has forbidden evidence target '{evidence_id}'",
                    )
                )
                continue
            if evidence_id not in evidence_ids:
                ok = False
                messages.append(
                    RefCheckMessage(
                        "FAIL",
                        f"{claim.ref} field 'actual_evidence_ids' references unknown evidence ID '{evidence_id}'",
                    )
                )

    # Skip claim_support validation when no claims are indexed (claim_map absent in alpha)
    if claim_ids:
        for evidence in evidence_records:
            record = evidence.record if isinstance(evidence.record, dict) else {}
            claim_support = record.get("claim_support")
            if not isinstance(claim_support, list):
                continue
            for claim_id in claim_support:
                if not isinstance(claim_id, str):
                    ok = False
                    messages.append(
                        RefCheckMessage(
                            "FAIL",
                            f"{evidence.ref} field 'claim_support' contains non-string claim ID",
                        )
                    )
                    continue
                if claim_id not in claim_ids:
                    ok = False
                    messages.append(
                        RefCheckMessage(
                            "FAIL",
                            f"{evidence.ref} field 'claim_support' references unknown claim ID '{claim_id}'",
                        )
                    )

    for trace in trace_records:
        record = trace.record if isinstance(trace.record, dict) else {}
        artifacts = record.get("artifacts_recorded")
        if isinstance(artifacts, list):
            for evidence_id in artifacts:
                if not isinstance(evidence_id, str) or evidence_id not in evidence_ids:
                    ok = False
                    messages.append(
                        RefCheckMessage(
                            "FAIL",
                            f"{trace.ref} field 'artifacts_recorded' references unknown evidence ID '{evidence_id}'",
                        )
                    )
        claims_advanced = record.get("claims_advanced")
        if isinstance(claims_advanced, list):
            for claim_id in claims_advanced:
                if not isinstance(claim_id, str) or claim_id not in claim_ids:
                    ok = False
                    messages.append(
                        RefCheckMessage(
                            "FAIL",
                            f"{trace.ref} field 'claims_advanced' references unknown claim ID '{claim_id}'",
                        )
                    )

    if ok:
        messages.append(RefCheckMessage("PASS", "ref-check cross-resource ID references resolve"))

    return ok, messages


def _build_ref_records(zf: zipfile.ZipFile) -> list[RefRecord]:
    names = set(zf.namelist())
    records: list[RefRecord] = []

    candidate_resources = sorted({
        "graph/feature_graph.json",
        "geometry/topology_map.json",
        "graph/aag.json",
        "objects/interface_graph.json",
        "results/evidence_index.json",
        "provenance/tool_trace.json",
        "graph/constraints.json",
        "ai/protected_regions.json",
        "simulation/cae_mapping.json",
        "validation/completeness_report.json",
        "task/task_spec.yaml",
        "task/external_tool_requirements.json",
        *[name for name in names if name.startswith("ai/patches/") and name.endswith(".json")],
    })

    for resource_path in candidate_resources:
        if resource_path not in names:
            continue
        data = _read_structured_member(zf, resource_path)
        if data is None:
            continue
        records.extend(_resource_records(resource_path, data))

    records.sort(key=lambda item: item.ref)
    return records


def _read_structured_member(zf: zipfile.ZipFile, resource_path: str) -> Any | None:
    if resource_path.endswith(".json"):
        return json.loads(zf.read(resource_path))
    if resource_path.endswith((".yaml", ".yml")):
        return yaml.safe_load(zf.read(resource_path))
    return None


def _resource_records(resource_path: str, data: Any) -> list[RefRecord]:
    if resource_path == "graph/feature_graph.json":
        return _from_collection(resource_path, data, "features", "id", "feature")
    if resource_path == "geometry/topology_map.json":
        return _from_collection(resource_path, data, "entities", "id", "topology")
    if resource_path == "graph/aag.json":
        nodes = _from_collection(resource_path, data, "nodes", "id", "topology")
        arcs = _from_collection(resource_path, data, "arcs", "id", "topology")
        return nodes + arcs
    if resource_path == "objects/interface_graph.json":
        return _from_collection(resource_path, data, "interfaces", "id", "interface")
    if resource_path == "results/evidence_index.json":
        return _from_collection(resource_path, data, "evidence_items", "evidence_id", "evidence")
    if resource_path == "provenance/tool_trace.json":
        return _from_collection(resource_path, data, "entries", "entry_id", "trace")
    if resource_path == "graph/constraints.json":
        return _from_collection(resource_path, data, "constraints", "id", "constraint")
    if resource_path == "ai/protected_regions.json":
        return _from_collection(resource_path, data, "protected_regions", "feature_id", "protected_region")
    if resource_path == "simulation/cae_mapping.json":
        records = _from_collection(resource_path, data, "mappings", "id", "cae_mapping")
        if records:
            return records
        return _from_collection(resource_path, data, "mappings", "cae_entity", "cae_mapping")
    if resource_path == "validation/completeness_report.json":
        return _from_collection(resource_path, data, "categories", "category", "completeness_item")
    if resource_path == "task/task_spec.yaml":
        return _from_single(resource_path, data, "task_id", "task_spec_item")
    if resource_path == "task/external_tool_requirements.json":
        return _from_single(resource_path, data, "handoff_id", "task_spec_item")
    if resource_path.startswith("ai/patches/") and resource_path.endswith(".json"):
        return _from_single(resource_path, data, "patch_id", "patch")
    return []


def _from_collection(
    resource_path: str,
    data: Any,
    collection_key: str,
    id_key: str,
    kind: str,
) -> list[RefRecord]:
    if not isinstance(data, dict):
        return []
    collection = data.get(collection_key)
    if not isinstance(collection, list):
        return []

    result: list[RefRecord] = []
    for item in collection:
        if not isinstance(item, dict):
            continue
        record_id = item.get(id_key)
        if not isinstance(record_id, str) or not record_id:
            continue
        result.append(
            RefRecord(
                ref=format_ref(resource_path, record_id),
                kind=kind,
                resource_path=resource_path,
                record_id=record_id,
                record=item,
            )
        )
    return result


def _from_single(resource_path: str, data: Any, id_key: str, kind: str) -> list[RefRecord]:
    if not isinstance(data, dict):
        return []
    record_id = data.get(id_key)
    if not isinstance(record_id, str) or not record_id:
        return []
    return [
        RefRecord(
            ref=format_ref(resource_path, record_id),
            kind=kind,
            resource_path=resource_path,
            record_id=record_id,
            record=data,
        )
    ]


def _derive_related_refs(record: Any) -> list[str]:
    related: list[str] = []
    _collect_related_refs(record, related)
    return related


def _collect_related_refs(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        try:
            parse_ref(value)
        except ReferenceResolutionError:
            return
        out.append(value)
        return

    if isinstance(value, list):
        for item in value:
            _collect_related_refs(item, out)
        return

    if isinstance(value, dict):
        for item in value.values():
            _collect_related_refs(item, out)
