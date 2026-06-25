"""Tests for Pilot B structural adapter surfaces."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.config import Settings
from app.external_adapters import AdapterPreflightResult, ExternalToolCapability
from app.structural_adapter import (
    ADAPTER_ID,
    preflight_structural_adapter,
    prepare_structural_run_preview,
    structural_capabilities,
)


def _hermetic_settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=tmp_path / "no-aieng",
        sample_step=workspace / "sample.step",
    )


def _block_binaries(monkeypatch) -> None:
    import shutil

    real_which = shutil.which

    def fake_which(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"FreeCADCmd", "FreeCADCmd.exe", "gmsh", "gmsh.exe", "ccx", "ccx_linux", "ccx2.21", "ccx_static", "ccx.exe"}:
            return None
        return real_which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", fake_which)


def _package_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_structural_package(
    pkg_path: Path,
    *,
    mesh: bool = True,
    solver_settings: bool = True,
    load_case: bool = True,
    input_deck: bool = False,
    load_case_id: str = "load_case_001",
    run_id: str = "run_001",
) -> None:
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "structural-test", "resources": {}}))
        if mesh:
            zf.writestr("simulation/mesh/mesh.inp", "*NODE\n1,0,0,0\n*ELEMENT, TYPE=C3D4, ELSET=EALL\n")
            zf.writestr("simulation/mesh/mesh_metadata.json", json.dumps({"elements": 10, "nodes": 20}))
        if solver_settings:
            zf.writestr("simulation/solver_settings.json", json.dumps({"solver": "CalculiX"}))
        if load_case:
            zf.writestr(
                f"simulation/load_cases/{load_case_id}.json",
                json.dumps({"id": load_case_id, "loads": []}),
            )
        if input_deck:
            zf.writestr(
                f"simulation/runs/{run_id}/solver_input.inp",
                "*HEADING\nstructural adapter preview\n*STEP\n*STATIC\n*END STEP\n",
            )


def _create_project_with_package(settings: Settings, project_name: str, package_name: str) -> tuple[str, Path]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(project_name))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / package_name
    project["aieng_file"] = package_name
    save_project(settings, project)
    return project_id, pkg_path


def test_manifest_contains_expected_structural_capabilities() -> None:
    caps = structural_capabilities()
    ids = {cap.id for cap in caps}
    assert {
        "structural.prepare_solver_run",
        "structural.generate_mesh",
        "structural.run_solver",
        "structural.extract_results",
    } <= ids


def test_manifest_capabilities_are_validated_models() -> None:
    for cap in structural_capabilities():
        assert isinstance(cap, ExternalToolCapability)
        assert cap.claim_advancement == "none"


def test_mesh_and_solver_capabilities_require_approval() -> None:
    caps = {cap.id: cap for cap in structural_capabilities()}
    assert caps["structural.generate_mesh"].requires_approval is True
    assert caps["structural.run_solver"].requires_approval is True
    assert caps["structural.extract_results"].requires_approval is True
    assert caps["structural.prepare_solver_run"].requires_approval is True


def test_solver_and_mesh_capabilities_declare_stale_artifacts() -> None:
    caps = {cap.id: cap for cap in structural_capabilities()}
    assert caps["structural.generate_mesh"].stale_artifacts_on_success
    assert "results/" in " ".join(caps["structural.run_solver"].stale_artifacts_on_success)


def test_preflight_partial_when_solver_only_present(tmp_path: Path, monkeypatch) -> None:
    _block_binaries(monkeypatch)
    settings = _hermetic_settings(tmp_path)
    settings.aieng_root.mkdir(parents=True)

    import shutil

    def fake_which(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"ccx", "ccx_linux", "ccx2.21", "ccx_static", "ccx.exe"}:
            solver = tmp_path / "bin" / "ccx"
            solver.parent.mkdir(parents=True, exist_ok=True)
            solver.write_text("", encoding="utf-8")
            return str(solver)
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    result = preflight_structural_adapter(settings)
    preflight = result["preflight"]
    assert preflight["status"] == "partial"
    assert "ccx" not in set(preflight["missing_dependencies"])


def test_api_endpoint_returns_structured_preflight(tmp_path: Path, monkeypatch) -> None:
    _block_binaries(monkeypatch)
    settings = _hermetic_settings(tmp_path)
    client = TestClient(create_app(settings))
    resp = client.get("/api/adapters/structural/preflight")
    assert resp.status_code == 200
    body = resp.json()
    assert body["adapter_id"] == "structural"
    assert "capabilities" in body and body["capabilities"]
    assert body["claim_boundary"]


def test_prepare_preview_reports_missing_items_without_mutating_package(tmp_path: Path, monkeypatch) -> None:
    _block_binaries(monkeypatch)
    settings = _hermetic_settings(tmp_path)
    project_id, pkg_path = _create_project_with_package(settings, "structural-preview-missing", "preview.aieng")
    _write_structural_package(pkg_path, mesh=False, solver_settings=False, load_case=False, input_deck=False)
    before = _package_digest(pkg_path)

    result = prepare_structural_run_preview(settings, project_id, {})

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["ready_to_run"] is False
    assert result["solver_execution_performed"] is False
    assert result["claim_advancement"] == "none"
    assert result["preflight"]["has_mesh"] is False
    assert result["preflight"]["has_solver_settings"] is False
    assert result["preflight"]["has_load_case"] is False
    assert result["preflight"]["has_input_deck"] is False
    assert len(result["preflight"]["missing_items"]) >= 4
    assert _package_digest(pkg_path) == before


def test_prepare_preview_ready_when_package_and_ccx_are_present(tmp_path: Path, monkeypatch) -> None:
    settings = _hermetic_settings(tmp_path)
    project_id, pkg_path = _create_project_with_package(settings, "structural-preview-ready", "ready.aieng")
    _write_structural_package(pkg_path, mesh=True, solver_settings=True, load_case=True, input_deck=True)

    import shutil

    def fake_which(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"ccx", "ccx_linux", "ccx2.21", "ccx_static", "ccx.exe"}:
            solver = tmp_path / "bin" / "ccx"
            solver.parent.mkdir(parents=True, exist_ok=True)
            solver.write_text("", encoding="utf-8")
            return str(solver)
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    result = prepare_structural_run_preview(settings, project_id, {})
    assert result["ok"] is True
    assert result["ready_to_run"] is True
    assert result["preflight"]["ccx_available"] is True
    assert result["input_deck_artifact"] == "simulation/runs/run_001/solver_input.inp"
    assert any(a["path"].endswith("result.frd") for a in result["planned_artifacts"])


def test_prepare_preview_endpoint_returns_structured_response(tmp_path: Path, monkeypatch) -> None:
    _block_binaries(monkeypatch)
    settings = _hermetic_settings(tmp_path)
    project_id, pkg_path = _create_project_with_package(settings, "structural-preview-api", "api.aieng")
    _write_structural_package(pkg_path, input_deck=True)
    client = TestClient(create_app(settings))

    before = _package_digest(pkg_path)
    resp = client.post(f"/api/projects/{project_id}/structural/prepare-preview", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "structural.prepare_solver_run"
    assert body["solver_execution_performed"] is False
    assert body["requires_approval"] is True
    assert body["claim_boundary"]
    assert "planned_artifacts" in body and body["planned_artifacts"]
    assert _package_digest(pkg_path) == before


# ── v0.30: close-the-loop integration tests ───────────────────────────────────

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def _real_aieng_settings(tmp_path: Path) -> Settings:
    """Settings pointed at the real aieng core so FRD extraction runs end-to-end."""
    workspace = tmp_path / "workspace"
    return Settings(
        platform_root=tmp_path / "platform",
        workspace_root=workspace,
        data_root=tmp_path / "data",
        aieng_root=_WORKSPACE_ROOT / "aieng",
        sample_step=workspace / "sample.step",
    )


def _frd_value(v: float) -> str:
    return f"{v:12.5E}"


def _frd_node_line(node_id: int, values: list) -> str:
    return "    -1" + f"{node_id:12d}" + "".join(_frd_value(v) for v in values)


def _make_test_frd(disp_nodes: dict | None, stress_nodes: dict | None) -> str:
    """Build a minimal valid CalculiX FRD text consumable by aieng.simulation.frd_result_extractor."""
    lines = ["    1C                                                                         1"]
    if disp_nodes is not None:
        lines += [
            "    -4  DISP        4    1",
            "    -5  D1          1    2    1    0",
            "    -5  D2          1    2    2    0",
            "    -5  D3          1    2    3    0",
            "    -5  ALL         1    2    0    1",
        ]
        for nid, vals in disp_nodes.items():
            lines.append(_frd_node_line(nid, vals))
        lines.append("    -3")
    if stress_nodes is not None:
        lines += [
            "    -4  S           6    1",
            "    -5  SXX         1    4    1    1",
            "    -5  SYY         1    4    2    1",
            "    -5  SZZ         1    4    3    1",
            "    -5  SXY         1    4    4    1",
            "    -5  SXZ         1    4    5    1",
            "    -5  SYZ         1    4    6    1",
        ]
        for nid, vals in stress_nodes.items():
            lines.append(_frd_node_line(nid, vals))
        lines.append("    -3")
    lines.append(" 9999")
    return "\n".join(lines) + "\n"


def _write_close_loop_package(
    pkg_path: Path,
    *,
    targets: list[dict[str, Any]] | None = None,
    run_id: str = "run_001",
    load_case_id: str = "load_case_001",
) -> None:
    """Package ready for a solver run plus design targets so target comparison can resolve."""
    import yaml

    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "close-loop-test", "resources": {}}))
        zf.writestr("simulation/mesh/mesh.inp", "*NODE\n1,0,0,0\n*ELEMENT, TYPE=C3D4, ELSET=EALL\n")
        zf.writestr("simulation/mesh/mesh_metadata.json", json.dumps({"elements": 10, "nodes": 20}))
        zf.writestr("simulation/solver_settings.json", json.dumps({"solver": "CalculiX"}))
        zf.writestr(
            f"simulation/load_cases/{load_case_id}.json",
            json.dumps({"id": load_case_id, "loads": []}),
        )
        zf.writestr(
            f"simulation/runs/{run_id}/solver_input.inp",
            "*HEADING\nclose-loop fixture\n*STEP\n*STATIC\n*END STEP\n",
        )
        if targets is not None:
            zf.writestr(
                "task/design_targets.yaml",
                yaml.safe_dump({"schema_version": "0.1", "targets": targets}, sort_keys=False),
            )


def _execute_solver_run_via_runtime(
    client: TestClient, project_id: str, tool_input: dict[str, Any]
) -> dict[str, Any]:
    """Start a solver run via the runtime endpoint, auto-approve, return final run record."""
    resp = client.post(
        "/api/runtime/runs",
        json={"message": "execute solver run", "project_id": project_id, "tool_input": tool_input},
    )
    assert resp.status_code == 200
    data = resp.json()
    if data["status"] == "awaiting_approval":
        approve = client.post(f"/api/runtime/runs/{data['run_id']}/approve")
        assert approve.status_code == 200
        data = approve.json()
    return data


def test_close_the_loop_solver_run_updates_computed_metrics_and_targets(tmp_path: Path) -> None:
    """End-to-end: cae.run_solver writes FRD-derived metrics into the package,
    and both the computed-metrics endpoint and the target-comparison endpoint
    reflect those metrics without any extra import step."""
    from unittest.mock import patch, MagicMock
    from app.main import default_project, project_dir, save_project

    if not (_WORKSPACE_ROOT / "aieng" / "src").exists():
        import pytest

        pytest.skip("aieng core repo not available; close-the-loop test requires it")

    settings = _real_aieng_settings(tmp_path)
    client = TestClient(create_app(settings))

    project = save_project(settings, default_project("structural-close-loop"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "close-loop.aieng"
    targets = [
        {
            "target_id": "stress_pass",
            "label": "Stress pass",
            "metric": "max_von_mises_stress",
            "operator": "<=",
            "value": 1000,
            "unit": "MPa",
        },
        {
            "target_id": "stress_fail",
            "label": "Stress fail",
            "metric": "max_von_mises_stress",
            "operator": "<=",
            "value": 1,
            "unit": "MPa",
        },
    ]
    _write_close_loop_package(pkg_path, targets=targets)
    project["aieng_file"] = "close-loop.aieng"
    save_project(settings, project)

    # Before any run, no computed metrics, both targets unknown.
    pre_metrics = client.get(f"/api/projects/{project_id}/computed-metrics").json()
    assert pre_metrics["metrics_count"] == 0
    pre_comparison = client.get(f"/api/projects/{project_id}/target-comparison").json()
    pre_statuses = {item["target_id"]: item["status"] for item in pre_comparison["items"]}
    assert pre_statuses == {"stress_pass": "unknown", "stress_fail": "unknown"}

    def fake_run(cmd, **kwargs):
        cwd = Path(kwargs.get("cwd", "."))
        # CalculiX would write <stem>.frd; stem matches input_deck filename.
        (cwd / "solver_input.frd").write_text(
            _make_test_frd(
                {1: [1.0, 0.0, 0.0, 1.0], 2: [5.0, 0.0, 0.0, 5.0]},
                {1: [200.0, 100.0, 50.0, 10.0, 0.0, 0.0]},
            ),
            encoding="utf-8",
        )
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("app.main.shutil.which", return_value="/fake/ccx"), patch(
        "subprocess.run", side_effect=fake_run
    ):
        run = _execute_solver_run_via_runtime(
            client,
            project_id,
            {
                "project_id": project_id,
                "input_deck_path": "simulation/runs/run_001/solver_input.inp",
                "extract_results": True,
                "refresh_summary": False,
            },
        )

    tool_output = run["tool_results"][0]["output"]
    assert tool_output["ok"] is True
    assert tool_output["solver_execution_performed"] is True
    assert tool_output["return_code"] == 0
    # Extraction surfaced on the runtime result so the UI can display it.
    assert "extracted_metrics" in tool_output
    extracted = tool_output["extracted_metrics"]
    assert isinstance(extracted, dict)
    assert extracted.get("load_cases"), "extraction must surface load case metrics"

    # Package now physically contains computed_metrics.json.
    with zipfile.ZipFile(pkg_path, "r") as zf:
        assert "results/computed_metrics.json" in zf.namelist()
        written = json.loads(zf.read("results/computed_metrics.json").decode("utf-8"))
    assert written["load_cases"], "package computed_metrics must contain load_cases"

    # GET /computed-metrics reflects the solver-generated metrics — no import step needed.
    post_metrics = client.get(f"/api/projects/{project_id}/computed-metrics").json()
    assert post_metrics["metrics_count"] > 0
    metric_names: set[str] = set()
    for lc in post_metrics["document"].get("load_cases") or []:
        metric_names.update((lc.get("metrics") or {}).keys())
    assert "max_von_mises_stress" in metric_names, (
        f"expected max_von_mises_stress in extracted load-case metrics, got {sorted(metric_names)}"
    )

    # Target comparison now resolves; the stress targets evaluate against the extracted metric.
    post_comparison = client.get(f"/api/projects/{project_id}/target-comparison").json()
    post_statuses = {item["target_id"]: item["status"] for item in post_comparison["items"]}
    assert post_statuses["stress_pass"] in {"pass", "fail"}
    assert post_statuses["stress_fail"] in {"pass", "fail"}
    # At least one of the two should differ from before — the loop closed.
    assert post_statuses != pre_statuses


def test_close_the_loop_extraction_failure_is_honest_and_does_not_fabricate_metrics(tmp_path: Path) -> None:
    """If FRD extraction raises, cae.run_solver surfaces a warning, does not
    set extracted_metrics, and the package's computed_metrics.json stays absent —
    no metric is ever fabricated to make the run look successful."""
    from unittest.mock import patch, MagicMock
    from app.main import default_project, project_dir, save_project

    settings = _real_aieng_settings(tmp_path)
    client = TestClient(create_app(settings))

    project = save_project(settings, default_project("structural-extract-fail"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "fail.aieng"
    _write_close_loop_package(pkg_path)
    project["aieng_file"] = "fail.aieng"
    save_project(settings, project)

    def fake_run(cmd, **kwargs):
        cwd = Path(kwargs.get("cwd", "."))
        # Produce an FRD so the run_solver path attempts extraction.
        (cwd / "solver_input.frd").write_text("not a valid frd file", encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    def failing_extract(*args, **kwargs):
        raise RuntimeError("simulated FRD parse failure")

    with patch("app.main.shutil.which", return_value="/fake/ccx"), patch(
        "subprocess.run", side_effect=fake_run
    ), patch("app.aieng_bridge.extract_frd_solver_results", side_effect=failing_extract):
        run = _execute_solver_run_via_runtime(
            client,
            project_id,
            {
                "project_id": project_id,
                "input_deck_path": "simulation/runs/run_001/solver_input.inp",
                "extract_results": True,
                "refresh_summary": False,
            },
        )

    tool_output = run["tool_results"][0]["output"]
    assert tool_output["ok"] is True  # the solver itself ran; extraction is a separate concern
    assert tool_output["solver_execution_performed"] is True
    assert "extracted_metrics" not in tool_output, "no extracted_metrics may be surfaced on failure"
    assert any(
        "FRD extraction" in w or "extraction failed" in w.lower() for w in tool_output["warnings"]
    ), f"expected an honest extraction-failure warning, got {tool_output['warnings']}"

    # Package must NOT contain a fabricated computed_metrics.json.
    with zipfile.ZipFile(pkg_path, "r") as zf:
        assert "results/computed_metrics.json" not in zf.namelist()
    # Endpoint also reports no metrics.
    post_metrics = client.get(f"/api/projects/{project_id}/computed-metrics").json()
    assert post_metrics["metrics_count"] == 0


def test_close_the_loop_no_frd_produced_is_honest(tmp_path: Path) -> None:
    """If the solver runs but does not produce an FRD file, cae.run_solver does
    not call extraction and does not write computed_metrics.json. The closed
    loop simply remains open — never fabricated."""
    from unittest.mock import patch, MagicMock
    from app.main import default_project, project_dir, save_project

    settings = _real_aieng_settings(tmp_path)
    client = TestClient(create_app(settings))

    project = save_project(settings, default_project("structural-no-frd"))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / "nofrd.aieng"
    _write_close_loop_package(pkg_path)
    project["aieng_file"] = "nofrd.aieng"
    save_project(settings, project)

    def fake_run(cmd, **kwargs):
        # Solver exits non-zero and writes no FRD.
        return MagicMock(returncode=1, stdout="", stderr="solver error")

    extract_calls: list[Any] = []

    def spy_extract(*args, **kwargs):  # pragma: no cover - asserted not called
        extract_calls.append((args, kwargs))
        return {"status": "ok", "metrics": {}, "artifacts": []}

    with patch("app.main.shutil.which", return_value="/fake/ccx"), patch(
        "subprocess.run", side_effect=fake_run
    ), patch("app.aieng_bridge.extract_frd_solver_results", side_effect=spy_extract):
        run = _execute_solver_run_via_runtime(
            client,
            project_id,
            {
                "project_id": project_id,
                "input_deck_path": "simulation/runs/run_001/solver_input.inp",
                "extract_results": True,
                "refresh_summary": False,
            },
        )

    tool_output = run["tool_results"][0]["output"]
    assert tool_output["solver_execution_performed"] is True
    assert tool_output["status"] == "failed"
    assert "extracted_metrics" not in tool_output
    assert extract_calls == [], "extraction must not be attempted when no FRD was produced"

    with zipfile.ZipFile(pkg_path, "r") as zf:
        assert "results/computed_metrics.json" not in zf.namelist()
    post_metrics = client.get(f"/api/projects/{project_id}/computed-metrics").json()
    assert post_metrics["metrics_count"] == 0
