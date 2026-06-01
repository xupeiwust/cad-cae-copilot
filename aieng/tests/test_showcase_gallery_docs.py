"""Smoke tests verifying showcase gallery docs point to existing files.

Lightweight checks — does not run heavy demos, only verifies paths and structure.
"""
from __future__ import annotations

import json
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_GALLERY_JSON = _WORKSPACE_ROOT / "aieng" / "docs" / "showcase_gallery.json"
_GALLERY_MD = _WORKSPACE_ROOT / "aieng" / "docs" / "showcase_gallery.md"


def test_gallery_json_exists():
    assert _GALLERY_JSON.exists(), f"missing {_GALLERY_JSON}"


def test_gallery_md_exists():
    assert _GALLERY_MD.exists(), f"missing {_GALLERY_MD}"


def test_gallery_json_has_required_entries():
    with open(_GALLERY_JSON, "r", encoding="utf-8") as f:
        doc = json.load(f)
    assert doc.get("format") == "aieng.showcase_gallery.v0"
    entries = doc.get("entries") or []
    ids = {e["id"] for e in entries if isinstance(e, dict)}
    required = {
        "single_part_topopt_bracket",
        "mesh_to_cad_step_reconstruction",
        "assembly_aware_topopt_bracket",
        "agent_guided_design_study_bracket",
    }
    missing = required - ids
    assert not missing, f"missing showcase entries: {missing}"


def test_gallery_json_entries_have_expected_fields():
    with open(_GALLERY_JSON, "r", encoding="utf-8") as f:
        doc = json.load(f)
    entries = doc.get("entries") or []
    for e in entries:
        for field in ("id", "title", "capability_area", "maturity", "showcase_ready",
                      "fixture_paths", "run_commands", "expected_artifacts",
                      "honesty_boundary", "limitations", "talking_points"):
            assert field in e, f"entry {e.get('id')} missing field {field}"
        assert isinstance(e.get("fixture_paths"), list)
        assert isinstance(e.get("run_commands"), list)
        assert isinstance(e.get("expected_artifacts"), list)


def test_gallery_json_fixture_paths_exist():
    """Referenced fixture/test paths should exist (relative to workspace root)."""
    with open(_GALLERY_JSON, "r", encoding="utf-8") as f:
        doc = json.load(f)
    entries = doc.get("entries") or []
    missing: list[str] = []
    for e in entries:
        for p in e.get("fixture_paths") or []:
            full = _WORKSPACE_ROOT / p
            if not full.exists():
                missing.append(p)
    assert not missing, f"missing fixture paths: {missing}"


def test_gallery_md_covers_all_json_entries():
    """Markdown should mention each JSON entry id (by title or id substring)."""
    with open(_GALLERY_JSON, "r", encoding="utf-8") as f:
        doc = json.load(f)
    with open(_GALLERY_MD, "r", encoding="utf-8") as f:
        md = f.read()
    entries = doc.get("entries") or []
    missing: list[str] = []
    for e in entries:
        title = e.get("title", "")
        if title.lower() not in md.lower():
            missing.append(e.get("id"))
    assert not missing, f"markdown missing sections for: {missing}"
