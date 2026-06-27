"""Tests for the Engineering Review Support Packet (v0.31).

Covers the safety boundary: the preview endpoint is read-only, the export
endpoint only writes packet artifacts, missing evidence is never fabricated,
and the response carries claim_advancement == "none".

Also pins a golden snapshot of the Markdown output for the rich fixture so
that future section changes cannot silently drop content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.config import Settings

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

# Phrases that must NOT appear in any preview or exported packet markdown.
# (The boundary statement uses negated forms — those are fine; we look for the
# affirmative ones the spec prohibits.)
_PROHIBITED_PHRASES = (
    "design is certified",
    "design is validated",
    "guaranteed safe",
    "approved design",
)


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project(
    settings: Settings, name: str, package_name: str
) -> tuple[str, Path]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(name))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / package_name
    project["aieng_file"] = package_name
    save_project(settings, project)
    return project_id, pkg_path


def _write_minimal_package(pkg_path: Path) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "review-test", "resources": {}}))


def _write_rich_package(pkg_path: Path) -> None:
    """Package with targets + metrics + freecad evidence + solver run + audit + stale state."""
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    targets_doc = {
        "schema_version": "0.1",
        "targets": [
            {
                "target_id": "stress_pass",
                "label": "Stress pass",
                "metric": "max_von_mises_stress",
                "operator": "<=",
                "value": 200,
                "unit": "MPa",
                "load_case_id": "lc1",
                "priority": "high",
                "rationale": "Below yield with safety margin.",
            },
            {
                "target_id": "stress_fail",
                "label": "Stress fail",
                "metric": "max_von_mises_stress",
                "operator": "<=",
                "value": 1.0,
                "unit": "MPa",
                "load_case_id": "lc1",
            },
        ],
    }
    metrics_doc = {
        "schema_version": "0.1",
        "metrics_source": {"tool": "test", "format": "json", "imported_by": "fixture"},
        "global_metrics": {"mass": {"value": 1.2, "unit": "kg"}},
        "load_cases": [
            {
                "load_case_id": "lc1",
                "metrics": {"max_von_mises_stress": {"value": 187.4, "unit": "MPa"}},
            }
        ],
    }
    parsed_features = {
        "bridge_provider": "freecad_mcp",
        "generated_at": "2026-05-19T12:00:00Z",
        "features": [
            {"id": "f1", "name": "Pad", "parameters": {"Length": 10.0}},
            {"id": "f2", "name": "Fillet", "parameters": {}},
        ],
    }
    feature_graph = {"features": parsed_features["features"]}
    solver_run = {
        "run_id": "run_001",
        "solver": "CalculiX",
        "state": "completed",
        "solved": True,
        "return_code": 0,
        "started_at": "2026-05-19T12:01:00Z",
        "finished_at": "2026-05-19T12:01:02Z",
    }
    audit_events = "\n".join(
        json.dumps(e)
        for e in [
            {
                "timestamp": "2026-05-19T12:01:02Z",
                "tool": "cae.run_solver",
                "status": "solver_run_completed",
                "artifacts_written": ["simulation/runs/run_001/solver_run.json"],
            },
            {
                "timestamp": "2026-05-19T12:00:30Z",
                "tool": "cad.edit_parameter",
                "status": "approved",
                "payload": {
                    "proposal_id": "p1",
                    "parameter": "Pad.Length",
                    "old_value": 8.0,
                    "new_value": 10.0,
                },
            },
        ]
    )
    revalidation = {
        "requires_revalidation": True,
        "current_geometry_revision": 2,
        "last_validated_geometry_revision": 1,
        "stale_artifacts": ["results/computed_metrics.json"],
    }
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "review-rich", "resources": {}}))
        zf.writestr("task/design_targets.yaml", yaml.safe_dump(targets_doc, sort_keys=False))
        zf.writestr("results/computed_metrics.json", json.dumps(metrics_doc))
        zf.writestr("simulation/cae_imports/parsed_features.json", json.dumps(parsed_features))
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))
        zf.writestr("simulation/runs/run_001/solver_input.inp", "*HEADING\nfixture\n")
        zf.writestr("simulation/runs/run_001/outputs/result.frd", "    1C\n 9999\n")
        zf.writestr("simulation/runs/run_001/solver_run.json", json.dumps(solver_run))
        zf.writestr("audit/events.jsonl", audit_events + "\n")
        zf.writestr("state/revalidation_status.json", json.dumps(revalidation))


def _package_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _section_by_id(body: dict[str, Any], sid: str) -> dict[str, Any]:
    for sec in body.get("sections") or []:
        if sec["id"] == sid:
            return sec
    raise AssertionError(f"section {sid!r} not in response: {[s['id'] for s in body['sections']]}")


# ── safety: preview is read-only ──────────────────────────────────────────────


def test_preview_is_read_only_does_not_modify_package(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "preview-readonly", "p.aieng")
    _write_minimal_package(pkg)
    before = _package_digest(pkg)

    resp = client.get(f"/api/projects/{project_id}/review-support-packet/preview")
    assert resp.status_code == 200, resp.text
    after = _package_digest(pkg)
    assert before == after, "preview must not mutate the package"

    body = resp.json()
    assert body["ok"] is True
    assert body["packet_id"]
    assert body["claim_advancement"] == "none"
    assert body["claim_boundary"]
    assert body["markdown_path"] is None
    assert body["manifest_path"] is None
    assert body["preview_markdown"] is not None
    assert "Engineering Review Support Packet" in body["preview_markdown"]


def test_preview_includes_claim_boundary_in_markdown(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "preview-boundary", "p.aieng")
    _write_minimal_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    md = body["preview_markdown"]
    assert "Safety boundary" in md
    assert "does not certify" in md.lower()
    assert "claim advancement" in md.lower()


def test_missing_targets_is_explicit_not_invented(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "no-targets", "p.aieng")
    _write_minimal_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "design_targets")
    assert sec["status"] == "missing"
    md = body["preview_markdown"]
    assert "No design targets were found" in md


def test_missing_metrics_is_explicit_not_invented(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "no-metrics", "p.aieng")
    _write_minimal_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "computed_metrics")
    assert sec["status"] == "missing"
    assert "No computed metrics were found" in body["preview_markdown"]


def test_missing_cad_approval_is_explicit(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "no-cad", "p.aieng")
    _write_minimal_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "cad_approval")
    assert sec["status"] == "missing"
    assert "No approval-gated CAD parameter edit records found" in body["preview_markdown"]


def test_missing_solver_evidence_is_explicit(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "no-solver", "p.aieng")
    _write_minimal_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "structural_solver")
    assert sec["status"] == "missing"
    assert "No structural solver run evidence found" in body["preview_markdown"]
    cred = _section_by_id(body, "cae_credibility")
    assert cred["status"] == "missing"
    assert "| Credibility tier | `no_result_artifact` |" in body["preview_markdown"]


def test_preview_does_not_500_when_project_has_no_package(tmp_path: Path) -> None:
    from app.main import default_project, save_project

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("no-pkg"))
    project_id = project["id"]

    resp = client.get(f"/api/projects/{project_id}/review-support-packet/preview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    # Most sections degrade to "missing" without a package; none should be "error".
    for sec in body["sections"]:
        assert sec["status"] != "error", f"section {sec['id']} errored"


# ── rich package: sections include real evidence ──────────────────────────────


def test_target_comparison_summary_present_when_evaluable(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "rich-tc", "p.aieng")
    _write_rich_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "target_comparison")
    md = body["preview_markdown"]
    assert sec["status"] == "included"
    assert "pass" in md.lower() and "fail" in md.lower()


def test_preview_includes_cae_credibility_tier(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "rich-credibility", "p.aieng")
    _write_rich_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "cae_credibility")
    md = body["preview_markdown"]

    assert sec["status"] == "partial"
    assert "results/computed_metrics.json" in sec["artifact_paths"]
    assert "simulation/runs/run_001/outputs/result.frd" in sec["artifact_paths"]
    assert "CAE Credibility" in md
    assert "| Credibility tier | `numerical_result_parsed` |" in md
    assert "| Missing next evidence | plausibility_checked |" in md
    assert "| Certified | False |" in md
    assert "does not run a solver or advance claims" in md


# ── export: writes only packet artifacts ──────────────────────────────────────


def test_preview_includes_evidence_lifecycle_rollup(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "rich-lifecycle", "p.aieng")
    _write_rich_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "evidence_lifecycle")
    md = body["preview_markdown"]

    assert sec["status"] in {"included", "partial"}
    assert "Evidence Lifecycle" in md
    assert "| stale |" in md
    assert "Missing evidence remains unknown/not evaluated" in md
    assert body["claim_advancement"] == "none"


def _members(pkg: Path) -> set[str]:
    with zipfile.ZipFile(pkg, "r") as zf:
        return set(zf.namelist())


def test_export_writes_only_review_support_artifacts(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "export-only", "p.aieng")
    _write_rich_package(pkg)
    before_members = _members(pkg)

    resp = client.post(f"/api/projects/{project_id}/review-support-packet/export", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["markdown_path"]
    assert body["manifest_path"]
    assert body["markdown_path"].startswith("reports/review_support/")
    assert body["manifest_path"].startswith("reports/review_support/")

    after_members = _members(pkg)
    new_members = after_members - before_members
    # All new members must live under reports/review_support/.
    for member in new_members:
        assert member.startswith("reports/review_support/"), (
            f"export wrote a member outside reports/review_support/: {member}"
        )
    assert body["markdown_path"] in after_members
    assert body["manifest_path"] in after_members


def test_exported_markdown_and_manifest_are_consistent(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "export-content", "p.aieng")
    _write_rich_package(pkg)

    body = client.post(f"/api/projects/{project_id}/review-support-packet/export", json={}).json()
    with zipfile.ZipFile(pkg, "r") as zf:
        md = zf.read(body["markdown_path"]).decode("utf-8")
        manifest = json.loads(zf.read(body["manifest_path"]).decode("utf-8"))

    assert "Engineering Review Support Packet" in md
    assert manifest["packet_id"] == body["packet_id"]
    assert manifest["project_id"] == project_id
    assert manifest["claim_advancement"] == "none"
    assert manifest["markdown_path"] == body["markdown_path"]
    assert manifest["json_path"] == body["manifest_path"]
    sec_ids = {s["id"] for s in manifest["sections"]}
    assert "header" in sec_ids and "safety_boundary" in sec_ids
    lifecycle = next(s for s in manifest["sections"] if s["id"] == "evidence_lifecycle")
    assert lifecycle["data"]["claim_advancement"] == "none"
    assert "missing" in lifecycle["data"]["summary"]


def test_export_returns_404_or_error_when_package_missing(tmp_path: Path) -> None:
    from app.main import default_project, save_project

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("no-pkg-export"))
    project_id = project["id"]

    resp = client.post(f"/api/projects/{project_id}/review-support-packet/export", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert any("package" in (e or "").lower() for e in body["errors"])
    assert body["claim_advancement"] == "none"


def test_export_does_not_run_solver_or_cad_or_preflight(tmp_path: Path, monkeypatch) -> None:
    """Export must not invoke any solver/CAD/runtime subprocess."""
    import subprocess

    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "export-quiet", "p.aieng")
    _write_rich_package(pkg)

    called: list[Any] = []

    def banned_run(*args, **kwargs):  # pragma: no cover - asserted not called
        called.append((args, kwargs))
        raise AssertionError("subprocess.run must not be called from review packet export")

    monkeypatch.setattr(subprocess, "run", banned_run)
    resp = client.post(f"/api/projects/{project_id}/review-support-packet/export", json={})
    assert resp.status_code == 200, resp.text
    assert called == []


# ── prohibited certification language ────────────────────────────────────────


def test_no_prohibited_certification_language(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "no-cert", "p.aieng")
    _write_rich_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    md_lower = body["preview_markdown"].lower()
    for phrase in _PROHIBITED_PHRASES:
        assert phrase not in md_lower, f"prohibited phrase {phrase!r} appeared in packet markdown"


# ── content cap behaviour ────────────────────────────────────────────────────


# ── golden snapshot of the rich-fixture markdown ─────────────────────────────

_SNAPSHOT_DIR = Path(__file__).parent / "fixtures"
_RICH_SNAPSHOT_PATH = _SNAPSHOT_DIR / "review_support_packet_rich.md"


def _normalize_markdown(md: str, *, project_id: str, tmp_root: Path) -> str:
    """Strip volatile fields so the rich-fixture markdown is byte-stable.

    Replaces packet ids, project ids, ISO timestamps, and the per-test temp
    path. Without this, every run would diff against the golden file because
    of the generated_at timestamp alone.
    """
    text = md
    text = re.sub(r"packet_\d{8}T\d{6}Z_[0-9a-f]{6}", "<PACKET_ID>", text)
    text = re.sub(rf"\b{re.escape(project_id)}\b", "<PROJECT_ID>", text)
    # ISO timestamps with optional fractional seconds and TZ.
    text = re.sub(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
        "<ISO>",
        text,
    )
    # Per-test temp path (e.g. C:\Users\…\Temp\pytest-of-…\…).
    tmp_str = str(tmp_root)
    text = text.replace(tmp_str, "<TMP>").replace(tmp_str.replace("\\", "/"), "<TMP>")
    # Normalize Windows backslashes for portable comparison.
    text = text.replace("\\", "/")
    return text


def test_rich_fixture_markdown_matches_golden_snapshot(tmp_path: Path) -> None:
    """Pin the Markdown output for the rich fixture as a golden file.

    Regenerate after intentional section changes with:
        UPDATE_SNAPSHOTS=1 pytest tests/test_review_support_packet.py::test_rich_fixture_markdown_matches_golden_snapshot
    """
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "snap", "p.aieng")
    _write_rich_package(pkg)

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    actual = _normalize_markdown(body["preview_markdown"], project_id=project_id, tmp_root=tmp_path)

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        _RICH_SNAPSHOT_PATH.write_text(actual, encoding="utf-8")
        return

    assert _RICH_SNAPSHOT_PATH.exists(), (
        f"missing snapshot {_RICH_SNAPSHOT_PATH}; regenerate with UPDATE_SNAPSHOTS=1"
    )
    expected = _RICH_SNAPSHOT_PATH.read_text(encoding="utf-8")
    if actual != expected:
        # Surface the first diverging line to make snapshot drift easy to read.
        actual_lines = actual.splitlines()
        expected_lines = expected.splitlines()
        max_lines = max(len(actual_lines), len(expected_lines))
        first_diff = None
        for i in range(max_lines):
            a = actual_lines[i] if i < len(actual_lines) else "<EOF>"
            e = expected_lines[i] if i < len(expected_lines) else "<EOF>"
            if a != e:
                first_diff = (i + 1, e, a)
                break
        diff_msg = (
            "review packet markdown drifted from snapshot."
            f" First diverging line {first_diff[0] if first_diff else '?'}:"
            f"\n  expected: {first_diff[1] if first_diff else 'n/a'}"
            f"\n  actual:   {first_diff[2] if first_diff else 'n/a'}"
            f"\n(regenerate with UPDATE_SNAPSHOTS=1 if the change is intentional)"
        )
        raise AssertionError(diff_msg)


def test_long_audit_events_are_capped_or_summarized(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project_id, pkg = _make_project(settings, "many-audit", "p.aieng")
    _write_minimal_package(pkg)
    # Append a large audit log.
    many = "\n".join(
        json.dumps(
            {
                "timestamp": f"2026-05-19T12:00:{i:02d}Z",
                "tool": "aieng.inspect_package",
                "status": "completed",
                "artifacts_written": [],
            }
        )
        for i in range(100)
    )
    with zipfile.ZipFile(pkg, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("audit/events.jsonl", many + "\n")

    body = client.get(f"/api/projects/{project_id}/review-support-packet/preview").json()
    sec = _section_by_id(body, "audit_trail")
    # Status reflects that capping happened or stayed within cap.
    assert sec["status"] in {"included", "partial"}
    md = body["preview_markdown"]
    # Either an explicit truncation note or status="partial" is acceptable.
    if sec["status"] == "partial":
        assert "earlier event(s) not shown" in md
