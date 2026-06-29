from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.config import Settings


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "aieng-ui" / "backend" / "scripts" / "value_demo_packet.py"
RUNBOOK = ROOT / "docs" / "cad-cae-value-demo.md"


def _load_packet_module():
    spec = importlib.util.spec_from_file_location("value_demo_packet", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _make_project_with_package(settings: Settings, pkg_path: Path) -> str:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project("value-demo-check"))
    project_id = project["id"]
    target = project_dir(settings, project_id) / "value-demo.aieng"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pkg_path.read_bytes())
    project["aieng_file"] = "value-demo.aieng"
    save_project(settings, project)
    return project_id


def test_value_demo_packet_anchors_real_frd_pipeline_and_honesty_boundaries() -> None:
    module = _load_packet_module()
    packet = module.build_packet()
    markdown = module.build_markdown()

    assert packet["geometry"]["kind"] == "single_connected_solid"
    assert "result = beam" in packet["geometry"]["cad_code"]
    assert "cae.run_simulation_pipeline" in markdown
    assert "report.generate" in markdown
    assert "simulation/runs/value_demo_run_001/outputs/result.frd" in packet["expected_evidence"]
    assert "results/computed_metrics.json" in packet["expected_evidence"]
    assert any("Synthetic fallback fields are a failed demo condition" in item for item in packet["honesty_boundaries"])
    assert any("mesh-dependent" in item for item in packet["honesty_boundaries"])


def test_value_demo_runbook_links_packet_and_forbids_synthetic_success() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "aieng-ui/backend/scripts/value_demo_packet.py" in text
    assert "cae.run_simulation_pipeline" in text
    assert "report.generate" in text
    assert "simulation/runs/value_demo_run_001/outputs/result.frd" in text
    assert "aieng.value_demo_check" in text
    assert "Synthetic fallback fields are a failed demo condition" in text
    assert "Do not invent face" in text
    assert "not certification" in text


def _write_demo_package(path: Path, *, complete: bool = True, synthetic_summary: bool = False) -> None:
    members = {
        "geometry/generated.step": "ISO-10303-21;\nEND-ISO-10303-21;\n",
        "geometry/topology_map.json": json.dumps({"entities": []}),
        "graph/feature_graph.json": json.dumps({"features": []}),
        "simulation/setup.yaml": "materials: []\n",
        "simulation/cae_mapping.json": json.dumps({"faces": {}}),
        "simulation/mesh/mesh.inp": "*NODE\n1,0,0,0\n",
        "simulation/runs/value_demo_run_001/solver_input.inp": "*HEADING\nvalue demo\n",
        "simulation/runs/value_demo_run_001/solver_run.json": json.dumps({
            "status": "completed",
            "solved": True,
            "return_code": 0,
        }),
        "results/computed_metrics.json": json.dumps({
            "load_cases": [{
                "metrics": {
                    "max_displacement": {"value": 0.1, "unit": "mm"},
                    "max_von_mises_stress": {"value": 12.0, "unit": "MPa"},
                },
            }],
        }),
        "results/result_summary.json": json.dumps({
            "source": (
                {"format": "vertex_synthetic", "note": "synthetic fallback"}
                if synthetic_summary
                else {"source_frd": "simulation/runs/value_demo_run_001/outputs/result.frd"}
            ),
        }),
        "simulation/runs/value_demo_run_001/outputs/result.frd": "    1PSTEP\n",
        "reports/value_demo.html": "<html><body>report</body></html>",
    }
    if not complete:
        members.pop("simulation/runs/value_demo_run_001/outputs/result.frd")
        members.pop("results/computed_metrics.json")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for member, content in members.items():
            zf.writestr(member, content)


def test_value_demo_package_checker_passes_complete_real_frd_package(tmp_path: Path) -> None:
    module = _load_packet_module()
    pkg = tmp_path / "complete.aieng"
    _write_demo_package(pkg)

    report = module.check_package(pkg)
    markdown = module.render_check_markdown(report)

    assert report["status"] == "pass"
    assert not report["missing_evidence"]
    assert {check["id"]: check["status"] for check in report["checks"]}["real_frd_result"] == "pass"
    assert "PASS" in markdown
    assert "not certification" in markdown


def test_value_demo_package_checker_blocks_missing_or_synthetic_evidence(tmp_path: Path) -> None:
    module = _load_packet_module()
    pkg = tmp_path / "incomplete.aieng"
    _write_demo_package(pkg, complete=False, synthetic_summary=True)

    report = module.check_package(pkg)
    by_id = {check["id"]: check for check in report["checks"]}

    assert report["status"] == "blocked"
    assert "simulation/runs/value_demo_run_001/outputs/result.frd" in report["missing_evidence"]
    assert "results/computed_metrics.json" in report["missing_evidence"]
    assert by_id["real_frd_result"]["status"] == "fail"
    assert by_id["computed_metrics"]["status"] == "fail"
    assert by_id["viewer_field_source"]["status"] == "fail"


def test_value_demo_check_runtime_tool_checks_project_package(tmp_path: Path) -> None:
    pkg = tmp_path / "complete.aieng"
    _write_demo_package(pkg)
    settings = _make_settings(tmp_path)
    project_id = _make_project_with_package(settings, pkg)
    client = TestClient(create_app(settings))

    resp = client.post(
        "/api/agent/invoke-tool",
        json={"tool": "aieng.value_demo_check", "input": {"project_id": project_id}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "aieng.value_demo_check"
    assert body["status"] == "pass"
    assert body["ok"] is True
    assert body["project_id"] == project_id
    assert body["claim_advancement"] == "none"
    assert not body["missing_evidence"]
    assert any(check["id"] == "real_frd_result" and check["status"] == "pass" for check in body["checks"])


def test_value_demo_check_runtime_tool_blocks_missing_package(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings))

    resp = client.post("/api/agent/invoke-tool", json={"tool": "aieng.value_demo_check", "input": {}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["code"] == "missing_package"


def test_value_demo_check_endpoint_reports_complete_project_package(tmp_path: Path) -> None:
    pkg = tmp_path / "complete.aieng"
    _write_demo_package(pkg)
    settings = _make_settings(tmp_path)
    project_id = _make_project_with_package(settings, pkg)
    client = TestClient(create_app(settings))

    resp = client.get(f"/api/projects/{project_id}/value-demo-check")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pass"
    assert body["ok"] is True
    assert body["project_id"] == project_id
    assert body["claim_advancement"] == "none"
    assert any(check["id"] == "real_frd_result" and check["status"] == "pass" for check in body["checks"])


def test_value_demo_check_endpoint_missing_package_is_graceful(tmp_path: Path) -> None:
    from app.main import default_project, save_project

    settings = _make_settings(tmp_path)
    project_id = save_project(settings, default_project("empty-value-demo"))["id"]
    client = TestClient(create_app(settings))

    resp = client.get(f"/api/projects/{project_id}/value-demo-check")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["code"] == "missing_package"
    assert body["checks"] == []
