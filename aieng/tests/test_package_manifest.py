"""Tests for aieng.package_manifest."""

from __future__ import annotations

import pytest

from aieng.package_manifest import (
    ARTIFACT_MANIFEST_PATH,
    FRESHNESS_CATEGORIES,
    classify_artifact_path,
    generate_artifact_manifest,
)


class TestClassifyArtifactPath:
    def test_revalidation_status(self) -> None:
        kind, category, producer, role = classify_artifact_path("state/revalidation_status.json")
        assert kind == "state"
        assert category == "state"
        assert producer == "cad.edit_parameter"
        assert role is None

    def test_audit_events(self) -> None:
        kind, category, producer, role = classify_artifact_path("audit/events.jsonl")
        assert kind == "audit_log"
        assert category == "audit"
        assert producer is None
        assert role is None

    def test_result_summary(self) -> None:
        kind, category, producer, role = classify_artifact_path("results/result_summary.json")
        assert kind == "cae_result_summary"
        assert category == "summary"
        assert producer == "postprocess.refresh_cae_summary"
        assert role == "llm_readable_postprocessing_summary"

    def test_evidence_index(self) -> None:
        kind, category, producer, role = classify_artifact_path("results/evidence_index.json")
        assert kind == "evidence_index"
        assert category == "evidence_index"
        assert role == "cae_evidence_catalog"

    def test_displacement_field_summary(self) -> None:
        kind, category, producer, role = classify_artifact_path(
            "results/fields/displacement.summary.json"
        )
        assert kind == "field"
        assert category == "field_summary"
        assert producer == "postprocess.refresh_cae_summary"
        assert role == "displacement_extrema"

    def test_stress_field_summary(self) -> None:
        kind, category, _, role = classify_artifact_path("results/fields/stress.summary.json")
        assert kind == "field"
        assert category == "field_summary"
        assert role == "stress_extrema"

    def test_solver_run_json_pattern(self) -> None:
        kind, category, producer, role = classify_artifact_path(
            "simulation/runs/run_001/solver_run.json"
        )
        assert kind == "solver_run_metadata"
        assert category == "solver_output"
        assert producer == "cae.run_solver"
        assert role == "solver_execution_evidence"

    def test_frd_pattern(self) -> None:
        kind, category, producer, role = classify_artifact_path(
            "simulation/runs/run_001/outputs/result.frd"
        )
        assert kind == "solver_raw_output"
        assert category == "solver_output"
        assert producer == "cae.run_solver"
        assert role == "solver_raw_output"

    def test_claim_proposal(self) -> None:
        kind, category, producer, role = classify_artifact_path("claims/proposals/abc123.json")
        assert kind == "claim_proposal"
        assert category == "claim_proposal"
        assert producer == "claims.propose_update"

    def test_geometry_step(self) -> None:
        kind, category, _, _ = classify_artifact_path("geometry/source.step")
        assert kind == "geometry"
        assert category == "geometry"

    def test_geometry_stp(self) -> None:
        _, category, _, _ = classify_artifact_path("geometry/model.stp")
        assert category == "geometry"

    def test_geometry_iges(self) -> None:
        _, category, _, _ = classify_artifact_path("geometry/part.iges")
        assert category == "geometry"

    def test_mesh_inp_pattern(self) -> None:
        kind, category, producer, _ = classify_artifact_path("simulation/mesh/mesh_2.0mm.inp")
        assert kind == "mesh"
        assert category == "mesh"
        assert producer == "cae.generate_mesh"

    def test_mesh_metadata(self) -> None:
        kind, category, producer, _ = classify_artifact_path("simulation/mesh/mesh_metadata.json")
        assert kind == "mesh_metadata"
        assert category == "mesh"
        assert producer == "cae.generate_mesh"

    def test_computed_metrics(self) -> None:
        kind, category, producer, role = classify_artifact_path("results/computed_metrics.json")
        assert kind == "result"
        assert category == "solver_output"
        assert producer == "cae.run_solver"
        assert role == "computed_extrema"

    def test_unknown_path(self) -> None:
        kind, category, producer, role = classify_artifact_path("custom/deep/nested/file.bin")
        assert kind == "unknown"
        assert category == "unknown"
        assert producer is None
        assert role is None

    def test_unknown_returns_four_tuple(self) -> None:
        result = classify_artifact_path("not/a/known/path.xyz")
        assert len(result) == 4

    def test_package_manifest(self) -> None:
        kind, category, _, _ = classify_artifact_path("manifest.json")
        assert category == "package"

    def test_package_metadata(self) -> None:
        kind, category, _, _ = classify_artifact_path("metadata.json")
        assert category == "package"


class TestFreshnessCategories:
    def test_solver_output_in_freshness(self) -> None:
        assert "solver_output" in FRESHNESS_CATEGORIES

    def test_summary_in_freshness(self) -> None:
        assert "summary" in FRESHNESS_CATEGORIES

    def test_field_summary_in_freshness(self) -> None:
        assert "field_summary" in FRESHNESS_CATEGORIES

    def test_evidence_index_in_freshness(self) -> None:
        assert "evidence_index" in FRESHNESS_CATEGORIES

    def test_geometry_not_in_freshness(self) -> None:
        assert "geometry" not in FRESHNESS_CATEGORIES

    def test_state_not_in_freshness(self) -> None:
        assert "state" not in FRESHNESS_CATEGORIES


class TestGenerateArtifactManifest:
    def test_top_level_claim_advancement_none(self) -> None:
        manifest = generate_artifact_manifest(["manifest.json"])
        assert manifest["claim_advancement"] == "none"

    def test_every_entry_claim_advancement_none(self) -> None:
        paths = [
            "results/result_summary.json",
            "results/evidence_index.json",
            "results/fields/displacement.summary.json",
            "simulation/runs/run_001/outputs/result.frd",
            "claims/proposals/p001.json",
        ]
        manifest = generate_artifact_manifest(paths)
        for entry in manifest["artifacts"]:
            assert entry["claim_advancement"] == "none", (
                f"entry {entry['path']!r} missing claim_advancement: none"
            )

    def test_schema_version(self) -> None:
        manifest = generate_artifact_manifest([])
        assert manifest["schema_version"] == "0.1"

    def test_required_top_level_fields(self) -> None:
        manifest = generate_artifact_manifest([])
        for field in ("schema_version", "generated_at", "claim_advancement",
                      "artifact_count", "artifacts"):
            assert field in manifest, f"manifest missing top-level field: {field!r}"

    def test_artifact_count_matches_artifacts(self) -> None:
        paths = ["results/result_summary.json", "manifest.json", "geometry/source.step"]
        manifest = generate_artifact_manifest(paths)
        assert manifest["artifact_count"] == len(manifest["artifacts"])

    def test_each_entry_has_required_fields(self) -> None:
        paths = ["results/result_summary.json", "claims/proposals/p.json", "geometry/model.step"]
        manifest = generate_artifact_manifest(paths)
        for entry in manifest["artifacts"]:
            for field in ("path", "kind", "category", "exists", "claim_advancement"):
                assert field in entry, f"entry {entry['path']!r} missing field {field!r}"

    def test_each_entry_exists_true(self) -> None:
        manifest = generate_artifact_manifest(["results/result_summary.json"])
        assert manifest["artifacts"][0]["exists"] is True

    def test_stale_revalidation_annotates_freshness_categories(self) -> None:
        rs = {"requires_revalidation": True, "current_geometry_revision": 3}
        manifest = generate_artifact_manifest(
            ["results/result_summary.json", "results/evidence_index.json"],
            revalidation_status=rs,
        )
        assert manifest["requires_revalidation"] is True
        assert manifest["current_geometry_revision"] == 3
        for entry in manifest["artifacts"]:
            assert entry["requires_revalidation"] is True
            assert entry["geometry_revision"] == 3

    def test_fresh_revalidation_annotates_freshness_categories(self) -> None:
        rs = {"requires_revalidation": False, "current_geometry_revision": 2}
        manifest = generate_artifact_manifest(
            ["results/fields/displacement.summary.json"],
            revalidation_status=rs,
        )
        assert manifest["requires_revalidation"] is False
        assert manifest["current_geometry_revision"] == 2
        entry = manifest["artifacts"][0]
        assert entry["requires_revalidation"] is False
        assert entry["geometry_revision"] == 2

    def test_non_freshness_artifacts_not_annotated(self) -> None:
        rs = {"requires_revalidation": True, "current_geometry_revision": 5}
        manifest = generate_artifact_manifest(
            ["geometry/source.step", "manifest.json"],
            revalidation_status=rs,
        )
        for entry in manifest["artifacts"]:
            assert "requires_revalidation" not in entry
            assert "geometry_revision" not in entry

    def test_no_revalidation_status_defaults_to_false(self) -> None:
        manifest = generate_artifact_manifest(["results/result_summary.json"])
        assert manifest["requires_revalidation"] is False
        assert manifest["current_geometry_revision"] == 0
        entry = manifest["artifacts"][0]
        assert entry["requires_revalidation"] is False
        assert entry["geometry_revision"] == 0

    def test_manifest_path_excluded(self) -> None:
        manifest = generate_artifact_manifest([ARTIFACT_MANIFEST_PATH, "manifest.json"])
        paths = {e["path"] for e in manifest["artifacts"]}
        assert ARTIFACT_MANIFEST_PATH not in paths

    def test_custom_generated_at(self) -> None:
        ts = "2026-01-01T00:00:00+00:00"
        manifest = generate_artifact_manifest([], generated_at=ts)
        assert manifest["generated_at"] == ts

    def test_empty_paths_zero_count(self) -> None:
        manifest = generate_artifact_manifest([])
        assert manifest["artifact_count"] == 0
        assert manifest["artifacts"] == []

    def test_producer_tool_present_for_known_artifacts(self) -> None:
        manifest = generate_artifact_manifest(["results/result_summary.json"])
        entry = manifest["artifacts"][0]
        assert entry.get("producer_tool") == "postprocess.refresh_cae_summary"

    def test_evidence_role_present_for_known_artifacts(self) -> None:
        manifest = generate_artifact_manifest(["results/fields/displacement.summary.json"])
        entry = manifest["artifacts"][0]
        assert entry.get("evidence_role") == "displacement_extrema"

    def test_unknown_category_no_freshness_annotation(self) -> None:
        rs = {"requires_revalidation": True, "current_geometry_revision": 1}
        manifest = generate_artifact_manifest(["custom/weird/file.bin"], revalidation_status=rs)
        entry = manifest["artifacts"][0]
        assert entry["category"] == "unknown"
        assert "requires_revalidation" not in entry
        assert "geometry_revision" not in entry

    def test_revalidation_status_none_no_freshness_keys_on_non_freshness(self) -> None:
        manifest = generate_artifact_manifest(["manifest.json"])
        entry = manifest["artifacts"][0]
        assert "requires_revalidation" not in entry
        assert "geometry_revision" not in entry
