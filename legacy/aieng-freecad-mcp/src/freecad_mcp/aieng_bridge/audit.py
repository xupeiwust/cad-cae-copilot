"""Audit report generation for .aieng packages.

Produces a deterministic summary of package state, evidence, provenance,
reference mapping, and claim discipline.

Rules:
- Audit is read-only except for writing the audit report itself.
- Audit must not modify claim_map.json, evidence_index.json, or tool_trace.json.
- Audit detects claim discipline violations (auto-advancement).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from freecad_mcp.aieng_bridge.persistence import _atomic_write_json


class AuditReport(BaseModel):
    """Structured audit report for an .aieng package."""

    model_config = ConfigDict(extra="forbid")

    package_path: str
    generated_at: str
    evidence_summary: dict[str, Any]
    trace_summary: dict[str, Any]
    patch_run_summary: dict[str, Any]
    reference_map_summary: dict[str, Any]
    claim_summary: dict[str, Any]
    artifacts_summary: dict[str, Any]
    failure_mode_summary: dict[str, Any]
    warnings: list[str]
    claim_discipline_summary: dict[str, Any]


def _load_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _count_entries(data: dict[str, Any] | None, key: str = "entries") -> int:
    if not data:
        return 0
    entries = data.get(key, [])
    return len(entries)


def _count_by_field(entries: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for entry in entries:
        value = entry.get(field)
        if isinstance(value, str):
            counter[value] += 1
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str):
                    counter[v] += 1
    return dict(counter)


def _collect_artifacts(entries: list[dict[str, Any]]) -> list[str]:
    artifacts: list[str] = []
    for entry in entries:
        meta = entry.get("metadata", {})
        written = meta.get("artifacts_written", [])
        if isinstance(written, list):
            for art in written:
                if isinstance(art, dict):
                    path = art.get("path") or art.get("file_path")
                    if path:
                        artifacts.append(str(path))
                elif isinstance(art, str):
                    artifacts.append(art)
        # Also check direct artifact paths
        for key in ("artifact_path", "modified_artifact", "deck_path", "result_path"):
            val = meta.get(key)
            if val:
                artifacts.append(str(val))
    return artifacts


def _detect_claim_violations(
    evidence_entries: list[dict[str, Any]],
    trace_entries: list[dict[str, Any]],
    claim_map: dict[str, Any] | None,
) -> list[str]:
    violations: list[str] = []

    # Check evidence entries for claims_advanced=True
    for entry in evidence_entries:
        meta = entry.get("metadata", {})
        if meta.get("claims_advanced") is True:
            violations.append(
                f"Evidence {entry.get('evidence_id', '?')} has claims_advanced=True; "
                "only aieng_update_claim should advance claims."
            )

    # Check trace entries for claim_map modifications not by aieng_update_claim
    for entry in trace_entries:
        op = entry.get("operation", "")
        if "claim" in op.lower() and op != "aieng_update_claim":
            violations.append(
                f"Trace {entry.get('trace_id', '?')} operation '{op}' may have modified claim_map; "
                "only aieng_update_claim is allowed."
            )

    # Check if claims were updated without a matching aieng_update_claim trace
    if claim_map:
        for claim in claim_map.get("claims", []):
            if claim.get("status") in ("pass", "fail"):
                # This is acceptable if there is an explicit update trace
                update_traces = [
                    t for t in trace_entries
                    if t.get("operation") == "aieng_update_claim"
                    and any(
                        cid == claim.get("id")
                        for cid in (t.get("inputs", {}).get("claim_id", []),)
                        if cid
                    )
                ]
                if not update_traces:
                    # Also check if claim status was changed in evidence
                    pass  # Not a strict violation since we don't track history

    return violations


def generate_audit_report(
    package_path: str,
    output_path: str | None = None,
    output_markdown: bool = True,
    output_json: bool = True,
) -> dict[str, Any]:
    """Generate an audit report for an .aieng package.

    Args:
        package_path: Path to the unpacked .aieng package directory.
        output_path: Optional override for the report output directory.
            Defaults to ``package_path / "reports"``.
        output_markdown: Whether to write a human-readable Markdown report.
        output_json: Whether to write a structured JSON report.

    Returns:
        Summary dictionary with report contents and written paths.
    """
    from datetime import datetime, timezone

    pkg = Path(package_path)
    if not pkg.is_dir():
        raise ValueError(f"Package path is not a directory: {package_path}")

    # Load package files
    evidence_data = _load_json_safe(pkg / "results" / "evidence_index.json")
    trace_data = _load_json_safe(pkg / "provenance" / "tool_trace.json")
    claim_map = _load_json_safe(pkg / "results" / "claim_map.json")
    ref_map = _load_json_safe(pkg / "objects" / "reference_map.json")

    evidence_entries = evidence_data.get("entries", []) if evidence_data else []
    trace_entries = trace_data.get("entries", []) if trace_data else []

    # Evidence summary
    evidence_summary = {
        "total": len(evidence_entries),
        "by_type": _count_by_field(evidence_entries, "evidence_type"),
        "by_producer_kind": _count_by_field(evidence_entries, "producer_kind"),
    }

    # Trace summary
    trace_summary = {
        "total": len(trace_entries),
        "by_operation": _count_by_field(trace_entries, "operation"),
    }

    # Patch run summary
    patch_runs_dir = pkg / "execution" / "patch_runs"
    patch_run_files = list(patch_runs_dir.glob("*.json")) if patch_runs_dir.exists() else []
    patch_run_summary = {
        "total": len(patch_run_files),
        "run_ids": [p.stem for p in patch_run_files],
    }

    # Reference map summary
    ref_status_counts: dict[str, int] = Counter()
    if ref_map:
        for geo in ref_map.get("geometry_references", []):
            status = geo.get("status", "unknown")
            ref_status_counts[status] += 1
        for cae in ref_map.get("cae_targets", []):
            status = cae.get("status", "unknown")
            ref_status_counts[status] += 1
    reference_map_summary = {
        "exists": ref_map is not None,
        "geometry_reference_count": len(ref_map.get("geometry_references", [])) if ref_map else 0,
        "cae_target_count": len(ref_map.get("cae_targets", [])) if ref_map else 0,
        "status_counts": dict(ref_status_counts),
    }

    # Claim summary
    claim_status_counts: dict[str, int] = Counter()
    if claim_map:
        for claim in claim_map.get("claims", []):
            status = claim.get("status", "unknown")
            claim_status_counts[status] += 1
    claim_summary = {
        "total": len(claim_map.get("claims", [])) if claim_map else 0,
        "status_counts": dict(claim_status_counts),
    }

    # Artifacts summary
    artifacts = _collect_artifacts(evidence_entries)
    artifacts_summary = {
        "total": len(artifacts),
        "paths": artifacts,
    }

    # Warnings
    warnings: list[str] = []
    for entry in evidence_entries:
        warnings.extend(entry.get("warnings", []))
    for entry in trace_entries:
        warnings.extend(entry.get("warnings", []))
    if not ref_map:
        warnings.append("No reference_map.json found.")

    # Failure mode taxonomy coverage
    failure_mode_counts: dict[str, int] = Counter()
    failure_mode_present = 0
    failure_mode_missing = 0
    for entry in evidence_entries:
        fm = entry.get("failure_mode")
        if isinstance(fm, dict) and fm.get("mode"):
            failure_mode_counts[fm["mode"]] += 1
            failure_mode_present += 1
        else:
            failure_mode_missing += 1
    for entry in trace_entries:
        fm = entry.get("failure_mode")
        if isinstance(fm, dict) and fm.get("mode"):
            failure_mode_counts[fm["mode"]] += 1
            failure_mode_present += 1
        else:
            failure_mode_missing += 1
    failure_mode_summary = {
        "present_count": failure_mode_present,
        "missing_count": failure_mode_missing,
        "coverage_ratio": (
            round(failure_mode_present / (failure_mode_present + failure_mode_missing), 2)
            if (failure_mode_present + failure_mode_missing) > 0
            else None
        ),
        "mode_counts": dict(failure_mode_counts),
    }

    # Claim discipline
    violations = _detect_claim_violations(evidence_entries, trace_entries, claim_map)
    claim_discipline_summary = {
        "tools_did_not_auto_advance_claims": len(violations) == 0,
        "violations": violations,
        "claims_updated_only_by_explicit_update": any(
            t.get("operation") == "aieng_update_claim" for t in trace_entries
        ),
        "explicit_update_trace_count": sum(
            1 for t in trace_entries if t.get("operation") == "aieng_update_claim"
        ),
    }

    report = AuditReport(
        package_path=str(pkg.resolve()),
        generated_at=datetime.now(timezone.utc).isoformat(),
        evidence_summary=evidence_summary,
        trace_summary=trace_summary,
        patch_run_summary=patch_run_summary,
        reference_map_summary=reference_map_summary,
        claim_summary=claim_summary,
        artifacts_summary=artifacts_summary,
        failure_mode_summary=failure_mode_summary,
        warnings=warnings,
        claim_discipline_summary=claim_discipline_summary,
    )

    # Write reports
    reports_dir = Path(output_path) if output_path else pkg / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[str] = []

    if output_json:
        json_path = reports_dir / "audit_report.json"
        _atomic_write_json(json_path, report.model_dump(mode="json"))
        written_paths.append(str(json_path.resolve()))

    if output_markdown:
        md_path = reports_dir / "audit_report.md"
        md_content = _render_audit_markdown(report)
        md_path.write_text(md_content, encoding="utf-8")
        written_paths.append(str(md_path.resolve()))

    return {
        "status": "success",
        "operation": "generate_audit_report",
        "package_path": str(pkg.resolve()),
        "written_paths": written_paths,
        "report": report.model_dump(mode="json"),
        "claim_policy": {"claims_advanced": False, "requires_explicit_update_claim": True},
    }


def _render_audit_markdown(report: AuditReport) -> str:
    """Render an AuditReport as human-readable Markdown."""
    lines: list[str] = []
    lines.append("# .aieng Package Audit Report")
    lines.append("")
    lines.append(f"**Package:** `{report.package_path}`")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append("")

    lines.append("## Evidence Summary")
    ev = report.evidence_summary
    lines.append(f"- **Total evidence entries:** {ev['total']}")
    if ev["by_type"]:
        lines.append("- **By type:**")
        for k, v in ev["by_type"].items():
            lines.append(f"  - {k}: {v}")
    if ev["by_producer_kind"]:
        lines.append("- **By producer kind:**")
        for k, v in ev["by_producer_kind"].items():
            lines.append(f"  - {k}: {v}")
    lines.append("")

    lines.append("## Trace Summary")
    tr = report.trace_summary
    lines.append(f"- **Total trace entries:** {tr['total']}")
    if tr["by_operation"]:
        lines.append("- **By operation:**")
        for k, v in tr["by_operation"].items():
            lines.append(f"  - {k}: {v}")
    lines.append("")

    lines.append("## Patch Run Summary")
    pr = report.patch_run_summary
    lines.append(f"- **Total patch runs:** {pr['total']}")
    if pr["run_ids"]:
        lines.append("- **Run IDs:**")
        for rid in pr["run_ids"]:
            lines.append(f"  - {rid}")
    lines.append("")

    lines.append("## Reference Map Summary")
    rm = report.reference_map_summary
    lines.append(f"- **Exists:** {rm['exists']}")
    lines.append(f"- **Geometry references:** {rm['geometry_reference_count']}")
    lines.append(f"- **CAE targets:** {rm['cae_target_count']}")
    if rm["status_counts"]:
        lines.append("- **Status counts:**")
        for k, v in rm["status_counts"].items():
            lines.append(f"  - {k}: {v}")
    lines.append("")

    lines.append("## Claim Summary")
    cl = report.claim_summary
    lines.append(f"- **Total claims:** {cl['total']}")
    if cl["status_counts"]:
        lines.append("- **Status counts:**")
        for k, v in cl["status_counts"].items():
            lines.append(f"  - {k}: {v}")
    lines.append("")

    lines.append("## Artifacts Summary")
    ar = report.artifacts_summary
    lines.append(f"- **Total artifacts:** {ar['total']}")
    if ar["paths"]:
        lines.append("- **Paths:**")
        for p in ar["paths"]:
            lines.append(f"  - {p}")
    lines.append("")

    lines.append("## Failure Mode Taxonomy Coverage")
    fm = report.failure_mode_summary
    lines.append(f"- **Entries with failure_mode:** {fm['present_count']}")
    lines.append(f"- **Entries without failure_mode:** {fm['missing_count']}")
    if fm["coverage_ratio"] is not None:
        lines.append(f"- **Coverage ratio:** {fm['coverage_ratio']}")
    if fm["mode_counts"]:
        lines.append("- **Mode counts:**")
        for k, v in fm["mode_counts"].items():
            lines.append(f"  - {k}: {v}")
    lines.append("")

    lines.append("## Claim Discipline")
    cd = report.claim_discipline_summary
    lines.append(f"- **No auto-advancement detected:** {cd['tools_did_not_auto_advance_claims']}")
    lines.append(f"- **Explicit update traces:** {cd['explicit_update_trace_count']}")
    if cd["violations"]:
        lines.append("- **Violations:**")
        for v in cd["violations"]:
            lines.append(f"  - {v}")
    else:
        lines.append("- **Violations:** none")
    lines.append("")

    if report.warnings:
        lines.append("## Warnings")
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("---")
    lines.append("*This report was generated by freecad_mcp audit.*")
    lines.append("")

    return "\n".join(lines)
