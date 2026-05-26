"""Computed Metrics Import & Target Mapping UX v0.12 backend tests."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.main import Settings, create_app, default_project, project_dir, save_project

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


def _make_package(
    pkg_path: Path,
    *,
    computed_metrics: dict[str, Any] | None = None,
    design_targets: list[dict[str, Any]] | None = None,
) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        if computed_metrics is not None:
            zf.writestr("results/computed_metrics.json", json.dumps(computed_metrics))
        if design_targets is not None:
            zf.writestr(
                "task/design_targets.yaml",
                yaml.safe_dump({"schema_version": "0.1", "targets": design_targets}, sort_keys=False, allow_unicode=True),
            )


def _client_project(tmp_path: Path, *, computed_metrics: dict[str, Any] | None = None, design_targets: list[dict[str, Any]] | None = None) -> tuple[TestClient, str, Path]:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))
    project = save_project(settings, default_project("metrics"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "test.aieng"
    _make_package(pkg_path, computed_metrics=computed_metrics, design_targets=design_targets)
    project["aieng_file"] = "test.aieng"
    save_project(settings, project)
    return client, project_id, pkg_path


def _simple_doc() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "global_metrics": {"mass": {"value": 1.24, "unit": "kg"}},
        "load_cases": [
            {
                "load_case_id": "load_case_001",
                "metrics": {
                    "max_von_mises_stress": {"value": 187.4, "unit": "MPa"},
                    "max_displacement": {"value": 0.82, "unit": "mm"},
                },
            }
        ],
    }


def test_get_computed_metrics_returns_empty_when_artifact_missing(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    resp = client.get(f"/api/projects/{project_id}/computed-metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["document"] is None
    assert body["metrics_count"] == 0
    assert any("No computed metrics artifact" in w for w in body["warnings"])


def test_get_computed_metrics_returns_existing_metrics(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path, computed_metrics=_simple_doc())
    resp = client.get(f"/api/projects/{project_id}/computed-metrics")
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["artifact_path"] == "results/computed_metrics.json"
    assert body["metrics_count"] == 3
    assert body["load_case_count"] == 1
    assert body["document"]["load_cases"][0]["metrics"]["max_displacement"]["value"] == 0.82


def test_preview_json_full_document_succeeds_and_maps_target(tmp_path: Path) -> None:
    targets = [{"target_id": "stress_limit", "label": "Stress", "metric": "max_von_mises_stress", "operator": "<=", "value": 200, "load_case_id": "load_case_001"}]
    client, project_id, _pkg = _client_project(tmp_path, design_targets=targets)
    resp = client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "json", "document": _simple_doc()})
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["metrics_count"] == 3
    assert body["target_mapping"][0]["status"] == "mapped"


def test_preview_json_simple_object_succeeds(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    text = json.dumps({"max_von_mises_stress": {"value": 187.4, "unit": "MPa"}, "max_displacement": {"value": 0.82, "unit": "mm"}})
    resp = client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "json", "text": text})
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["document"]["global_metrics"]["max_von_mises_stress"]["value"] == 187.4


def test_preview_csv_succeeds(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    csv_text = "metric,value,unit,load_case_id\nmax_von_mises_stress,187.4,MPa,load_case_001\nmass,1.24,kg,\n"
    resp = client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "csv", "text": csv_text})
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is True
    assert body["metrics_count"] == 2
    assert body["load_case_count"] == 1


def test_preview_invalid_json_returns_structured_error(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    resp = client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "json", "text": "{bad"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "invalid_json"


def test_preview_invalid_csv_non_numeric_value_returns_structured_error(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    resp = client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "csv", "text": "metric,value\nmax_stress,abc\n"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "invalid_value"
    assert body["errors"][0]["row"] == 2


def test_preview_unsupported_format_returns_structured_error(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    resp = client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "xlsx", "text": ""})
    body = resp.json()
    assert resp.status_code == 200
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "unsupported_format"


def test_get_and_preview_do_not_change_package_digest(tmp_path: Path) -> None:
    client, project_id, pkg = _client_project(tmp_path)
    before = hashlib.sha256(pkg.read_bytes()).hexdigest()
    client.get(f"/api/projects/{project_id}/computed-metrics")
    client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "json", "document": _simple_doc()})
    after = hashlib.sha256(pkg.read_bytes()).hexdigest()
    assert before == after


def test_put_valid_metrics_writes_artifact_and_roundtrips(tmp_path: Path) -> None:
    client, project_id, pkg = _client_project(tmp_path)
    before = hashlib.sha256(pkg.read_bytes()).hexdigest()
    with zipfile.ZipFile(pkg, "r") as zf:
        names_before = set(zf.namelist())
    resp = client.put(f"/api/projects/{project_id}/computed-metrics", json=_simple_doc())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["changed_artifact_path"] == "results/computed_metrics.json"
    assert hashlib.sha256(pkg.read_bytes()).hexdigest() != before

    with zipfile.ZipFile(pkg, "r") as zf:
        names_after = set(zf.namelist())
        assert "results/computed_metrics.json" in names_after
        assert names_after - names_before == {"results/computed_metrics.json"}
        assert "ai/claim_map.json" not in names_after
        written = json.loads(zf.read("results/computed_metrics.json"))
    assert written["load_cases"][0]["metrics"]["max_von_mises_stress"]["value"] == 187.4

    get_body = client.get(f"/api/projects/{project_id}/computed-metrics").json()
    assert get_body["metrics_count"] == 3


def test_put_rejects_nan_and_infinity(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    for value in ("NaN", "Infinity"):
        resp = client.put(
            f"/api/projects/{project_id}/computed-metrics",
            json={"format": "json", "text": f'{{"bad_metric": {{"value": {value}}}}}'},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["errors"][0]["code"] == "invalid_value"


def test_put_rejects_duplicate_metrics_within_same_load_case(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    payload = {
        "schema_version": "0.1",
        "load_cases": [
            {"load_case_id": "lc1", "metrics": {"max_stress": {"value": 1}}},
            {"load_case_id": "lc1", "metrics": {"max_stress": {"value": 2}}},
        ],
    }
    resp = client.put(f"/api/projects/{project_id}/computed-metrics", json=payload)
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"][0]["code"] == "duplicate_metric"


def test_health_check_missing_metrics_action_disappears_after_put(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path, design_targets=[{"target_id": "m", "label": "Mass", "metric": "mass", "operator": "<=", "value": 2}])
    before = client.get(f"/api/projects/{project_id}/health-check").json()
    assert any(a["id"] == "import_computed_metrics" for a in before["recommended_actions"])

    put = client.put(f"/api/projects/{project_id}/computed-metrics", json={"mass": {"value": 1.24, "unit": "kg"}})
    assert put.status_code == 200

    after = client.get(f"/api/projects/{project_id}/health-check").json()
    metric_check = next(c for c in after["checks"] if c["id"] == "computed_metrics")
    assert metric_check["status"] == "passed"
    assert not any(a["id"] == "import_computed_metrics" for a in after["recommended_actions"])


def test_target_mapping_missing_and_ambiguous_are_honest(tmp_path: Path) -> None:
    targets = [
        {"target_id": "missing", "label": "Missing", "metric": "min_safety_factor", "operator": ">=", "value": 1.5},
        {"target_id": "ambiguous", "label": "Stress", "metric": "max_stress", "operator": "<=", "value": 200},
    ]
    client, project_id, _pkg = _client_project(tmp_path, design_targets=targets)
    payload = {
        "load_cases": [
            {"load_case_id": "lc1", "metrics": {"max_stress": {"value": 10}}},
            {"load_case_id": "lc2", "metrics": {"max_stress": {"value": 12}}},
        ],
    }
    body = client.post(f"/api/projects/{project_id}/computed-metrics/preview", json={"format": "json", "document": payload}).json()
    statuses = {m["target_id"]: m["status"] for m in body["target_mapping"]}
    assert statuses["missing"] == "missing_metric"
    assert statuses["ambiguous"] == "ambiguous"


def test_import_computed_metrics_action_has_navigation_target(tmp_path: Path) -> None:
    client, project_id, _pkg = _client_project(tmp_path)
    body = client.get(f"/api/projects/{project_id}/health-check").json()
    action = next(a for a in body["recommended_actions"] if a["id"] == "import_computed_metrics")
    assert action["action_type"] == "navigate"
    assert action["target"] == {"tab": "copilot_loop", "section": "computed_metrics", "intent": "navigation"}
    assert action["safety"] == {"mutates_package": False, "runs_solver": False, "advances_claim": False}
