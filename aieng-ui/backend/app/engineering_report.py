"""Self-contained engineering report export (#372).

The report is a read-only deliverable assembled from artifacts that already
exist in a project's `.aieng` package. It never runs CAD, mesh, solver, or
post-processing tools, and it never writes back into the package.
"""

from __future__ import annotations

import html
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import Settings, now_iso
from .project_io import get_project, resolve_project_path

REPORT_SCHEMA_VERSION = "0.1"
CLAIM_ADVANCEMENT = "none"

REPORT_BOUNDARY = (
    "This report is a review artifact only. It does not certify design safety, "
    "does not advance engineering claims, and requires qualified engineering review."
)


def _read_package_member(pkg: Path, member: str) -> bytes | None:
    try:
        with zipfile.ZipFile(pkg, "r") as zf:
            if member not in zf.namelist():
                return None
            return zf.read(member)
    except Exception:
        return None


def _thumbnail_data_uri(pkg: Path) -> str | None:
    stl = _read_package_member(pkg, "geometry/preview.stl")
    if not stl:
        return None
    try:
        from .cad_generation import render_mesh_thumbnail

        b64 = render_mesh_thumbnail(stl)
    except Exception:
        b64 = None
    if not b64:
        return None
    return f"data:image/png;base64,{b64}"


def _bom_markdown(settings: Settings, project_id: str) -> tuple[str | None, list[str]]:
    try:
        from .standards_bridge import generate_bom

        result = generate_bom(settings, project_id=project_id, package_path=None, fmt="markdown")
    except Exception as exc:
        return None, [f"BOM generation raised {type(exc).__name__}: {exc}"]
    if result.get("status") != "ok":
        return None, [str(result.get("message") or "BOM unavailable.")]
    markdown = result.get("markdown")
    warnings = [str(item) for item in (result.get("warnings") or [])]
    return str(markdown) if markdown else None, warnings


def _credibility(settings: Settings, project_id: str, package_path: Path) -> dict[str, Any]:
    try:
        from .routers.evidence import _build_credibility_report

        return _build_credibility_report(settings, project_id, package_path)
    except Exception as exc:
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "claim_advancement": CLAIM_ADVANCEMENT,
            "summary": {"overall": "unknown"},
            "warnings": [f"Credibility report unavailable: {type(exc).__name__}: {exc}"],
            "missing_evidence": ["Credibility report could not be assembled."],
        }


def _review_packet(settings: Settings, project_id: str) -> dict[str, Any]:
    from . import review_support_packet

    return review_support_packet.preview_review_support_packet(
        settings,
        project_id,
        {"packet_id": "engineering_report_preview"},
    )


def _status_counts(sections: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in sections:
        status = str(section.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _html_block(markdown: str | None) -> str:
    if not markdown:
        return "<p class=\"muted\">No data available.</p>"
    return f"<pre>{html.escape(markdown.strip())}</pre>"


def _html_list(items: list[str]) -> str:
    if not items:
        return "<p class=\"muted\">None recorded.</p>"
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _html_report(payload: dict[str, Any]) -> str:
    project = payload["project"]
    credibility = payload["credibility"]
    review_packet = payload["review_packet"]
    report = payload["report"]
    thumbnail_uri = report.get("thumbnail_data_uri")
    bom_markdown = report.get("bom_markdown")
    warnings = report.get("warnings") or []
    missing = credibility.get("missing_evidence") or []
    credibility_summary = credibility.get("summary") or {}
    sections = review_packet.get("sections") or []
    status_counts = _status_counts(sections)
    review_markdown = review_packet.get("preview_markdown") or ""

    thumbnail_html = (
        f"<img class=\"thumbnail\" src=\"{html.escape(thumbnail_uri)}\" alt=\"Geometry thumbnail\" />"
        if thumbnail_uri
        else "<div class=\"thumbnail placeholder\">No embedded thumbnail available</div>"
    )
    status_chip = html.escape(str(credibility_summary.get("overall") or "unknown"))
    project_name = html.escape(str(project.get("name") or "(unnamed project)"))
    project_id = html.escape(str(project.get("id") or ""))
    generated_at = html.escape(str(report.get("generated_at") or ""))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AIENG Engineering Report - {project_name}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #172033; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 32px 24px 48px; }}
    header {{ display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 24px; align-items: start; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; line-height: 1.1; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; color: #172033; }}
    p {{ line-height: 1.5; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .chip {{ border: 1px solid #ccd5e1; border-radius: 999px; background: #fff; padding: 5px 10px; font-size: 12px; color: #334155; }}
    .chip strong {{ color: #0f172a; }}
    .section {{ background: #fff; border: 1px solid #dde5ef; border-radius: 8px; padding: 18px; margin: 14px 0; break-inside: avoid; }}
    .hero {{ background: #ffffff; border: 1px solid #dde5ef; border-radius: 8px; padding: 18px; }}
    .thumbnail {{ width: 100%; border: 1px solid #dde5ef; border-radius: 8px; background: #f8fafc; object-fit: contain; }}
    .placeholder {{ min-height: 180px; display: grid; place-items: center; color: #64748b; font-size: 13px; }}
    .boundary {{ color: #7f1d1d; background: #fff7ed; border-color: #fed7aa; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .metric {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #f8fafc; }}
    .metric span {{ display: block; color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 16px; color: #0f172a; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.45; }}
    ul {{ padding-left: 20px; }}
    .muted {{ color: #64748b; }}
    @media (max-width: 760px) {{ header, .grid {{ grid-template-columns: 1fr; }} main {{ padding: 20px 14px 32px; }} }}
    @media print {{ body {{ background: #fff; }} main {{ padding: 0; }} .section, .hero {{ border-color: #cbd5e1; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="hero">
      <h1>Engineering Report</h1>
      <p>{project_name}</p>
      <div class="meta">
        <span class="chip"><strong>Project</strong> {project_id}</span>
        <span class="chip"><strong>Generated</strong> {generated_at}</span>
        <span class="chip"><strong>Credibility</strong> {status_chip}</span>
        <span class="chip"><strong>Claim advancement</strong> none</span>
      </div>
    </div>
    {thumbnail_html}
  </header>

  <section class="section boundary">
    <h2>Honesty Boundary</h2>
    <p>{html.escape(REPORT_BOUNDARY)}</p>
  </section>

  <section class="section">
    <h2>Credibility Stamp</h2>
    <div class="grid">
      <div class="metric"><span>Overall</span><strong>{html.escape(str(credibility_summary.get("overall") or "unknown"))}</strong></div>
      <div class="metric"><span>Geometry</span><strong>{html.escape(str(credibility_summary.get("geometry_evidence") or "unknown"))}</strong></div>
      <div class="metric"><span>CAE</span><strong>{html.escape(str(credibility_summary.get("cae_evidence") or "unknown"))}</strong></div>
      <div class="metric"><span>Results</span><strong>{html.escape(str(credibility_summary.get("result_evidence") or "unknown"))}</strong></div>
    </div>
  </section>

  <section class="section">
    <h2>Bill of Materials</h2>
    {_html_block(bom_markdown)}
  </section>

  <section class="section">
    <h2>Evidence Coverage</h2>
    <p class="muted">Review packet section statuses: {html.escape(str(status_counts))}</p>
    {_html_block(review_markdown)}
  </section>

  <section class="section">
    <h2>Missing Evidence</h2>
    {_html_list([str(item) for item in missing])}
  </section>

  <section class="section">
    <h2>Warnings</h2>
    {_html_list([str(item) for item in warnings])}
  </section>
</main>
</body>
</html>
"""


def generate_engineering_report(settings: Settings, project_id: str) -> dict[str, Any]:
    """Return a self-contained HTML report from existing project evidence only."""
    project = get_project(settings, project_id)
    package_path = resolve_project_path(settings, project_id, project.get("aieng_file"))
    if package_path is None or not package_path.exists():
        raise HTTPException(status_code=404, detail=".aieng package not found")

    bom_markdown, bom_warnings = _bom_markdown(settings, project_id)
    review_packet = _review_packet(settings, project_id)
    credibility = _credibility(settings, project_id, package_path)
    thumbnail_uri = _thumbnail_data_uri(package_path)
    warnings = list(bom_warnings)
    warnings.extend(str(item) for item in (review_packet.get("warnings") or []))
    warnings.extend(str(item) for item in (credibility.get("warnings") or []))

    payload: dict[str, Any] = {
        "ok": True,
        "schema_version": REPORT_SCHEMA_VERSION,
        "project": {
            "id": project_id,
            "name": project.get("name"),
            "package_path": str(package_path),
        },
        "report": {
            "generated_at": now_iso(),
            "claim_advancement": CLAIM_ADVANCEMENT,
            "claim_boundary": REPORT_BOUNDARY,
            "format": "html",
            "thumbnail_embedded": bool(thumbnail_uri),
            "thumbnail_data_uri": thumbnail_uri,
            "bom_markdown": bom_markdown,
            "warnings": warnings,
        },
        "credibility": credibility,
        "review_packet": review_packet,
    }
    payload["html"] = _html_report(payload)
    return payload


__all__ = [
    "CLAIM_ADVANCEMENT",
    "REPORT_BOUNDARY",
    "REPORT_SCHEMA_VERSION",
    "generate_engineering_report",
]
