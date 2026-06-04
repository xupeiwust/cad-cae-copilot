from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import agent_context as agent_context_module
from app.app_factory import create_app
from app.config import Settings, now_iso

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


def _make_project(settings: Settings, name: str, package: str) -> tuple[str, Path]:
    from app.main import default_project, project_dir, save_project

    project = save_project(settings, default_project(name))
    project_id = project["id"]
    pkg_path = project_dir(settings, project_id) / package
    project["aieng_file"] = package
    save_project(settings, project)
    return project_id, pkg_path


def _write_package(pkg: Path) -> None:
    pkg.parent.mkdir(parents=True, exist_ok=True)
    feature_graph = {
        "features": [
            {
                "id": "body",
                "parameters": [
                    {
                        "name": "thickness_mm",
                        "cad_parameter_name": "WALL_THICKNESS",
                        "value": 5.0,
                    }
                ],
            }
        ]
    }
    topology = {"faces": [{"id": "face_1"}], "edges": [], "vertices": []}
    fixture: dict[str, Any] = {
        "template_id": "cantilever_beam",
        "parameters": {"length_mm": 200.0, "material": "aluminum_6061_t6"},
        "geometry": {
            "geometry_kind": "cantilever_beam",
            "primitive": "rectangular_prism",
            "dimensions": {"length_mm": 200.0, "width_mm": 20.0, "height_mm": 10.0},
            "named_regions": [
                {"id": "fixed_root", "role": "fixed_support"},
                {"id": "tip_face", "role": "tip_load"},
            ],
            "material": {"id": "aluminum_6061_t6", "name": "Aluminum 6061-T6"},
        },
    }
    simulation_setup = {
        "analysis_type": "linear_static",
        "material": {"name": "Aluminum 6061-T6"},
        "loads": [{"id": "tip_load"}],
        "boundary_conditions": [{"id": "fixed_root", "type": "fixed"}],
    }

    with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"model_id": "cache-test"}))
        zf.writestr("geometry/template_cad_fixture.json", json.dumps(fixture))
        zf.writestr("graph/feature_graph.json", json.dumps(feature_graph))
        zf.writestr("geometry/topology_map.json", json.dumps(topology))
        zf.writestr("simulation/setup.json", json.dumps(simulation_setup))
        zf.writestr("task/design_targets.yaml", "targets: []\n")
        zf.writestr("results/computed_metrics.json", json.dumps({"global_metrics": {}, "load_cases": []}))


def _patch_nonessential_context_readers(monkeypatch) -> None:
    monkeypatch.setattr("app.package_inspection._detect_cae_artifacts", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.package_inspection._generate_cae_preprocessing_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.package_inspection._generate_cae_result_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.package_inspection._generate_cae_simulation_run_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.agent_context._detect_cae_artifacts", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.agent_context._generate_cae_preprocessing_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.agent_context._generate_cae_result_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.agent_context._generate_cae_simulation_run_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.design_targets.get_design_targets", lambda *args, **kwargs: {"ok": True, "targets": [], "document": None, "warnings": []})
    monkeypatch.setattr("app.computed_metrics.get_computed_metrics", lambda *args, **kwargs: {"ok": True, "document": None, "metrics_count": 0, "load_case_count": 0})
    monkeypatch.setattr("app.target_comparison.compare_package_targets", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.copilot_loop.list_loops", lambda *args, **kwargs: {"loops": []})
    monkeypatch.setattr("app.brep_graph.load_or_build_digest", lambda *args, **kwargs: None)


def test_build_agent_context_uses_single_zip_open_for_direct_reads(monkeypatch, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    project_id, pkg = _make_project(settings, "cache-context", "p.aieng")
    _write_package(pkg)
    _patch_nonessential_context_readers(monkeypatch)

    real_zipfile = zipfile.ZipFile
    open_count = 0

    def _counting_zipfile(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal open_count
        open_count += 1
        return real_zipfile(*args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", _counting_zipfile)

    context = agent_context_module.build_agent_context(settings, project_id)

    assert context["package"]["exists"] is True
    assert context["cad"]["geometry_evidence_level"] == "metadata"
    assert open_count == 1


# NOTE: the autopilot-run path that previously also exercised the shared package
# reader was removed with the engine retirement (#17 B-backend). The core #4
# guarantee — build_agent_context opens the package zip once — is covered by
# test_build_agent_context_uses_single_zip_open_for_direct_reads above.
