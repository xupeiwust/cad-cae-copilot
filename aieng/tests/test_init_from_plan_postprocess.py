from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from aieng.orchestration.init_from_plan import init_from_plan
from aieng.modeling_plan.planner import RuleBasedModelingPlanner


def _make_valid_plan() -> dict:
    planner = RuleBasedModelingPlanner()
    return planner.plan("create a 120x80x10 plate with 4 holes")


def _write_plan(path: Path, plan: dict) -> None:
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")


def _read_json_from_package(package_path: Path, member: str) -> dict:
    with zipfile.ZipFile(package_path, "r") as zf:
        return json.loads(zf.read(member))


def _read_text_from_package(package_path: Path, member: str) -> str:
    with zipfile.ZipFile(package_path, "r") as zf:
        return zf.read(member).decode("utf-8")


def _read_status(package_path: Path) -> dict[str, Any]:
    text = _read_text_from_package(package_path, "validation/status.yaml")
    return yaml.safe_load(text)


class TestManifestGeometryResources:
    def test_manifest_contains_geometry_resource_paths(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        manifest = _read_json_from_package(out_path, "manifest.json")
        resources = manifest["resources"]
        assert "geometry" in resources
        assert resources["geometry"]["source"] == "geometry/source.step"
        assert resources["geometry"]["normalized"] == "geometry/normalized.step"


class TestPostprocessSuccess:
    def test_postprocess_creates_topology_map(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        topo = _read_json_from_package(out_path, "geometry/topology_map.json")
        assert "entities" in topo
        assert any(e.get("type") == "solid" for e in topo["entities"])

    def test_postprocess_creates_aag(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        aag = _read_json_from_package(out_path, "graph/aag.json")
        assert "nodes" in aag
        assert "arcs" in aag

    def test_postprocess_creates_feature_graph(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        fg = _read_json_from_package(out_path, "graph/feature_graph.json")
        assert "features" in fg

    def test_postprocess_updates_manifest_graph_resources(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        manifest = _read_json_from_package(out_path, "manifest.json")
        graph = manifest["resources"]["graph"]
        assert graph.get("aag") == "graph/aag.json"
        assert graph.get("feature_graph") == "graph/feature_graph.json"

    def test_status_yaml_records_postprocess_summary(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path)

        status = _read_status(out_path)
        assert "semantic_postprocess" in status
        sp = status["semantic_postprocess"]
        assert sp["requested"] is True
        assert sp["topology_status"] == "success"
        assert sp["aag_status"] == "success"
        assert sp["feature_graph_status"] == "success"


class TestPostprocessSkipped:
    def test_run_postprocess_false_skips_semantic_files(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(plan_path, out_path, run_postprocess=False)

        with zipfile.ZipFile(out_path, "r") as zf:
            names = set(zf.namelist())
        assert "geometry/topology_map.json" not in names
        assert "graph/aag.json" not in names
        assert "graph/feature_graph.json" not in names

        status = _read_status(out_path)
        sp = status["semantic_postprocess"]
        assert sp["requested"] is False
        assert sp["topology_status"] == "skipped"

    def test_diagnostic_package_skips_postprocess(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        init_from_plan(
            plan_path,
            out_path,
            backend_options={"fail_at_step_id": plan["steps"][0]["step_id"]},
        )

        with zipfile.ZipFile(out_path, "r") as zf:
            names = set(zf.namelist())
        assert "geometry/topology_map.json" not in names
        assert "graph/aag.json" not in names
        assert "graph/feature_graph.json" not in names

        status = _read_status(out_path)
        sp = status["semantic_postprocess"]
        assert sp["requested"] is True
        assert sp["topology_status"] == "skipped"
        assert any("modeling did not succeed" in w for w in sp["warnings"])


class TestPostprocessFailures:
    def test_postprocess_strict_raises_on_topology_failure(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        with patch("aieng.orchestration.init_from_plan.extract_topology_package", side_effect=RuntimeError("mock topo fail")):
            with pytest.raises(RuntimeError, match="mock topo fail"):
                init_from_plan(plan_path, out_path, postprocess_strict=True)

    def test_postprocess_failure_non_strict_preserves_package(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        with patch("aieng.orchestration.init_from_plan.extract_topology_package", side_effect=RuntimeError("mock topo fail")):
            init_from_plan(plan_path, out_path, postprocess_strict=False)

        # Package must still exist and contain core members
        with zipfile.ZipFile(out_path, "r") as zf:
            names = set(zf.namelist())
        assert "manifest.json" in names
        assert "geometry/source.step" in names

        status = _read_status(out_path)
        sp = status["semantic_postprocess"]
        assert sp["topology_status"] == "failed"
        assert any("mock topo fail" in e for e in sp["errors"])
        assert sp["aag_status"] == "skipped"

    def test_postprocess_non_strict_aag_failure_skips_feature_graph(self, tmp_path: Path) -> None:
        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        with patch("aieng.orchestration.init_from_plan.build_aag_package", side_effect=RuntimeError("mock aag fail")):
            init_from_plan(plan_path, out_path, postprocess_strict=False)

        # Topology should have succeeded, AAG failed, feature graph skipped
        topo = _read_json_from_package(out_path, "geometry/topology_map.json")
        assert "entities" in topo

        with zipfile.ZipFile(out_path, "r") as zf:
            names = set(zf.namelist())
        assert "graph/aag.json" not in names
        assert "graph/feature_graph.json" not in names

        status = _read_status(out_path)
        sp = status["semantic_postprocess"]
        assert sp["topology_status"] == "success"
        assert sp["aag_status"] == "failed"
        assert sp["feature_graph_status"] == "skipped"


class TestPostprocessCLI:
    def test_cli_no_postprocess_flag(self, tmp_path: Path) -> None:
        from aieng.cli import main

        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        rc = main([
            "init-from-plan", str(plan_path),
            "--out", str(out_path),
            "--no-postprocess",
        ])
        assert rc == 0

        with zipfile.ZipFile(out_path, "r") as zf:
            names = set(zf.namelist())
        assert "geometry/topology_map.json" not in names

    def test_cli_postprocess_strict_flag(self, tmp_path: Path) -> None:
        from aieng.cli import main

        plan = _make_valid_plan()
        plan_path = tmp_path / "plan.json"
        _write_plan(plan_path, plan)
        out_path = tmp_path / "model.aieng"

        with patch("aieng.orchestration.init_from_plan.extract_topology_package", side_effect=RuntimeError("mock fail")):
            rc = main([
                "init-from-plan", str(plan_path),
                "--out", str(out_path),
                "--postprocess-strict",
            ])
        # Package is written before post-processing; failure returns 2 but leaves package.
        assert rc == 2
        assert out_path.exists()
