"""Design Targets Authoring & Import UX v0.10 — backend tests.

Verifies GET/PUT endpoints, validation, package integration, and health-check
interaction.
"""

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import (
    Settings,
    create_app,
    default_project,
    project_dir,
    save_project,
)

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_minimal_package(pkg_path: Path) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))


def _make_package_with_design_targets(pkg_path: Path, targets: list[dict[str, Any]]) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1", "targets": targets}
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        zf.writestr("task/design_targets.yaml", yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


# ---------------------------------------------------------------------------
# GET endpoint
# ---------------------------------------------------------------------------


class TestGetDesignTargets:
    def test_get_returns_empty_when_artifact_missing(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-targets"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        resp = client.get(f"/api/projects/{project_id}/design-targets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["targets"] == []
        assert any("No design target artifact" in w for w in body["warnings"])

    def test_get_returns_targets_when_present(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("with-targets"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        targets = [
            {"target_id": "t1", "label": "Mass", "metric": "mass_kg", "operator": ">=", "value": 1.5, "priority": "required"},
        ]
        _make_package_with_design_targets(pkg_path, targets)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        resp = client.get(f"/api/projects/{project_id}/design-targets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert len(body["targets"]) == 1
        assert body["targets"][0]["target_id"] == "t1"
        assert body["warnings"] == []

    def test_get_returns_404_when_package_missing(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-pkg"))
        project_id = project["id"]

        resp = client.get(f"/api/projects/{project_id}/design-targets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert any("no .aieng package" in w.lower() for w in body["warnings"])

    def test_get_returns_warning_for_invalid_artifact(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("bad-targets"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        pkg_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pkg_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"model_id": "test"}))
            zf.writestr("task/design_targets.yaml", "not: valid: yaml: [")
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        resp = client.get(f"/api/projects/{project_id}/design-targets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert any("not valid" in w.lower() for w in body["warnings"])


# ---------------------------------------------------------------------------
# PUT endpoint
# ---------------------------------------------------------------------------


class TestPutDesignTargets:
    def test_put_writes_targets(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("write-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [
            {"target_id": "t1", "label": "Mass", "metric": "mass_kg", "operator": ">=", "value": 1.5, "priority": "required"},
        ]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["artifact_path"] == "task/design_targets.yaml"
        assert len(body["targets"]) == 1

        # Verify inside package
        with zipfile.ZipFile(pkg_path, "r") as zf:
            raw = zf.read("task/design_targets.yaml").decode("utf-8")
            doc = yaml.safe_load(raw)
        assert doc["targets"][0]["target_id"] == "t1"

    def test_put_accepts_document_object(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("doc-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        doc = {"schema_version": "0.1", "targets": [{"target_id": "t1", "label": "L", "metric": "m", "operator": ">=", "value": 1}]}
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=doc)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["document"]["schema_version"] == "0.1"

    def test_put_rejects_duplicate_target_ids(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("dup-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [
            {"target_id": "t1", "label": "A", "metric": "m", "operator": ">=", "value": 1},
            {"target_id": "t1", "label": "B", "metric": "m", "operator": ">=", "value": 2},
        ]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any("Duplicate target_id" in e["message"] for e in detail["errors"])

    def test_put_rejects_unsupported_operator(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("op-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [{"target_id": "t1", "label": "A", "metric": "m", "operator": "is_about", "value": 1}]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any("Unsupported operator" in e["message"] for e in detail["errors"])

    def test_put_rejects_non_numeric_value(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("val-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [{"target_id": "t1", "label": "A", "metric": "m", "operator": ">=", "value": "ten"}]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any("value must be numeric" in e["message"].lower() for e in detail["errors"])

    def test_put_rejects_too_many_targets(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("many-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [{"target_id": f"t{i}", "label": "A", "metric": "m", "operator": ">=", "value": i} for i in range(101)]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any("Too many targets" in e["message"] for e in detail["errors"])

    def test_put_limited_to_design_target_artifact(self, tmp_path: Path) -> None:
        """PUT should only write the design target artifact, not other package members."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("scope-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [{"target_id": "t1", "label": "A", "metric": "m", "operator": ">=", "value": 1}]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert resp.status_code == 200

        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = set(zf.namelist())
        assert "task/design_targets.yaml" in names
        assert "manifest.json" in names
        # No new artifacts should appear
        assert len(names) == 2

    def test_put_does_not_advance_claim(self, tmp_path: Path) -> None:
        """PUT should not create claim_map or any claim-advancing artifact."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("claim-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [{"target_id": "t1", "label": "A", "metric": "m", "operator": ">=", "value": 1}]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert resp.status_code == 200

        with zipfile.ZipFile(pkg_path, "r") as zf:
            names = set(zf.namelist())
        assert "ai/claim_map.json" not in names
        assert "claims/proposals" not in [n.split("/")[0] for n in names]

    def test_get_after_put_returns_saved_targets(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("roundtrip"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [
            {"target_id": "t1", "label": "Mass", "metric": "mass_kg", "operator": ">=", "value": 1.5},
            {"target_id": "t2", "label": "Stress", "metric": "max_stress_mpa", "operator": "<=", "value": 200, "unit": "MPa", "priority": "critical"},
        ]
        put_resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert put_resp.status_code == 200

        get_resp = client.get(f"/api/projects/{project_id}/design-targets")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["ok"] is True
        assert len(body["targets"]) == 2
        assert body["targets"][1]["unit"] == "MPa"
        assert body["warnings"] == []


# ---------------------------------------------------------------------------
# Read-only / mutation tests
# ---------------------------------------------------------------------------


class TestDesignTargetsReadOnly:
    def test_get_does_not_change_package_digest(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("readonly-get"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_package_with_design_targets(pkg_path, [{"target_id": "t1", "label": "A", "metric": "m", "operator": ">=", "value": 1}])
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        before = hashlib.sha256(pkg_path.read_bytes()).hexdigest()
        resp = client.get(f"/api/projects/{project_id}/design-targets")
        after = hashlib.sha256(pkg_path.read_bytes()).hexdigest()

        assert resp.status_code == 200
        assert before == after

    def test_put_changes_package_digest(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("mutate-put"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        before = hashlib.sha256(pkg_path.read_bytes()).hexdigest()
        targets = [{"target_id": "t1", "label": "A", "metric": "m", "operator": ">=", "value": 1}]
        resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        after = hashlib.sha256(pkg_path.read_bytes()).hexdigest()

        assert resp.status_code == 200
        assert before != after


# ---------------------------------------------------------------------------
# Health-check integration
# ---------------------------------------------------------------------------


class TestDesignTargetsHealthCheckIntegration:
    def test_missing_target_action_disappears_after_put(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("hc-integration"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        # Before: health check should warn about missing design targets
        hc_before = client.get(f"/api/projects/{project_id}/health-check").json()
        dt_check_before = next((c for c in hc_before["checks"] if c["id"] == "design_targets"), None)
        assert dt_check_before is not None
        assert dt_check_before["status"] == "warning"
        assert any(a["id"] == "add_design_targets" for a in hc_before["recommended_actions"])

        # Save design targets
        targets = [{"target_id": "t1", "label": "Mass", "metric": "mass_kg", "operator": ">=", "value": 1.5}]
        put_resp = client.put(f"/api/projects/{project_id}/design-targets", json=targets)
        assert put_resp.status_code == 200

        # After: health check should pass design targets
        hc_after = client.get(f"/api/projects/{project_id}/health-check").json()
        dt_check_after = next((c for c in hc_after["checks"] if c["id"] == "design_targets"), None)
        assert dt_check_after is not None
        assert dt_check_after["status"] == "passed"
        assert not any(a["id"] == "add_design_targets" for a in hc_after["recommended_actions"])

    def test_health_check_counts_saved_targets(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("hc-count"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        targets = [
            {"target_id": "t1", "label": "A", "metric": "m", "operator": ">=", "value": 1},
            {"target_id": "t2", "label": "B", "metric": "m", "operator": "<=", "value": 2},
            {"target_id": "t3", "label": "C", "metric": "m", "operator": "==", "value": 3},
        ]
        client.put(f"/api/projects/{project_id}/design-targets", json=targets)

        hc = client.get(f"/api/projects/{project_id}/health-check").json()
        dt_check = next((c for c in hc["checks"] if c["id"] == "design_targets"), None)
        assert dt_check is not None
        assert "3 design target(s)" in dt_check["summary"]
