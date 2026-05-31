"""Project Health Check v0.9 — recommended actions and read-only safety.

These tests verify that the health-check endpoint generates deterministic,
safe, read-only recommended actions from project state.
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


def _make_minimal_package(
    pkg_path: Path,
    *,
    manifest: bool = True,
    design_targets: bool = True,
    computed_metrics: bool = True,
    feature_graph: bool = True,
    parsed_features: bool = True,
    evidence_index: bool = True,
    stale: bool = False,
    solver_input: bool = True,
) -> None:
    """Create a minimal .aieng package with configurable contents."""
    pkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if manifest:
            zf.writestr("manifest.json", json.dumps({"model_id": "test", "resources": {}}))
        if design_targets:
            zf.writestr(
                "task/design_targets.yaml",
                yaml.safe_dump(
                    {"schema_version": "0.1", "targets": [{"target_id": "t1", "threshold": 1.0}]},
                    sort_keys=False,
                ),
            )
        if computed_metrics:
            zf.writestr(
                "results/computed_metrics.json",
                json.dumps({"schema_version": "0.1", "metrics": {}}),
            )
        if feature_graph:
            zf.writestr(
                "graph/feature_graph.json",
                json.dumps(
                    {
                        "features": [
                            {
                                "id": "f1",
                                "parameters": [
                                    {
                                        "name": "thickness_mm",
                                        "editability": {"executable": True},
                                    }
                                ],
                            }
                        ]
                    }
                ),
            )
        if parsed_features:
            zf.writestr(
                "simulation/cae_imports/parsed_features.json",
                json.dumps({"features": [{"id": "f1", "thickness_mm": 10.0}]}),
            )
        if evidence_index:
            zf.writestr("results/evidence_index.json", json.dumps({"evidence_items": []}))
        if stale:
            zf.writestr(
                "revalidation_status.json",
                json.dumps({"stress_by_feature": {"stale": True}}),
            )
        if solver_input:
            zf.writestr("simulation/runs/run_001/solver_input.inp", "*Solver input\n")


def _call_health_check(client: TestClient, project_id: str) -> dict[str, Any]:
    resp = client.get(f"/api/projects/{project_id}/health-check")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _action_ids(actions: list[dict[str, Any]]) -> list[str]:
    return [a["id"] for a in actions]


def _find_action(actions: list[dict[str, Any]], action_id: str) -> dict[str, Any] | None:
    for a in actions:
        if a["id"] == action_id:
            return a
    return None


def _assert_safety_false(action: dict[str, Any]) -> None:
    assert action["safety"]["mutates_package"] is False
    assert action["safety"]["runs_solver"] is False
    assert action["safety"]["advances_claim"] is False


def _assert_navigation_target(action: dict[str, Any], section: str) -> None:
    assert action["action_type"] == "navigate"
    assert action["target"] is not None
    assert action["target"]["tab"] == "copilot_loop"
    assert action["target"]["section"] == section
    assert action["target"]["intent"] == "navigation"
    _assert_safety_false(action)


# ---------------------------------------------------------------------------
# Action generation tests
# ---------------------------------------------------------------------------


class TestProjectHealthActions:
    """Verify recommended action generation from health check state."""

    def test_missing_package_generates_upload_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-pkg"))
        project_id = project["id"]

        body = _call_health_check(client, project_id)
        assert body["readiness"] == "not_ready"
        actions = body["recommended_actions"]
        action = _find_action(actions, "upload_package")
        assert action is not None
        assert action["priority"] == "high"
        assert action["action_type"] == "manual"
        _assert_safety_false(action)
        assert action["source_check_ids"]
        assert any(sid in action["source_check_ids"] for sid in ("package_file", "package_path"))

    def test_unreadable_package_generates_fix_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("bad-pkg"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        pkg_path.parent.mkdir(parents=True, exist_ok=True)
        pkg_path.write_text("not a zip")
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        assert body["readiness"] == "not_ready"
        actions = body["recommended_actions"]
        action = _find_action(actions, "fix_package")
        assert action is not None
        assert action["priority"] == "high"
        _assert_safety_false(action)

    def test_missing_manifest_generates_fix_manifest_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-manifest"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        with zipfile.ZipFile(pkg_path, "w") as zf:
            zf.writestr("other.txt", "hello")
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        assert body["readiness"] == "not_ready"
        actions = body["recommended_actions"]
        action = _find_action(actions, "fix_manifest")
        assert action is not None
        assert action["priority"] == "high"
        _assert_safety_false(action)

    def test_missing_design_targets_generates_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-targets"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, design_targets=False)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "add_design_targets")
        assert action is not None
        assert action["priority"] == "high"
        _assert_navigation_target(action, "design_targets")
        assert "design_targets" in action["source_check_ids"]

    def test_missing_computed_metrics_generates_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-metrics"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, computed_metrics=False)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "import_computed_metrics")
        assert action is not None
        assert action["priority"] == "medium"
        _assert_navigation_target(action, "computed_metrics")
        assert "computed_metrics" in action["source_check_ids"]

    def test_stale_evidence_generates_high_priority_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("stale"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, stale=True)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "review_stale")
        assert action is not None
        assert action["priority"] == "high"
        _assert_navigation_target(action, "stale_evidence")
        assert "stale_evidence" in action["source_check_ids"]

    def test_no_editable_parameters_generates_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-params"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, feature_graph=False, parsed_features=False)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "add_editable_params")
        assert action is not None
        assert action["priority"] == "medium"
        _assert_safety_false(action)
        # navigates to the geometry inspection card for read-only feature inspection
        _assert_navigation_target(action, "geometry_inspection")

    def test_missing_cad_context_generates_inspect_cad_features_action(self, tmp_path: Path) -> None:
        """When no CAD feature graph / parsed features are present,
        the health check should suggest running read-only geometry feature
        inspection and route the user to the geometry inspection card.
        """
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-cad-context"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, feature_graph=False, parsed_features=False)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "inspect_cad_features")
        assert action is not None
        assert action["priority"] == "medium"
        _assert_safety_false(action)
        _assert_navigation_target(action, "geometry_inspection")
        # The action is purely navigation guidance; nothing is auto-run.
        assert "read-only" in action["summary"].lower()

    def test_no_loops_generates_start_loop_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-loops"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "start_loop")
        assert action is not None
        assert action["priority"] == "medium"
        _assert_navigation_target(action, "copilot_stepper")

    def test_one_loop_generates_run_another_loop_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("one-loop"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        # Create exactly one loop
        loops_dir = project_dir(settings, project_id) / "copilot_loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        loop = {
            "loop_id": "loop_001",
            "status": "completed",
            "steps": [],
            "context": {},
        }
        (loops_dir / "loop_001.json").write_text(json.dumps(loop))

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "run_another_loop")
        assert action is not None
        assert action["priority"] == "low"
        _assert_navigation_target(action, "copilot_stepper")

    def test_missing_loop_reports_generates_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-reports"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        # Create a loop without a report
        loops_dir = project_dir(settings, project_id) / "copilot_loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        loop = {
            "loop_id": "loop_001",
            "status": "completed",
            "steps": [],
            "context": {},
        }
        (loops_dir / "loop_001.json").write_text(json.dumps(loop))

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "generate_reports")
        assert action is not None
        assert action["priority"] == "medium"
        _assert_navigation_target(action, "loop_history")

    def test_action_targets_are_navigation_hints_only(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("navigation-only"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, design_targets=False, stale=True)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        targeted_actions = [a for a in body["recommended_actions"] if a.get("target")]
        assert targeted_actions
        for action in targeted_actions:
            _assert_safety_false(action)
            assert action["action_type"] == "navigate"
            assert action["target"]["intent"] == "navigation"
            assert "section" in action["target"]
            assert "execute" not in action["target"]
            assert "mutation" not in action["target"]
            assert "solver" not in action["target"]

    def test_missing_claim_boundary_generates_high_priority_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-boundary"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        # Create a loop with a report that lacks claim boundary
        loops_dir = project_dir(settings, project_id) / "copilot_loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        loop = {
            "loop_id": "loop_001",
            "status": "completed",
            "steps": [],
            "context": {"report": {"artifact_path": "reports/copilot_loop/loop_001.md"}},
        }
        (loops_dir / "loop_001.json").write_text(json.dumps(loop))
        (loops_dir / "loop_001.md").write_text("# Loop Report\n\nNo claim boundary here.\n", encoding="utf-8")

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "regenerate_claim_boundary")
        assert action is not None
        assert action["priority"] == "high"
        _assert_safety_false(action)

    def test_demo_project_generates_educational_action(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("demo-proj"))
        project["demo"] = True
        project["demo_notice"] = "Fixture data for testing."
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "demo_notice")
        assert action is not None
        assert action["priority"] == "low"
        _assert_safety_false(action)
        assert "demo_metadata" in action["source_check_ids"]

    def test_actions_sorted_by_priority(self, tmp_path: Path) -> None:
        """High-priority actions should appear before medium and low."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("sort-test"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        # Package with stale evidence (high), no computed metrics (medium), one loop (low)
        _make_minimal_package(pkg_path, stale=True, computed_metrics=False)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        # Create one loop
        loops_dir = project_dir(settings, project_id) / "copilot_loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        loop = {
            "loop_id": "loop_001",
            "status": "completed",
            "steps": [],
            "context": {},
        }
        (loops_dir / "loop_001.json").write_text(json.dumps(loop))

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        priorities = [a["priority"] for a in actions]
        # All high should come before medium, which should come before low
        priority_values = {"high": 0, "medium": 1, "low": 2}
        numeric = [priority_values[p] for p in priorities]
        assert numeric == sorted(numeric), f"Actions not sorted by priority: {priorities}"

    def test_actions_are_unique(self, tmp_path: Path) -> None:
        """No duplicate action IDs should be returned."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("uniq"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        ids = [a["id"] for a in actions]
        assert len(ids) == len(set(ids)), f"Duplicate action IDs: {ids}"

    def test_every_action_has_safety_flags_false(self, tmp_path: Path) -> None:
        """All returned actions must declare mutates_package=False, runs_solver=False,
        advances_claim=False."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("safety"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        # Create a package with multiple warnings to generate many actions
        _make_minimal_package(pkg_path, design_targets=False, computed_metrics=False, stale=True)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        assert actions, "Expected actions to test safety flags"
        for action in actions:
            _assert_safety_false(action)

    def test_read_only_digest_unchanged(self, tmp_path: Path) -> None:
        """The health check must not mutate the .aieng package."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("readonly"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        before = hashlib.sha256(pkg_path.read_bytes()).hexdigest()
        body = _call_health_check(client, project_id)
        after = hashlib.sha256(pkg_path.read_bytes()).hexdigest()

        assert before == after, "Package was mutated during health check"
        assert not any(
            "digest changed" in w for w in body["warnings"]
        ), "Mutation guard fired unexpectedly"

    def test_ready_project_has_no_actions(self, tmp_path: Path) -> None:
        """A fully ready project should have empty recommended_actions."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("ready"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        # Create two loops with reports that have claim boundary
        loops_dir = project_dir(settings, project_id) / "copilot_loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        for i in range(2):
            loop_id = f"loop_{i:03d}"
            loop = {
                "loop_id": loop_id,
                "status": "completed",
                "steps": [],
                "context": {"report": {"artifact_path": f"reports/copilot_loop/{loop_id}.md"}},
            }
            (loops_dir / f"{loop_id}.json").write_text(json.dumps(loop))
            report_text = (
                "# Report\n\n"
                "This decision review export is a reviewable record. "
                "It does not certify either design, does not advance engineering claims.\n\n"
                "This decision review export does not certify design safety, does not auto-advance engineering claims, and must be reviewed by a qualified engineer.\n"
            )
            (loops_dir / f"{loop_id}.md").write_text(report_text, encoding="utf-8")

        body = _call_health_check(client, project_id)
        assert body["readiness"] == "ready"
        assert body["recommended_actions"] == []
        assert body["overall_next_action"] == "This project appears ready for the current Copilot Loop review workflow."

    def test_overall_next_action_from_highest_priority(self, tmp_path: Path) -> None:
        """When readiness is partial, overall_next_action should reflect the highest-priority action."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("partial"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, design_targets=False)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        assert body["readiness"] == "partial"
        actions = body["recommended_actions"]
        assert actions
        assert body["overall_next_action"] == actions[0]["label"]

    def test_prohibited_language_generates_action(self, tmp_path: Path) -> None:
        """If a loop report contains prohibited certification language, a high-priority
        action is generated."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("bad-lang"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        loops_dir = project_dir(settings, project_id) / "copilot_loops"
        loops_dir.mkdir(parents=True, exist_ok=True)
        loop = {
            "loop_id": "loop_001",
            "status": "completed",
            "steps": [],
            "context": {"report": {"artifact_path": "reports/copilot_loop/loop_001.md"}},
        }
        (loops_dir / "loop_001.json").write_text(json.dumps(loop))
        (loops_dir / "loop_001.md").write_text(
            "# Report\n\nThe design is certified and engineering claim approved.\n", encoding="utf-8"
        )

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        action = _find_action(actions, "remove_certification_language")
        assert action is not None
        assert action["priority"] == "high"
        _assert_safety_false(action)

    def test_no_cae_artifacts_without_computed_metrics_does_not_duplicate(self, tmp_path: Path) -> None:
        """When both cae_artifacts and computed_metrics are missing, only the computed_metrics
        action should be generated (not a duplicate cae_artifacts action)."""
        settings = _make_settings(tmp_path)
        client = TestClient(create_app(settings))
        project = save_project(settings, default_project("no-cae"))
        project_id = project["id"]
        pkg_path = project_dir(settings, project_id) / "test.aieng"
        _make_minimal_package(pkg_path, computed_metrics=False, solver_input=False)
        project["aieng_file"] = "test.aieng"
        save_project(settings, project)

        body = _call_health_check(client, project_id)
        actions = body["recommended_actions"]
        ids = _action_ids(actions)
        assert "import_computed_metrics" in ids
        # The cae_artifacts action should be suppressed because computed_metrics already covers it
        assert "import_cae_artifacts" not in ids
